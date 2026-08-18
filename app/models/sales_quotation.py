# =============================================================================
# app/models/sales_quotation.py
# -----------------------------------------------------------------------------
# ORM model for outbound Sales Quotations created via the Quotation Builder.
# A SalesQuotation progresses through draft → sent → accepted/rejected →
# converted, at which point a SalesOrder is generated from it.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import SalesQuotationStatus

if TYPE_CHECKING:
    from app.models.sales_quotation_item import SalesQuotationItem
    from app.models.rfq import RFQ
    from app.models.customer_rfq import CustomerRFQ
    from app.models.user import User


class SalesQuotation(AuditMixin, Base):
    """Commercial offer sent to a customer via the Quotation Builder.

    Table: ``sales_quotations``

    Key relationships:
    - ``items`` — line items (``SalesQuotationItem``) with cascade delete.

    Lifecycle states (see ``SalesQuotationStatus``):
    ``draft`` → ``sent`` → ``accepted`` / ``rejected`` → ``converted``
    """

    __tablename__ = "sales_quotations"

    # ── Reference & dates ─────────────────────────────────────────────────────
    quote_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    date: Mapped[Optional[date]] = mapped_column(Date)
    delivery_date: Mapped[Optional[date]] = mapped_column(Date)

    # ── Commercial terms ──────────────────────────────────────────────────────
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    validity: Mapped[Optional[str]] = mapped_column(String(100))
    delivery_time: Mapped[Optional[str]] = mapped_column(String(100))
    delivery_location: Mapped[Optional[str]] = mapped_column(String(255))
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255))
    invoice_address: Mapped[Optional[str]] = mapped_column(Text)
    delivery_address: Mapped[Optional[str]] = mapped_column(Text)

    # ── Customer contact details (denormalised — no FK to customers table) ────
    customer_name: Mapped[Optional[str]] = mapped_column(String(255))
    department: Mapped[Optional[str]] = mapped_column(String(255))
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    fax: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    cc: Mapped[Optional[str]] = mapped_column(String(500))      # CC recipients
    your_ref: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[Optional[str]] = mapped_column(String(500))

    # ── Financials (denormalised totals recomputed on every save) ─────────────
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    vat: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    # ── CRM link (optional — links this quote to a CRM lead/opportunity) ──────
    crm_lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("crm_leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── RFQ link (optional — traces this quote back to the outbound RFQ WE
    # sent a supplier to source pricing, so the quote_number can be
    # auto-derived as "QT" + rfq_number) ───────────────────────────────────
    rfq_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rfqs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Customer RFQ link (optional — traces this quote back to the request
    # the CUSTOMER sent us, distinct from rfq_id above) ────────────────────
    customer_rfq_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customer_rfqs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Who created / approved this quotation (displayed on the record) ──────
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Notes ─────────────────────────────────────────────────────────────────
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    terms: Mapped[Optional[str]] = mapped_column(Text)

    # ── Tracker fields (mirrors the team's existing quotation tracker) ────────
    oem: Mapped[Optional[str]] = mapped_column(String(200))
    date_received: Mapped[Optional[date]] = mapped_column(Date)
    deadline: Mapped[Optional[date]] = mapped_column(Date)
    follow_up_date: Mapped[Optional[date]] = mapped_column(Date)
    outcome: Mapped[Optional[str]] = mapped_column(String(100))

    # ── Status & audit timestamps ──────────────────────────────────────────────
    status: Mapped[SalesQuotationStatus] = mapped_column(
        Enum(SalesQuotationStatus, name="sales_quotation_status"),
        default=SalesQuotationStatus.DRAFT,
        nullable=False,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # UUID of the user who last changed the status (not a FK to keep it lightweight)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    items: Mapped[List["SalesQuotationItem"]] = relationship(
        "SalesQuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="SalesQuotationItem.line_no",
    )
    rfq: Mapped[Optional["RFQ"]] = relationship("RFQ", foreign_keys=[rfq_id], lazy="noload")
    customer_rfq: Mapped[Optional["CustomerRFQ"]] = relationship(
        "CustomerRFQ", foreign_keys=[customer_rfq_id], lazy="noload"
    )
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id], lazy="noload"
    )
    approved_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[approved_by_id], lazy="noload"
    )

    # ── Denormalised display helpers (require ``rfq``/``created_by``/
    # ``approved_by`` to be eagerly loaded — see selectinload() in the
    # service layer to avoid lazy-load errors under async sessions) ──────────
    @property
    def rfq_number(self) -> Optional[str]:
        return self.rfq.rfq_number if self.rfq else None

    @property
    def customer_reference(self) -> Optional[str]:
        return self.rfq.customer_reference if self.rfq else None

    @property
    def created_by_name(self) -> Optional[str]:
        return self.created_by.full_name if self.created_by else None

    @property
    def approved_by_name(self) -> Optional[str]:
        return self.approved_by.full_name if self.approved_by else None

    def __repr__(self) -> str:
        return f"<SalesQuotation {self.quote_number} status={self.status} total={self.total}>"
