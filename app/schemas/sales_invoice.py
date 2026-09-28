# =============================================================================
# app/schemas/sales_invoice.py
# -----------------------------------------------------------------------------
# Pydantic request/response schemas for customer (sales) invoices.
# Totals, net prices and status are always computed server-side — clients
# only send raw quantities/prices and never the derived values.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date as _Date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import SalesInvoiceStatus

PAYMENT_METHODS = ("bank_transfer", "cash", "cheque", "card", "other")


# ── Items ─────────────────────────────────────────────────────────────────────

class SalesInvoiceItemCreate(BaseModel):
    catalog_no: Optional[str] = None
    item_name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    qty: float = Field(gt=0)
    unit: str = "EA"
    unit_price: float = Field(ge=0)
    discount: float = Field(default=0, ge=0, le=100)


class SalesInvoiceItemResponse(BaseModel):
    id: uuid.UUID
    line_no: int
    catalog_no: Optional[str] = None
    item_name: str
    description: Optional[str] = None
    qty: float
    unit: str
    unit_price: float
    discount: float
    net_price: float
    total: float                            # taxable amount for the line (after discount)
    tax_amount: float = 0                   # derived: total x vat_rate
    subtotal_incl_vat: float = 0            # derived: total + tax_amount
    model_config = ConfigDict(from_attributes=True)


# ── Payments ──────────────────────────────────────────────────────────────────

class SalesInvoicePaymentCreate(BaseModel):
    amount: float = Field(gt=0)
    payment_date: Optional[_Date] = None
    method: Literal["bank_transfer", "cash", "cheque", "card", "other"] = "bank_transfer"
    reference: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class SalesInvoicePaymentResponse(BaseModel):
    id: uuid.UUID
    amount: float
    payment_date: _Date
    method: str
    reference: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Invoice ───────────────────────────────────────────────────────────────────

class SalesInvoiceCreate(BaseModel):
    """Request body for creating (or fully replacing a draft) invoice.

    Field groups follow the printed invoice: header references, buyer block,
    terms, line items, notes.
    """

    # Blank → auto-assigned (INV-YYYY-NNNN) when the invoice is confirmed.
    invoice_number: Optional[str] = Field(default=None, max_length=50)

    # Buyer / bill-to
    customer_name: str = Field(min_length=1, max_length=255)
    customer_building_no: Optional[str] = None
    customer_street: Optional[str] = None
    customer_district: Optional[str] = None
    customer_city: Optional[str] = None
    customer_country: Optional[str] = None
    customer_postal_code: Optional[str] = None
    customer_tax_id: Optional[str] = None
    customer_cr_no: Optional[str] = None
    # Internal only — not printed on the PDF; used for "Email invoice".
    email: Optional[str] = None
    contact_person: Optional[str] = None

    # Header references
    delivery_note_no: Optional[str] = None
    delivery_date: Optional[_Date] = None
    your_ref: Optional[str] = None
    vendor_number: Optional[str] = None
    internal_reference: Optional[str] = None
    gr_ses: Optional[str] = None

    # Terms
    currency: str = Field(default="SAR", min_length=3, max_length=3)
    # SAR per 1 unit of `currency`. Omit for SAR (1) / USD (3.75) / AED (1.0211);
    # required for any other currency.
    exchange_rate: Optional[float] = Field(default=None, gt=0)
    invoice_date: Optional[_Date] = None
    due_date: Optional[_Date] = None
    payment_terms: Optional[str] = None
    vat_rate: float = Field(default=15, ge=0, le=100)

    remarks: Optional[str] = None
    sales_order_id: Optional[uuid.UUID] = None

    items: List[SalesInvoiceItemCreate] = Field(min_length=1)


class SalesInvoiceUpdate(SalesInvoiceCreate):
    """Same fields as create; kept separate so the two can diverge."""


class SalesInvoiceSummary(BaseModel):
    """Row shape for the invoice list (no line items / payments)."""

    id: uuid.UUID
    invoice_number: Optional[str] = None
    customer_name: str
    your_ref: Optional[str] = None
    currency: str
    invoice_date: Optional[_Date] = None
    due_date: Optional[_Date] = None
    subtotal: float
    vat: float
    total: float
    amount_paid: float
    balance: float
    status: SalesInvoiceStatus  # raw DB status
    display_status: str         # Draft | Open | Overdue | Paid | Cancelled
    sales_order_number: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SalesInvoiceListResponse(BaseModel):
    items: List[SalesInvoiceSummary]
    total: int
    counts: Dict[str, int]


class SalesInvoiceResponse(BaseModel):
    """Full invoice, including line items and payments."""

    id: uuid.UUID
    invoice_number: Optional[str] = None
    sales_order_id: Optional[uuid.UUID] = None
    sales_order_number: Optional[str] = None

    customer_name: str
    customer_building_no: Optional[str] = None
    customer_street: Optional[str] = None
    customer_district: Optional[str] = None
    customer_city: Optional[str] = None
    customer_country: Optional[str] = None
    customer_postal_code: Optional[str] = None
    customer_tax_id: Optional[str] = None
    customer_cr_no: Optional[str] = None
    email: Optional[str] = None
    contact_person: Optional[str] = None

    delivery_note_no: Optional[str] = None
    delivery_date: Optional[_Date] = None
    your_ref: Optional[str] = None
    vendor_number: Optional[str] = None
    internal_reference: Optional[str] = None
    gr_ses: Optional[str] = None

    currency: str
    exchange_rate: float
    invoice_date: Optional[_Date] = None
    due_date: Optional[_Date] = None
    payment_terms: Optional[str] = None
    vat_rate: float
    subtotal: float          # total excluding VAT, before discount
    discount: float
    taxable_amount: float    # subtotal - discount
    vat: float
    vat_sar: float
    total: float             # total amount due
    total_sar: float
    amount_paid: float
    balance: float

    remarks: Optional[str] = None

    status: SalesInvoiceStatus
    display_status: str
    posted_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_by_id: Optional[uuid.UUID] = None
    created_by_name: Optional[str] = None
    created_by_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    items: List[SalesInvoiceItemResponse] = []
    payments: List[SalesInvoicePaymentResponse] = []
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _fill_line_tax(self):
        """Per-line tax columns, computed once here so API and PDF agree."""
        for it in self.items:
            it.tax_amount = round(it.total * self.vat_rate / 100, 2)
            it.subtotal_incl_vat = round(it.total + it.tax_amount, 2)
        return self


class BankAccountInfo(BaseModel):
    currency: str
    account_name: str = ""
    account_no: str = ""
    swift: str = ""
    bank: str = ""
    branch: str = ""
    iban: str = ""


class SellerProfile(BaseModel):
    """Read-only seller block + bank accounts (from server settings) shown on the form."""

    name: str
    building: str
    street: str
    district: str
    city: str
    country: str
    postal_code: str
    vat_number: str
    cr_no: str
    bank_accounts: List[BankAccountInfo]


class SalesInvoiceKPIs(BaseModel):
    currency: str = "SAR"
    other_currency_invoices: int = 0
    total_invoiced: float
    total_received: float
    total_outstanding: float
    overdue_count: int
    overdue_amount: float
    invoice_count: int
