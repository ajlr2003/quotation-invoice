# =============================================================================
# app/models/sales_invoice.py
# -----------------------------------------------------------------------------
# ORM models for customer (sales) invoices issued by Kytos — the in-house
# replacement for the Odoo-backed invoicing that used to live behind
# /api/v1/odoo. Three tables:
#
#   sales_invoices          — header, totals and lifecycle
#   sales_invoice_items     — priced line items
#   sales_invoice_payments  — manually recorded payments against the invoice
#
# (Not to be confused with PurchaseInvoice, which is the supplier-side bill
# raised from a GRN.)
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import SalesInvoiceStatus

if TYPE_CHECKING:
    from app.models.sales_order import SalesOrder
    from app.models.user import User


class SalesInvoice(AuditMixin, Base):
    """A customer invoice.

    Table: ``sales_invoices``

    Lifecycle (see ``SalesInvoiceStatus``): ``draft`` → ``posted`` → ``paid``
    (or ``cancelled``). The ``invoice_number`` is only assigned when the
    invoice is posted, so drafts never burn a number from the sequence.
    """

    __tablename__ = "sales_invoices"

    # ── Reference ─────────────────────────────────────────────────────────────
    # NULL while the invoice is a draft; assigned sequentially on posting.
    invoice_number: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, nullable=True, index=True
    )
    sales_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sales_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Buyer / bill-to (snapshot — no FK, same as quotations/orders) ─────────
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    customer_building_no: Mapped[Optional[str]] = mapped_column(String(100))
    customer_street: Mapped[Optional[str]] = mapped_column(String(255))
    customer_district: Mapped[Optional[str]] = mapped_column(String(255))
    customer_city: Mapped[Optional[str]] = mapped_column(String(255))
    customer_country: Mapped[Optional[str]] = mapped_column(String(100))
    customer_postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    customer_tax_id: Mapped[Optional[str]] = mapped_column(String(100))   # buyer VAT number
    customer_cr_no: Mapped[Optional[str]] = mapped_column(String(100))     # buyer commercial registration
    # Internal use only — never printed on the PDF (the reference invoice has
    # no email field), used to send the invoice to the customer.
    email: Mapped[Optional[str]] = mapped_column(String(255))
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))

    # ── Invoice references (the header block of the printed invoice) ──────────
    delivery_note_no: Mapped[Optional[str]] = mapped_column(String(255))
    delivery_date: Mapped[Optional[date]] = mapped_column(Date)
    your_ref: Mapped[Optional[str]] = mapped_column(String(255))           # Customer's PO Ref
    vendor_number: Mapped[Optional[str]] = mapped_column(String(100))      # our vendor no. at the customer
    internal_reference: Mapped[Optional[str]] = mapped_column(String(100))
    gr_ses: Mapped[Optional[str]] = mapped_column(String(100))             # goods receipt / service entry sheet

    # ── Terms ─────────────────────────────────────────────────────────────────
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    # SAR per 1 unit of `currency` — printed VAT / total "in SAR" use it.
    exchange_rate: Mapped[float] = mapped_column(Numeric(14, 6), default=1, nullable=False)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date)
    due_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255))

    # ── Financials (recomputed server-side on every save) ─────────────────────
    # subtotal = total excluding VAT *before* discount; taxable = subtotal - discount.
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=15, nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    discount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    vat: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    amount_paid: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    # ── Notes ─────────────────────────────────────────────────────────────────
    remarks: Mapped[Optional[str]] = mapped_column(Text)               # printed as "Notes"

    # ── Status & audit ────────────────────────────────────────────────────────
    status: Mapped[SalesInvoiceStatus] = mapped_column(
        Enum(SalesInvoiceStatus, name="sales_invoice_status"),
        default=SalesInvoiceStatus.DRAFT,
        nullable=False,
        index=True,
    )
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    posted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    items: Mapped[List["SalesInvoiceItem"]] = relationship(
        "SalesInvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="SalesInvoiceItem.line_no",
    )
    payments: Mapped[List["SalesInvoicePayment"]] = relationship(
        "SalesInvoicePayment",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="SalesInvoicePayment.payment_date, SalesInvoicePayment.created_at",
    )
    sales_order: Mapped[Optional["SalesOrder"]] = relationship(
        "SalesOrder", foreign_keys=[sales_order_id], lazy="noload"
    )
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id], lazy="noload"
    )
    posted_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[posted_by_id], lazy="noload"
    )

    # ── Display helpers (need created_by / sales_order eagerly loaded) ────────
    @property
    def balance(self) -> float:
        """Outstanding amount still owed, in the invoice's own currency."""
        return round(float(self.total or 0) - float(self.amount_paid or 0), 2)

    @property
    def taxable_amount(self) -> float:
        """Subtotal net of discount — the base VAT is calculated on."""
        return round(float(self.subtotal or 0) - float(self.discount or 0), 2)

    @property
    def vat_sar(self) -> float:
        """VAT converted to SAR via ``exchange_rate`` — printed for foreign-currency invoices."""
        return round(float(self.vat or 0) * float(self.exchange_rate or 1), 2)

    @property
    def total_sar(self) -> float:
        """Total converted to SAR via ``exchange_rate`` — printed for foreign-currency invoices."""
        return round(float(self.total or 0) * float(self.exchange_rate or 1), 2)

    @property
    def display_status(self) -> str:
        """UI status: Draft | Open | Overdue | Paid | Cancelled.

        "Overdue" is derived, not stored — a posted invoice past its due date.
        """
        if self.status == SalesInvoiceStatus.DRAFT:
            return "Draft"
        if self.status == SalesInvoiceStatus.PAID:
            return "Paid"
        if self.status == SalesInvoiceStatus.CANCELLED:
            return "Cancelled"
        if self.due_date and self.due_date < date.today():
            return "Overdue"
        return "Open"

    @property
    def sales_order_number(self) -> Optional[str]:
        return self.sales_order.order_number if self.sales_order else None

    @property
    def created_by_name(self) -> Optional[str]:
        return self.created_by.full_name if self.created_by else None

    @property
    def created_by_email(self) -> Optional[str]:
        return self.created_by.email if self.created_by else None

    def __repr__(self) -> str:
        return f"<SalesInvoice {self.invoice_number or 'DRAFT'} status={self.status} total={self.total}>"


class SalesInvoiceItem(AuditMixin, Base):
    """A single priced line on a SalesInvoice (``sales_invoice_items``)."""

    __tablename__ = "sales_invoice_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_no: Mapped[Optional[str]] = mapped_column(String(100))
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    qty: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="EA", nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    discount: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    net_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    invoice: Mapped["SalesInvoice"] = relationship("SalesInvoice", back_populates="items")


class SalesInvoicePayment(AuditMixin, Base):
    """A payment recorded against a SalesInvoice (``sales_invoice_payments``)."""

    __tablename__ = "sales_invoice_payments"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    # bank_transfer | cash | cheque | card | other
    method: Mapped[str] = mapped_column(String(30), default="bank_transfer", nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    recorded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    invoice: Mapped["SalesInvoice"] = relationship("SalesInvoice", back_populates="payments")
