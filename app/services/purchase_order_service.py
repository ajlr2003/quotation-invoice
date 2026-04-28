"""
app/services/purchase_order_service.py
Business logic for PurchaseOrder creation.

Rules enforced:
- RFQ must exist and be in AWARDED status.
- Supplier must be linked to the RFQ via rfq_suppliers.
- At most one PO per RFQ/supplier pair (unique constraint, caught as 409).
- ordered_quantity is seeded from the sum of all RFQ item quantities.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RFQStatus
from app.models.purchase_order import PurchaseOrder
from app.models.rfq import RFQ, rfq_suppliers
from app.models.rfq_item import RFQItem
from app.models.supplier import Supplier
from app.models.supplier_quotation import SupplierQuotation
from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderListResponse,
    PurchaseOrderResponse,
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


async def _sum_rfq_item_quantities(db: AsyncSession, rfq_id: uuid.UUID) -> float:
    """Return the total ordered quantity across all line items of an RFQ."""
    result = await db.execute(
        select(func.sum(RFQItem.quantity)).where(RFQItem.rfq_id == rfq_id)
    )
    return float(result.scalar() or 0)


async def _get_unit_price_or_422(
    db: AsyncSession, rfq_id: uuid.UUID, supplier_id: uuid.UUID
) -> float:
    """
    Fetch the supplier's unit price from supplier_quotations.
    Raises 422 if no quotation exists or the price is not positive.
    """
    result = await db.execute(
        select(SupplierQuotation.unit_price).where(
            SupplierQuotation.rfq_id == rfq_id,
            SupplierQuotation.supplier_id == supplier_id,
        )
    )
    price = result.scalar_one_or_none()
    if price is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No quotation found for this supplier on the given RFQ. "
                "The supplier must submit a quotation before a purchase order can be created."
            ),
        )
    unit_price = float(price)
    if unit_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Supplier's quoted unit price must be greater than zero.",
        )
    return unit_price


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
        return await _po_to_response(db, po)

    # 5 — Seed ordered_quantity and pricing from RFQ items + SupplierQuotation
    ordered_quantity = await _sum_rfq_item_quantities(db, rfq_id)
    if ordered_quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot create a purchase order for an RFQ with no items or zero total quantity.",
        )

    # unit_price  = supplier's quoted per-unit price (raises 422 if missing/zero).
    # total_price = unit_price × ordered_quantity — locked at PO creation time.
    unit_price = await _get_unit_price_or_422(db, rfq_id, supplier_id)
    total_price = unit_price * ordered_quantity

    # 6 — Create new PO
    po = PurchaseOrder(
        rfq_id=rfq_id,
        supplier_id=supplier_id,
        ordered_quantity=ordered_quantity,
        received_quantity=0,
        unit_price=unit_price,
        total_price=total_price,
    )
    db.add(po)
    await db.flush()
    await db.refresh(po)
    return await _po_to_response(db, po)


# ---------------------------------------------------------------------------
# Shared response builder (attaches supplier_name)
# ---------------------------------------------------------------------------

async def _po_to_response(db: AsyncSession, po: PurchaseOrder) -> PurchaseOrderResponse:
    result = await db.execute(
        select(Supplier.company_name).where(Supplier.id == po.supplier_id)
    )
    supplier_name = result.scalar_one_or_none()
    data = PurchaseOrderResponse.model_validate(po)
    data.supplier_name = supplier_name
    return data


# ---------------------------------------------------------------------------
# Get single PO by ID
# ---------------------------------------------------------------------------

async def get_purchase_order(
    db: AsyncSession, po_id: uuid.UUID
) -> PurchaseOrderResponse:
    result = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.id == po_id)
    )
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found.",
        )
    return await _po_to_response(db, po)


# ---------------------------------------------------------------------------
# List all POs
# ---------------------------------------------------------------------------

async def list_purchase_orders(db: AsyncSession) -> PurchaseOrderListResponse:
    result = await db.execute(
        select(PurchaseOrder, Supplier.company_name)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .order_by(PurchaseOrder.created_at.desc())
    )
    rows = result.all()

    items = []
    for po, supplier_name in rows:
        data = PurchaseOrderResponse.model_validate(po)
        data.supplier_name = supplier_name
        items.append(data)

    return PurchaseOrderListResponse(items=items, total=len(items))
