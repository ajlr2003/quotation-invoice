"""
app/routers/purchase_invoices.py
Purchase Invoice endpoints (supplier-side invoices generated from GRN).

Routes:
  POST   /api/v1/purchase-invoices/            — create invoice from GRN
  GET    /api/v1/purchase-invoices/            — list all invoices
  POST   /api/v1/purchase-invoices/{id}/approve — approve a draft invoice
  POST   /api/v1/purchase-invoices/{id}/pay    — mark an approved invoice as paid
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.purchase_invoice import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceListResponse,
    PurchaseInvoiceResponse,
)
from app.services import purchase_invoice_service

router = APIRouter()


@router.post(
    "",
    response_model=PurchaseInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a purchase invoice from a GRN",
)
async def create_invoice(
    payload: PurchaseInvoiceCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Generate a supplier invoice from a Goods Receipt Note.

    **Rules:**
    - GRN must exist.
    - Only one invoice is allowed per GRN.
    - `total_amount` = `GRN.received_quantity × PO.unit_price`.
    - Invoice starts in **draft** status.
    """
    return await purchase_invoice_service.create_invoice(db, payload)


@router.get(
    "",
    response_model=PurchaseInvoiceListResponse,
    summary="List all purchase invoices",
)
async def list_invoices(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Return all purchase invoices ordered by creation date descending."""
    return await purchase_invoice_service.list_invoices(db)


@router.post(
    "/{invoice_id}/approve",
    response_model=PurchaseInvoiceResponse,
    summary="Approve a draft purchase invoice",
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
    return await purchase_invoice_service.approve_invoice(db, invoice_id)


@router.post(
    "/{invoice_id}/pay",
    response_model=PurchaseInvoiceResponse,
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
    return await purchase_invoice_service.pay_invoice(db, invoice_id)
