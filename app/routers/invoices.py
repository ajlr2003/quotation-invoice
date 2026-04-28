"""
app/routers/invoices.py
Invoice endpoints — supplier-side invoices created from GRN.

All business logic lives in purchase_invoice_service; this router
handles HTTP concerns only and maps the service's PurchaseInvoiceResponse
to the public InvoiceResponse schema (which exposes `amount` not `total_amount`).

Routes:
  POST /api/v1/invoices/from-grn         — create invoice from a GRN
  GET  /api/v1/invoices                  — list all invoices
  POST /api/v1/invoices/{id}/approve     — approve a draft invoice
  POST /api/v1/invoices/{id}/pay         — mark an approved invoice as paid
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.invoice import InvoiceFromGRNRequest, InvoiceListResponse, InvoiceResponse
from app.schemas.purchase_invoice import PurchaseInvoiceCreate, PurchaseInvoiceResponse
from app.services import purchase_invoice_service

router = APIRouter()


def _to_invoice_response(src: PurchaseInvoiceResponse) -> InvoiceResponse:
    """
    Convert service-layer PurchaseInvoiceResponse → public InvoiceResponse.
    Maps total_amount → amount and carries all other fields across.
    """
    return InvoiceResponse(
        id=src.id,
        po_id=src.po_id,
        grn_id=src.grn_id,
        supplier_id=src.supplier_id,
        supplier_name=src.supplier_name,
        quantity=src.quantity,
        unit_price=src.unit_price,
        total_amount=src.total_amount,   # alias → amount in the serialised output
        status=src.status,
        created_at=src.created_at,
    )


# ---------------------------------------------------------------------------
# POST /from-grn  — create an invoice from a GRN
# ---------------------------------------------------------------------------

@router.post(
    "/from-grn",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an invoice from a Goods Receipt Note",
)
async def create_invoice_from_grn(
    payload: InvoiceFromGRNRequest,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Generate a supplier invoice directly from a GRN.

    **Calculation:** `amount = GRN.received_quantity × PO.unit_price`

    **Rules:**
    - GRN must exist.
    - PO linked to the GRN must exist.
    - `received_quantity` must be > 0.
    - Only one invoice per GRN is allowed (409 on duplicate).
    - Invoice starts in **draft** status.
    """
    svc_payload = PurchaseInvoiceCreate(grn_id=payload.grn_id)
    result = await purchase_invoice_service.create_invoice(db, svc_payload)
    return _to_invoice_response(result)


# ---------------------------------------------------------------------------
# GET /  — list all invoices
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=InvoiceListResponse,
    summary="List all invoices",
)
async def list_invoices(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Return all invoices ordered by creation date descending."""
    result = await purchase_invoice_service.list_invoices(db)
    return InvoiceListResponse(
        items=[_to_invoice_response(i) for i in result.items],
        total=result.total,
    )


# ---------------------------------------------------------------------------
# POST /{id}/approve
# ---------------------------------------------------------------------------

@router.post(
    "/{invoice_id}/approve",
    response_model=InvoiceResponse,
    summary="Approve a draft invoice",
)
async def approve_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Transition a **draft** invoice to **approved**.
    Only draft invoices may be approved.
    """
    result = await purchase_invoice_service.approve_invoice(db, invoice_id)
    return _to_invoice_response(result)


# ---------------------------------------------------------------------------
# POST /{id}/pay
# ---------------------------------------------------------------------------

@router.post(
    "/{invoice_id}/pay",
    response_model=InvoiceResponse,
    summary="Mark an approved invoice as paid",
)
async def pay_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Transition an **approved** invoice to **paid**.
    Only approved invoices may be marked paid.
    """
    result = await purchase_invoice_service.pay_invoice(db, invoice_id)
    return _to_invoice_response(result)
