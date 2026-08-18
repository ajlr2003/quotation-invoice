# =============================================================================
# app/services/customer_rfq_service.py
# -----------------------------------------------------------------------------
# Business logic for the Customer RFQ module: create, list, get, status
# transitions. All DB writes use SQLAlchemy async sessions.
# =============================================================================

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_rfq import CustomerRFQ
from app.models.enums import ActivityEntityType, CustomerRFQStatus
from app.schemas.customer_rfq import (
    CustomerRFQCreate,
    CustomerRFQListResponse,
    CustomerRFQResponse,
    CustomerRFQStatusUpdate,
)
from app.services import activity_service

# ── State machine: allowed status transitions ──────────────────────────────────
_VALID_TRANSITIONS: dict[CustomerRFQStatus, set[CustomerRFQStatus]] = {
    CustomerRFQStatus.OPEN:   {CustomerRFQStatus.QUOTED, CustomerRFQStatus.CLOSED},
    CustomerRFQStatus.QUOTED: {CustomerRFQStatus.CLOSED},
    CustomerRFQStatus.CLOSED: set(),
}


async def create_customer_rfq(
    db: AsyncSession, payload: CustomerRFQCreate, user_id: Optional[uuid.UUID] = None
) -> CustomerRFQResponse:
    rfq = CustomerRFQ(**payload.model_dump())
    db.add(rfq)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.CUSTOMER_RFQ, rfq.id, "created",
        f"Customer RFQ {rfq.customer_reference} logged for {rfq.customer_name}",
        user_id=user_id,
    )
    await db.commit()
    await db.refresh(rfq)
    return CustomerRFQResponse.model_validate(rfq)


async def list_customer_rfqs(
    db: AsyncSession, status_filter: Optional[CustomerRFQStatus] = None
) -> CustomerRFQListResponse:
    q = select(CustomerRFQ).order_by(CustomerRFQ.created_at.desc())
    if status_filter:
        q = q.where(CustomerRFQ.status == status_filter)
    rows = (await db.execute(q)).scalars().all()
    items = [CustomerRFQResponse.model_validate(r) for r in rows]
    return CustomerRFQListResponse(items=items, total=len(items))


async def get_customer_rfq(db: AsyncSession, rfq_id: uuid.UUID) -> Optional[CustomerRFQ]:
    return (await db.execute(select(CustomerRFQ).where(CustomerRFQ.id == rfq_id))).scalar_one_or_none()


async def update_status(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    payload: CustomerRFQStatusUpdate,
    user_id: Optional[uuid.UUID] = None,
) -> CustomerRFQResponse:
    rfq = await get_customer_rfq(db, rfq_id)
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer RFQ not found")

    if payload.status != rfq.status:
        allowed = _VALID_TRANSITIONS.get(rfq.status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot transition from '{rfq.status.value}' to '{payload.status.value}'",
            )
        old_status = rfq.status
        rfq.status = payload.status
        activity_service.log_activity(
            db, ActivityEntityType.CUSTOMER_RFQ, rfq.id, "status_changed",
            f"Status changed from {old_status.value} to {payload.status.value}",
            user_id=user_id,
        )
    await db.commit()
    await db.refresh(rfq)
    return CustomerRFQResponse.model_validate(rfq)


async def mark_quoted_if_open(db: AsyncSession, rfq_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> None:
    """Auto-transition open -> quoted when a Sales Quotation links to this
    Customer RFQ. Silently no-ops if the RFQ is already quoted/closed or
    doesn't exist — this is a side effect of quotation creation, not a
    user-facing action, so it shouldn't block or surprise-fail that flow.
    """
    rfq = await get_customer_rfq(db, rfq_id)
    if not rfq or rfq.status != CustomerRFQStatus.OPEN:
        return
    rfq.status = CustomerRFQStatus.QUOTED
    activity_service.log_activity(
        db, ActivityEntityType.CUSTOMER_RFQ, rfq.id, "status_changed",
        "Status changed from open to quoted (quotation created)",
        user_id=user_id,
    )
