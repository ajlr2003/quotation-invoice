# =============================================================================
# app/services/supplier_quotation_service.py
# -----------------------------------------------------------------------------
# Business logic for recording and retrieving supplier bids on RFQs.
# Supports multi-item bids where each item carries its own price/qty.
# =============================================================================

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.rfq import RFQ, rfq_suppliers
from app.models.supplier import Supplier
from app.models.supplier_quotation import SupplierQuotation
from app.models.supplier_quotation_item import SupplierQuotationItem
from app.schemas.supplier_quotation import (
    QuotationCreate,
    QuotationListResponse,
    QuotationResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_rfq_or_404(db: AsyncSession, rfq_id: uuid.UUID) -> RFQ:
    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} not found.",
        )
    return rfq


async def _get_supplier_or_404(db: AsyncSession, supplier_id: uuid.UUID) -> Supplier:
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id} not found.",
        )
    return supplier


async def _assert_supplier_on_rfq(
    db: AsyncSession, rfq_id: uuid.UUID, supplier_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(rfq_suppliers).where(
            rfq_suppliers.c.rfq_id == rfq_id,
            rfq_suppliers.c.supplier_id == supplier_id,
        )
    )
    if not result.first():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Supplier is not assigned to this RFQ.",
        )


async def _load_quotation(
    db: AsyncSession, quotation_id: uuid.UUID
) -> SupplierQuotation:
    result = await db.execute(
        select(SupplierQuotation)
        .where(SupplierQuotation.id == quotation_id)
        .options(
            selectinload(SupplierQuotation.supplier),
            selectinload(SupplierQuotation.items),
        )
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Submit a quotation (with optional multi-item support)
# ---------------------------------------------------------------------------

async def submit_quotation(
    db: AsyncSession,
    payload: QuotationCreate,
) -> QuotationResponse:
    await _get_rfq_or_404(db, payload.rfq_id)
    await _get_supplier_or_404(db, payload.supplier_id)
    await _assert_supplier_on_rfq(db, payload.rfq_id, payload.supplier_id)

    # Compute total from items when provided; fall back to flat unit_price
    if payload.items:
        total_price = round(
            sum(float(i.unit_price) * float(i.quantity) for i in payload.items), 2
        )
    elif payload.unit_price is not None:
        total_price = float(payload.unit_price)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either items or unit_price.",
        )

    quotation = SupplierQuotation(
        rfq_id=payload.rfq_id,
        supplier_id=payload.supplier_id,
        unit_price=total_price,
        notes=payload.notes,
    )
    db.add(quotation)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A quotation from this supplier for this RFQ already exists.",
        )

    # Persist line items
    for item in payload.items:
        item_total = round(float(item.unit_price) * float(item.quantity), 2)
        db.add(SupplierQuotationItem(
            supplier_quotation_id=quotation.id,
            product_name=item.product_name.strip(),
            description=(item.description or "").strip() or None,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total=item_total,
        ))

    await db.flush()
    quotation_full = await _load_quotation(db, quotation.id)
    return QuotationResponse.model_validate(quotation_full)


# ---------------------------------------------------------------------------
# List quotations for an RFQ
# ---------------------------------------------------------------------------

async def list_quotations_for_rfq(
    db: AsyncSession,
    rfq_id: uuid.UUID,
) -> QuotationListResponse:
    await _get_rfq_or_404(db, rfq_id)

    result = await db.execute(
        select(SupplierQuotation)
        .where(SupplierQuotation.rfq_id == rfq_id)
        .options(
            selectinload(SupplierQuotation.supplier),
            selectinload(SupplierQuotation.items),
        )
        .order_by(SupplierQuotation.created_at.asc())
    )
    quotations = result.scalars().all()

    return QuotationListResponse(
        items=[QuotationResponse.model_validate(q) for q in quotations],
        total=len(quotations),
    )
