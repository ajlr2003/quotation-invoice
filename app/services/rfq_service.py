"""
app/services/rfq_service.py
Business logic for RFQ and RFQItem CRUD.

Status transition rules enforced here:
  draft      → sent, cancelled
  sent       → received, cancelled
  received   → evaluated, cancelled
  evaluated  → closed, cancelled
  closed     → (terminal)
  cancelled  → (terminal)
"""
import math
import uuid
from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import exists, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import RFQStatus
from app.models.purchase_order import PurchaseOrder
from app.models.rfq import RFQ, rfq_suppliers
from app.models.rfq_item import RFQItem
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.rfq import (
    RFQCreateRequest,
    RFQItemCreateRequest,
    RFQItemListResponse,
    RFQItemResponse,
    RFQListResponse,
    RFQResponse,
    RFQSummaryResponse,
    RFQUpdateRequest,
    SelectSupplierRequest,
)

# ---------------------------------------------------------------------------
# Valid status transitions
# ---------------------------------------------------------------------------

_ALLOWED_TRANSITIONS: dict[RFQStatus, set[RFQStatus]] = {
    RFQStatus.DRAFT:      {RFQStatus.SENT, RFQStatus.CANCELLED},
    RFQStatus.SENT:       {RFQStatus.RECEIVED, RFQStatus.CANCELLED},
    RFQStatus.RECEIVED:   {RFQStatus.EVALUATED, RFQStatus.CANCELLED},
    RFQStatus.EVALUATED:  {RFQStatus.AWARDED, RFQStatus.CLOSED, RFQStatus.CANCELLED},
    RFQStatus.AWARDED:    {RFQStatus.CLOSED, RFQStatus.CANCELLED},
    RFQStatus.CLOSED:     set(),
    RFQStatus.CANCELLED:  set(),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_po_for_rfq(db: AsyncSession, rfq_id: uuid.UUID):
    """Return the PurchaseOrder for this RFQ, or None if not yet created."""
    result = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.rfq_id == rfq_id)
    )
    return result.scalar_one_or_none()


async def _get_rfq_or_404(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    load_items: bool = True,
) -> RFQ:
    query = select(RFQ).where(RFQ.id == rfq_id)
    if load_items:
        query = query.options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.suppliers),
        )
    result = await db.execute(query)
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} not found.",
        )
    return rfq


async def _get_item_or_404(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    item_id: uuid.UUID,
) -> RFQItem:
    result = await db.execute(
        select(RFQItem).where(
            RFQItem.id == item_id,
            RFQItem.rfq_id == rfq_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found on RFQ {rfq_id}.",
        )
    return item


def _assert_editable(rfq: RFQ) -> None:
    """Raise 409 if RFQ is in a terminal or non-editable state."""
    if rfq.status not in {RFQStatus.DRAFT}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"RFQ cannot be modified in '{rfq.status}' status. "
                   "Only DRAFT RFQs are editable.",
        )


def _assert_transition(rfq: RFQ, new_status: RFQStatus) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(rfq.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot transition RFQ from '{rfq.status}' to '{new_status}'. "
                   f"Allowed transitions: {[s.value for s in allowed] or 'none'}.",
        )


async def _next_line_number(db: AsyncSession, rfq_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.max(RFQItem.line_number)).where(RFQItem.rfq_id == rfq_id)
    )
    max_line = result.scalar_one_or_none()
    return (max_line or 0) + 1


async def _generate_rfq_number(db: AsyncSession) -> str:
    """Auto-generate sequential RFQ number: RFQ-00001, RFQ-00002 …"""
    result = await db.execute(select(func.count()).select_from(RFQ))
    count = result.scalar_one()
    return f"RFQ-{(count + 1):05d}"


# ---------------------------------------------------------------------------
# RFQ — Create
# ---------------------------------------------------------------------------

