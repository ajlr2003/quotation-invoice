"""
app/services/grn_service.py
Business logic for Goods Receipt Note (GRN).

Rules enforced:
- PO must exist.
- received_quantity must be > 0 (enforced by schema).
- received_quantity + po.received_quantity must not exceed po.ordered_quantity.
- After a GRN is created, PO.received_quantity is incremented and PO.status
  is recalculated: created → partial → completed.
"""
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PurchaseOrderStatus
from app.models.grn import GRN
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.schemas.grn import GRNCreate, GRNListResponse, GRNResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_po_or_404(db: AsyncSession, po_id: uuid.UUID) -> PurchaseOrder:
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found.",
        )
    return po


def _recalculate_po_status(po: PurchaseOrder) -> None:
    """
    Recalculate and assign PO.status based on received vs ordered quantity.
      received == 0            → CREATED
      0 < received < ordered   → PARTIAL
      received >= ordered      → COMPLETED
    """
    received = Decimal(str(po.received_quantity))
    ordered = Decimal(str(po.ordered_quantity))

    if received <= 0:
        po.status = PurchaseOrderStatus.CREATED
    elif received < ordered:
        po.status = PurchaseOrderStatus.PARTIAL
    else:
        po.status = PurchaseOrderStatus.COMPLETED


async def _grn_to_response(db: AsyncSession, grn: GRN) -> GRNResponse:
    """Fetch supplier_name for a single GRN and build the response."""
    result = await db.execute(
        select(Supplier.company_name)
        .select_from(PurchaseOrder)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .where(PurchaseOrder.id == grn.po_id)
    )
    supplier_name = result.scalar_one()
    return GRNResponse(
        id=grn.id,
        po_id=grn.po_id,
        supplier_name=supplier_name,
        received_quantity=grn.received_quantity,
        created_at=grn.created_at,
    )


# ---------------------------------------------------------------------------
# Create GRN
# ---------------------------------------------------------------------------

async def create_grn(db: AsyncSession, payload: GRNCreate) -> GRNResponse:
    po_id = uuid.UUID(str(payload.po_id))

    # 1 — PO must exist
    po = await _get_po_or_404(db, po_id)

    # 2 — Validate quantity will not exceed what was ordered
    new_received = Decimal(str(payload.received_quantity))
    current_received = Decimal(str(po.received_quantity))
    ordered = Decimal(str(po.ordered_quantity))

    if ordered > 0 and (current_received + new_received) > ordered:
        remaining = float(ordered - current_received)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot receive {payload.received_quantity} units: only "
                f"{remaining} unit(s) remaining on this purchase order "
                f"(ordered={float(ordered)}, already received={float(current_received)})."
            ),
        )

    # 3 — Insert GRN
    grn = GRN(po_id=po_id, received_quantity=payload.received_quantity)
    db.add(grn)
    await db.flush()

    # 4 — Update PO received_quantity and recalculate status
    po.received_quantity = float(current_received + new_received)
    _recalculate_po_status(po)
    await db.flush()

    await db.refresh(grn)
    return await _grn_to_response(db, grn)


# ---------------------------------------------------------------------------
# List GRNs (optionally filtered by po_id)
# ---------------------------------------------------------------------------

async def list_grns(
    db: AsyncSession,
    po_id: uuid.UUID | None = None,
) -> GRNListResponse:
    query = (
        select(GRN, Supplier.company_name)
        .join(PurchaseOrder, PurchaseOrder.id == GRN.po_id)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .order_by(GRN.created_at.desc())
    )
    if po_id is not None:
        query = query.where(GRN.po_id == po_id)

    result = await db.execute(query)
    rows = result.all()
    items = [
        GRNResponse(
            id=grn.id,
            po_id=grn.po_id,
            supplier_name=supplier_name,
            received_quantity=grn.received_quantity,
            created_at=grn.created_at,
        )
        for grn, supplier_name in rows
    ]
    return GRNListResponse(items=items, total=len(items))
