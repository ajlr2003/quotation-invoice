"""
app/services/purchase_order_service.py
Business logic for PurchaseOrder creation.

Rules enforced:
- RFQ must exist.
- RFQ must be in AWARDED status.
- Supplier must be linked to the RFQ via rfq_suppliers.
- At most one PO per RFQ/supplier pair (unique constraint, caught as 409).
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RFQStatus
from app.models.purchase_order import PurchaseOrder
from app.models.rfq import RFQ, rfq_suppliers
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderResponse


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


# ---------------------------------------------------------------------------
# Create PO
# ---------------------------------------------------------------------------

async def create_purchase_order(
    db: AsyncSession,
    payload: PurchaseOrderCreate,
) -> PurchaseOrderResponse:
    rfq_id = uuid.UUID(str(payload.rfq_id))

    # 1 — RFQ must exist
    rfq = await _get_rfq_or_404(db, rfq_id)

    # 2 — RFQ must be awarded
    if rfq.status != RFQStatus.AWARDED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Cannot create a purchase order for an RFQ in '{rfq.status}' status. "
                "RFQ must be in AWARDED status."
            ),
        )

    # Resolve supplier_id — use payload value or fall back to rfq.selected_supplier_id
    raw_supplier_id = payload.supplier_id or rfq.selected_supplier_id
    if not raw_supplier_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="supplier_id is required (or select a supplier on the RFQ first).",
        )
    supplier_id = uuid.UUID(str(raw_supplier_id))

    # 3 — Supplier must be linked to this RFQ
    membership = await db.execute(
        select(
            exists().where(
                rfq_suppliers.c.rfq_id == rfq_id,
                rfq_suppliers.c.supplier_id == supplier_id,
            )
        )
    )
    if not membership.scalar():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Supplier is not assigned to this RFQ.",
        )

    # 4 — Return existing PO if one already exists (idempotent)
    existing = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.rfq_id == rfq_id,
            PurchaseOrder.supplier_id == supplier_id,
        )
    )
    po = existing.scalar_one_or_none()
    if po:
        return PurchaseOrderResponse.model_validate(po)

    # 5 — Create new PO
    po = PurchaseOrder(rfq_id=rfq_id, supplier_id=supplier_id)
    db.add(po)
    await db.flush()
    await db.refresh(po)
    return PurchaseOrderResponse.model_validate(po)