async def create_rfq(
    db: AsyncSession,
    payload: RFQCreateRequest,
    current_user: User,
) -> RFQResponse:
    rfq_number = await _generate_rfq_number(db)

    rfq = RFQ(
        rfq_number=rfq_number,
        title=payload.title,
        description=payload.description,
        currency=payload.currency,
        issue_date=payload.issue_date,
        deadline=payload.deadline,
        status=RFQStatus.DRAFT,
        created_by_id=current_user.id,
    )
    db.add(rfq)
    await db.flush()  # get rfq.id before adding items

    # Attach invited suppliers via direct join-table insert (avoids async lazy-load)
    if payload.supplier_ids:
        await db.execute(
            insert(rfq_suppliers).values(
                [{"rfq_id": rfq.id, "supplier_id": sid} for sid in payload.supplier_ids]
            )
        )

    # Optionally create inline items
    if payload.items:
        for idx, item_payload in enumerate(payload.items, start=1):
            item = RFQItem(
                rfq_id=rfq.id,
                line_number=idx,
                **item_payload.model_dump(),
            )
            db.add(item)

    await db.flush()
    # Capture id before expiring, then expire so selectinload re-fetches suppliers
    rfq_id = rfq.id
    db.expire(rfq)
    rfq_full = await _get_rfq_or_404(db, rfq_id)
    return RFQResponse.from_orm_with_count(rfq_full)


# ---------------------------------------------------------------------------
# RFQ — List
# ---------------------------------------------------------------------------

async def list_rfqs(
    db: AsyncSession,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    status_filter: Optional[RFQStatus] = None,
    my_rfqs_only: bool = False,
) -> RFQListResponse:
    # Base query — count items per RFQ via subquery
    item_count_subq = (
        select(RFQItem.rfq_id, func.count(RFQItem.id).label("item_count"))
        .group_by(RFQItem.rfq_id)
        .subquery()
    )

    query = select(RFQ)

    if my_rfqs_only:
        query = query.where(RFQ.created_by_id == current_user.id)
    if status_filter:
        query = query.where(RFQ.status == status_filter)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                RFQ.rfq_number.ilike(term),
                RFQ.title.ilike(term),
                RFQ.description.ilike(term),
            )
        )

    # Total count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(RFQ.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    rfqs = result.scalars().all()

    # Build item_count per RFQ efficiently
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
        items=summaries,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


# ---------------------------------------------------------------------------
# RFQ — Get by ID
# ---------------------------------------------------------------------------

async def get_rfq(db: AsyncSession, rfq_id: uuid.UUID) -> RFQResponse:
    rfq = await _get_rfq_or_404(db, rfq_id)
    po = await _get_po_for_rfq(db, rfq_id)
    return RFQResponse.from_orm_with_count(rfq, po)


# ---------------------------------------------------------------------------
# RFQ — Update (PATCH)
# ---------------------------------------------------------------------------

async def update_rfq(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    payload: RFQUpdateRequest,
    current_user: User,
) -> RFQResponse:
    rfq = await _get_rfq_or_404(db, rfq_id)

    update_data = payload.model_dump(exclude_none=True)

    # Handle status transition separately
    new_status = update_data.pop("status", None)
    if new_status and new_status != rfq.status:
        _assert_transition(rfq, new_status)
        rfq.status = new_status
    elif update_data:
        # Non-status field edits only allowed in DRAFT
        _assert_editable(rfq)

    # Validate deadline vs issue_date
    issue = update_data.get("issue_date", rfq.issue_date)
    deadline = update_data.get("deadline", rfq.deadline)
    if issue and deadline and deadline <= issue:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="deadline must be after issue_date.",
        )

    for field, value in update_data.items():
        setattr(rfq, field, value)

    await db.flush()
    rfq_full = await _get_rfq_or_404(db, rfq_id)
    po = await _get_po_for_rfq(db, rfq_id)
    return RFQResponse.from_orm_with_count(rfq_full, po)


# ---------------------------------------------------------------------------
# RFQ — Delete (only DRAFT RFQs can be hard-deleted)
# ---------------------------------------------------------------------------

async def delete_rfq(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    current_user: User,
) -> dict:
    rfq = await _get_rfq_or_404(db, rfq_id, load_items=False)
    _assert_editable(rfq)  # only DRAFT

    await db.delete(rfq)
    await db.flush()
    return {"message": f"RFQ '{rfq.rfq_number}' has been deleted."}


# ---------------------------------------------------------------------------
# RFQ — Send (DRAFT → SENT)
# ---------------------------------------------------------------------------

async def send_rfq(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    current_user: User,
) -> RFQResponse:
    rfq = await _get_rfq_or_404(db, rfq_id)
    _assert_transition(rfq, RFQStatus.SENT)  # enforces draft-only rule
    rfq.status = RFQStatus.SENT
    await db.flush()
    rfq_full = await _get_rfq_or_404(db, rfq_id)
    return RFQResponse.from_orm_with_count(rfq_full)


