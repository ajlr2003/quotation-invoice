# =============================================================================
# app/services/supplier_service.py
# -----------------------------------------------------------------------------
# Business logic for Supplier CRUD: create, list, get, update, and
# soft-delete (deactivation).
# =============================================================================

import uuid
import math
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ActivityEntityType
from app.models.rfq import RFQ, rfq_suppliers
from app.models.rfq_item import RFQItem
from app.models.supplier import Supplier
from app.schemas.rfq import RFQListResponse, RFQSummaryResponse
from app.schemas.supplier import (
    SupplierCreateRequest,
    SupplierUpdateRequest,
    SupplierResponse,
    SupplierListResponse,
)
from app.services import activity_service


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_supplier_or_404(db: AsyncSession, supplier_id: uuid.UUID) -> Supplier:
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id} not found.",
        )
    return supplier


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_supplier(
    db: AsyncSession,
    payload: SupplierCreateRequest,
    user_id: Optional[uuid.UUID] = None,
) -> SupplierResponse:
    # Check for duplicate email
    existing = await db.execute(
        select(Supplier).where(Supplier.email == payload.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A supplier with this email already exists.",
        )

    supplier = Supplier(
        **payload.model_dump(exclude={'email'}),
        email=payload.email.lower(),
    )
    db.add(supplier)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.SUPPLIER, supplier.id, "created",
        f"Supplier '{supplier.company_name}' added",
        user_id=user_id,
    )
    await db.flush()
    return SupplierResponse.model_validate(supplier)


# ---------------------------------------------------------------------------
# List (paginated, with search + filters)
# ---------------------------------------------------------------------------

async def list_suppliers(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_preferred: Optional[bool] = None,
    country: Optional[str] = None,
) -> SupplierListResponse:
    query = select(Supplier)

    # Filters
    if is_active is not None:
        query = query.where(Supplier.is_active == is_active)
    if is_preferred is not None:
        query = query.where(Supplier.is_preferred == is_preferred)
    if country:
        query = query.where(Supplier.country.ilike(f"%{country}%"))

    # Full-text search across name, email, contact
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Supplier.company_name.ilike(term),
                Supplier.email.ilike(term),
                Supplier.contact_name.ilike(term),
            )
        )

    # Total count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Supplier.company_name).offset(offset).limit(page_size)
    result = await db.execute(query)
    suppliers = result.scalars().all()

    return SupplierListResponse(
        items=[SupplierResponse.model_validate(s) for s in suppliers],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


# ---------------------------------------------------------------------------
# Get by ID
# ---------------------------------------------------------------------------

async def get_supplier(
    db: AsyncSession,
    supplier_id: uuid.UUID,
) -> SupplierResponse:
    supplier = await _get_supplier_or_404(db, supplier_id)
    return SupplierResponse.model_validate(supplier)


# ---------------------------------------------------------------------------
# Update (PATCH — partial update)
# ---------------------------------------------------------------------------

async def update_supplier(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    payload: SupplierUpdateRequest,
    user_id: Optional[uuid.UUID] = None,
) -> SupplierResponse:
    supplier = await _get_supplier_or_404(db, supplier_id)

    # If email is being changed, check for conflicts
    update_data = payload.model_dump(exclude_none=True)
    if "email" in update_data:
        new_email = update_data["email"].lower()
        if new_email != supplier.email:
            conflict = await db.execute(
                select(Supplier).where(
                    Supplier.email == new_email,
                    Supplier.id != supplier_id,
                )
            )
            if conflict.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Another supplier with this email already exists.",
                )
        update_data["email"] = new_email

    changed_fields = [f for f in update_data if getattr(supplier, f) != update_data[f]]
    for field, value in update_data.items():
        setattr(supplier, field, value)

    if changed_fields:
        activity_service.log_activity(
            db, ActivityEntityType.SUPPLIER, supplier.id, "updated",
            f"Updated: {', '.join(changed_fields)}",
            user_id=user_id,
        )

    await db.flush()
    # updated_at is server-managed (onupdate=func.now()) and left expired
    # after flush — refresh explicitly so Pydantic doesn't trigger an
    # implicit lazy-load, which raises MissingGreenlet under async sessions.
    await db.refresh(supplier)
    return SupplierResponse.model_validate(supplier)


# ---------------------------------------------------------------------------
# RFQs this supplier has been invited to
# ---------------------------------------------------------------------------

async def list_supplier_rfqs(
    db: AsyncSession,
    supplier_id: uuid.UUID,
) -> RFQListResponse:
    """Return every RFQ this supplier was invited to, most recent first.

    Mirrors the equivalent supplier-facing view of a vendor's "Purchases"
    smart button — lets the supplier detail screen show their full RFQ
    history without a separate lookup.
    """
    await _get_supplier_or_404(db, supplier_id)

    result = await db.execute(
        select(RFQ)
        .join(rfq_suppliers, rfq_suppliers.c.rfq_id == RFQ.id)
        .where(rfq_suppliers.c.supplier_id == supplier_id)
        .order_by(RFQ.created_at.desc())
    )
    rfqs = result.scalars().all()

    if rfqs:
        rfq_ids = [r.id for r in rfqs]
        count_q = await db.execute(
            select(RFQItem.rfq_id, func.count(RFQItem.id).label("cnt"))
            .where(RFQItem.rfq_id.in_(rfq_ids))
            .group_by(RFQItem.rfq_id)
        )
        counts = {row.rfq_id: row.cnt for row in count_q}
    else:
        counts = {}

    summaries = []
    for rfq in rfqs:
        s = RFQSummaryResponse.model_validate(rfq)
        s.item_count = counts.get(rfq.id, 0)
        summaries.append(s)

    return RFQListResponse(
        items=summaries, total=len(summaries), page=1, page_size=len(summaries) or 1, pages=1,
    )


# ---------------------------------------------------------------------------
# Delete (soft delete — sets is_active = False)
# ---------------------------------------------------------------------------

async def delete_supplier(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    user_id: Optional[uuid.UUID] = None,
) -> dict:
    supplier = await _get_supplier_or_404(db, supplier_id)

    # Check if supplier has active quotes before deactivating
    from sqlalchemy import select as sa_select
    from app.models.supplier_quote import SupplierQuote
    from app.models.enums import SupplierQuoteStatus

    active_quotes = await db.execute(
        sa_select(func.count()).where(
            SupplierQuote.supplier_id == supplier_id,
            SupplierQuote.status == SupplierQuoteStatus.PENDING,
        )
    )
    pending_count = active_quotes.scalar_one()
    if pending_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot deactivate supplier with {pending_count} pending quote(s). "
                   "Resolve all pending quotes first.",
        )

    supplier.is_active = False
    activity_service.log_activity(
        db, ActivityEntityType.SUPPLIER, supplier.id, "deactivated",
        f"Supplier '{supplier.company_name}' deactivated",
        user_id=user_id,
    )
    await db.flush()
    return {"message": f"Supplier '{supplier.company_name}' has been deactivated."}
