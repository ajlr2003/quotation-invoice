# =============================================================================
# app/routers/sales_invoices.py
# -----------------------------------------------------------------------------
# Customer (sales) invoice endpoints — the in-house replacement for the old
# /api/v1/odoo/invoices proxy. Mounted at /api/v1/sales/invoices. Reads need
# any authenticated user; every write needs ADMIN, MANAGER or FINANCE.
#
#   GET    /                          list (?status=Draft|Open|Overdue|Paid|Cancelled&q=)
#   GET    /kpis                      headline totals (base currency)
#   GET    /company                   seller block + bank accounts shown on the form
#   POST   /                          create a draft
#   GET    /{id}                      full invoice with lines + payments
#   PUT    /{id}                      replace a draft
#   DELETE /{id}                      delete a draft (posted invoices can only be cancelled)
#   POST   /{id}/post                 confirm — assigns the sequential number
#   POST   /{id}/cancel               cancel a posted invoice with no payments
#   POST   /{id}/email                email the PDF to the customer
#   POST   /{id}/payments             record a payment
#   DELETE /{id}/payments/{pid}       void a payment
#   GET    /{id}/pdf                  download the PDF
# =============================================================================

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.sales_invoice import (
    SalesInvoiceCreate,
    SalesInvoiceKPIs,
    SalesInvoiceListResponse,
    SalesInvoicePaymentCreate,
    SalesInvoiceResponse,
    SalesInvoiceUpdate,
    SellerProfile,
)
from app.services import sales_invoice_service as svc

router = APIRouter()

_finance = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.FINANCE)


@router.get("", response_model=SalesInvoiceListResponse, summary="List customer invoices")
async def list_invoices(
    status_filter: Optional[str] = Query(None, alias="status", description="Draft | Open | Overdue | Paid | Cancelled"),
    q: Optional[str] = Query(None, description="Search customer name or invoice number"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await svc.list_invoices(db, status_filter=status_filter, search=q, skip=skip, limit=limit)


@router.get("/company", response_model=SellerProfile,
            summary="Seller block and bank accounts printed on invoices (read-only)")
async def seller_profile(_=Depends(get_current_user)):
    return svc.get_seller_profile()


@router.get("/kpis", response_model=SalesInvoiceKPIs, summary="Invoice KPIs (base currency)")
async def kpis(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await svc.get_kpis(db)


@router.post("", response_model=SalesInvoiceResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a draft invoice")
async def create_invoice(
    payload: SalesInvoiceCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_finance),
):
    return await svc.create_invoice(db, payload, user.id)


@router.get("/{invoice_id}", response_model=SalesInvoiceResponse, summary="Get an invoice")
async def get_invoice(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await svc.get_invoice(db, invoice_id)


@router.put("/{invoice_id}", response_model=SalesInvoiceResponse, summary="Edit a draft invoice")
async def update_invoice(
    invoice_id: uuid.UUID,
    payload: SalesInvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_finance),
):
    return await svc.update_invoice(db, invoice_id, payload, user.id)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a draft invoice")
async def delete_invoice(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(_finance)):
    await svc.delete_draft(db, invoice_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{invoice_id}/post", response_model=SalesInvoiceResponse,
             summary="Confirm a draft — assigns the invoice number")
async def post_invoice(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(_finance)):
    return await svc.post_invoice(db, invoice_id, user.id)


@router.post("/{invoice_id}/cancel", response_model=SalesInvoiceResponse,
             summary="Cancel a posted invoice that has no payments")
async def cancel_invoice(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(_finance)):
    return await svc.cancel_invoice(db, invoice_id, user.id)


@router.post("/{invoice_id}/email", response_model=SalesInvoiceResponse,
             summary="Email the invoice PDF to the customer")
async def email_invoice(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(_finance)):
    return await svc.email_invoice(db, invoice_id, user.id)


@router.post("/{invoice_id}/payments", response_model=SalesInvoiceResponse,
             status_code=status.HTTP_201_CREATED, summary="Record a payment")
async def record_payment(
    invoice_id: uuid.UUID,
    payload: SalesInvoicePaymentCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_finance),
):
    return await svc.record_payment(db, invoice_id, payload, user.id)


@router.delete("/{invoice_id}/payments/{payment_id}", response_model=SalesInvoiceResponse,
               summary="Void a recorded payment")
async def delete_payment(
    invoice_id: uuid.UUID,
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(_finance),
):
    return await svc.delete_payment(db, invoice_id, payment_id, user.id)


@router.get("/{invoice_id}/pdf", summary="Download the invoice as PDF", response_class=Response)
async def invoice_pdf(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await svc.generate_pdf(db, invoice_id)