# ============================================================================
# RFQ Items
# ============================================================================

# ---------------------------------------------------------------------------
# Add item to RFQ
# ---------------------------------------------------------------------------

async def add_rfq_item(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    payload: RFQItemCreateRequest,
    current_user: User,
) -> RFQItemResponse:
    rfq = await _get_rfq_or_404(db, rfq_id, load_items=False)
    _assert_editable(rfq)

    line_number = await _next_line_number(db, rfq_id)

    item = RFQItem(
        rfq_id=rfq_id,
        line_number=line_number,
        **payload.model_dump(),
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return RFQItemResponse.model_validate(item)


# ---------------------------------------------------------------------------
# List items for an RFQ
# ---------------------------------------------------------------------------

async def list_rfq_items(
    db: AsyncSession,
    rfq_id: uuid.UUID,
) -> RFQItemListResponse:
    # Verify RFQ exists
    await _get_rfq_or_404(db, rfq_id, load_items=False)

    result = await db.execute(
        select(RFQItem)
        .where(RFQItem.rfq_id == rfq_id)
        .order_by(RFQItem.line_number)
    )
    items = result.scalars().all()

    return RFQItemListResponse(
        items=[RFQItemResponse.model_validate(i) for i in items],
        total=len(items),
    )


# ---------------------------------------------------------------------------
# Delete a single item from RFQ
# ---------------------------------------------------------------------------

async def delete_rfq_item(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: User,
) -> dict:
    rfq = await _get_rfq_or_404(db, rfq_id, load_items=False)
    _assert_editable(rfq)

    item = await _get_item_or_404(db, rfq_id, item_id)

    # Check item has no supplier quotes
    from app.models.supplier_quote import SupplierQuote
    quote_count = await db.execute(
        select(func.count()).where(SupplierQuote.rfq_item_id == item_id)
    )
    if quote_count.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete item that already has supplier quotes.",
        )

    await db.delete(item)
    await db.flush()

    # Re-sequence line numbers
    remaining = await db.execute(
        select(RFQItem)
        .where(RFQItem.rfq_id == rfq_id)
        .order_by(RFQItem.line_number)
    )
    for idx, remaining_item in enumerate(remaining.scalars().all(), start=1):
        remaining_item.line_number = idx
    await db.flush()

    return {"message": f"Item '{item.product_name}' (line {item.line_number}) removed from RFQ."}


# ---------------------------------------------------------------------------
# Select Supplier (EVALUATED / RECEIVED → AWARDED)
# ---------------------------------------------------------------------------

async def select_supplier(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    payload: SelectSupplierRequest,
    current_user: User,
) -> RFQResponse:
    rfq = await _get_rfq_or_404(db, rfq_id)

    # Allow selection from any active post-send status
    if rfq.status not in {RFQStatus.SENT, RFQStatus.RECEIVED, RFQStatus.EVALUATED, RFQStatus.AWARDED}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Cannot select a supplier when RFQ is in '{rfq.status}' status. "
                "RFQ must be in SENT, RECEIVED, EVALUATED, or AWARDED status."
            ),
        )

    # Normalise to plain uuid.UUID objects — avoids asyncpg type mismatch when
    # the values arrive as strings or UUID subclasses from path/body parsing.
    lookup_rfq_id = uuid.UUID(str(rfq_id))
    lookup_supplier_id = uuid.UUID(str(payload.supplier_id))

    # Supplier must be linked to this RFQ via rfq_suppliers
    membership = await db.execute(
        select(
            exists().where(
                rfq_suppliers.c.rfq_id == lookup_rfq_id,
                rfq_suppliers.c.supplier_id == lookup_supplier_id,
            )
        )
    )
    if not membership.scalar():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Supplier is not assigned to this RFQ.",
        )

    rfq.selected_supplier_id = payload.supplier_id
    rfq.status = RFQStatus.AWARDED
    await db.flush()

    # Reload with all relationships — populate_existing forces SQLAlchemy to
    # re-fetch from DB even if the instance is already in the session identity map.
    result = await db.execute(
        select(RFQ)
        .where(RFQ.id == rfq_id)
        .options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.suppliers),
            selectinload(RFQ.selected_supplier),
        )
        .execution_options(populate_existing=True)
    )
    rfq_full = result.scalar_one()
    po = await _get_po_for_rfq(db, rfq_id)
    return RFQResponse.from_orm_with_count(rfq_full, po)
