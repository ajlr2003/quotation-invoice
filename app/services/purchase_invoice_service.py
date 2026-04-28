"""
app/services/purchase_invoice_service.py
Business logic for PurchaseInvoice (supplier-side invoices created from GRN).

Rules enforced:
- GRN must exist.
- One invoice per GRN — duplicate creation returns a 409 Conflict.
- total_amount = GRN.received_quantity * PO.unit_price (snapshot at creation).
- Status transitions: draft → approved → paid (must follow order).
"""
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PurchaseInvoiceStatus
from app.models.grn import GRN
from app.models.purchase_invoice import PurchaseInvoice
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.schemas.purchase_invoice import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceListResponse,
    PurchaseInvoiceResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_grn_or_404(db: AsyncSession, grn_id: uuid.UUID) -> GRN:
    result = await db.execute(select(GRN).where(GRN.id == grn_id))
    grn = result.scalar_one_or_none()
    if not grn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"GRN {grn_id} not found.",
        )
    return grn


async def _get_invoice_or_404(db: AsyncSession, invoice_id: uuid.UUID) -> PurchaseInvoice:
    result = await db.execute(
        select(PurchaseInvoice).where(PurchaseInvoice.id == invoice_id)
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found.",
        )
    return inv


async def _invoice_to_response(
    db: AsyncSession, inv: PurchaseInvoice, quantity: float
) -> PurchaseInvoiceResponse:
    """Attach supplier_name and quantity (not stored on the model) to the response."""
    result = await db.execute(
        select(Supplier.company_name).where(Supplier.id == inv.supplier_id)
    )
    supplier_name = result.scalar_one_or_none()
    data = PurchaseInvoiceResponse.model_validate(inv)
    data.supplier_name = supplier_name
    data.quantity = quantity
    return data


# ---------------------------------------------------------------------------
# Create Invoice
# ---------------------------------------------------------------------------

async def create_invoice(
    db: AsyncSession, payload: PurchaseInvoiceCreate
) -> PurchaseInvoiceResponse:
    grn_id = uuid.UUID(str(payload.grn_id))

    # 1 — GRN must exist
    grn = await _get_grn_or_404(db, grn_id)

    # 2 — Prevent duplicate invoice for the same GRN
    existing = await db.execute(
        select(PurchaseInvoice).where(PurchaseInvoice.grn_id == grn_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An invoice already exists for GRN {grn_id}.",
        )

    # 3 — Fetch the related PO (GRN → PO)
    po_result = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.id == grn.po_id)
    )
    po = po_result.scalar_one_or_none()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Purchase order {grn.po_id} linked to this GRN not found.",
        )

    # 4 — Validate quantities and pricing before calculating
    received_qty = Decimal(str(grn.received_quantity))
    unit_price = Decimal(str(po.unit_price))

    if received_qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GRN {grn_id} has received_quantity={grn.received_quantity}; must be > 0 to generate an invoice.",
        )
    if unit_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Purchase order {po.id} has unit_price={po.unit_price}; must be > 0 to generate an invoice.",
        )

    total_amount = received_qty * unit_price

    # 5 — Create the invoice (snapshot unit_price so it survives future PO edits)
    inv = PurchaseInvoice(
        po_id=po.id,
        grn_id=grn_id,
        supplier_id=po.supplier_id,
        unit_price=float(unit_price),
        total_amount=float(total_amount),
        status=PurchaseInvoiceStatus.DRAFT,
    )
    db.add(inv)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An invoice already exists for GRN {grn_id}.",
        )

    await db.refresh(inv)
    return await _invoice_to_response(db, inv, float(received_qty))


# ---------------------------------------------------------------------------
# Approve Invoice
# ---------------------------------------------------------------------------

async def approve_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> PurchaseInvoiceResponse:
    inv = await _get_invoice_or_404(db, invoice_id)

    if inv.status != PurchaseInvoiceStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only draft invoices can be approved (current status: '{inv.status}').",
        )

    inv.status = PurchaseInvoiceStatus.APPROVED
    await db.flush()

    grn_result = await db.execute(select(GRN).where(GRN.id == inv.grn_id))
    grn = grn_result.scalar_one_or_none()
    return await _invoice_to_response(db, inv, float(grn.received_quantity) if grn else 0.0)


# ---------------------------------------------------------------------------
# Pay Invoice
# ---------------------------------------------------------------------------

async def pay_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> PurchaseInvoiceResponse:
    inv = await _get_invoice_or_404(db, invoice_id)

    if inv.status != PurchaseInvoiceStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only approved invoices can be marked paid (current status: '{inv.status}').",
        )

    inv.status = PurchaseInvoiceStatus.PAID
    await db.flush()

    grn_result = await db.execute(select(GRN).where(GRN.id == inv.grn_id))
    grn = grn_result.scalar_one_or_none()
    return await _invoice_to_response(db, inv, float(grn.received_quantity) if grn else 0.0)


# ---------------------------------------------------------------------------
# List all Invoices
# ---------------------------------------------------------------------------

async def list_invoices(db: AsyncSession) -> PurchaseInvoiceListResponse:
    result = await db.execute(
        select(PurchaseInvoice, GRN.received_quantity, Supplier.company_name)
        .join(GRN, GRN.id == PurchaseInvoice.grn_id)
        .join(Supplier, Supplier.id == PurchaseInvoice.supplier_id)
        .order_by(PurchaseInvoice.created_at.desc())
    )
    rows = result.all()

    items = []
    for inv, received_qty, supplier_name in rows:
        data = PurchaseInvoiceResponse.model_validate(inv)
        data.supplier_name = supplier_name
        data.quantity = float(received_qty)
        items.append(data)

    return PurchaseInvoiceListResponse(items=items, total=len(items))
