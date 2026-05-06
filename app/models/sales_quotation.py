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

from sqlalchemy import Date, DateTime, Enum, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import SalesQuotationStatus

if TYPE_CHECKING:
    from app.models.sales_quotation_item import SalesQuotationItem


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

    # ── Commercial terms ──────────────────────────────────────────────────────
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    validity: Mapped[Optional[str]] = mapped_column(String(100))
    delivery_time: Mapped[Optional[str]] = mapped_column(String(100))
    delivery_location: Mapped[Optional[str]] = mapped_column(String(255))
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255))

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

    # ── Notes ─────────────────────────────────────────────────────────────────
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    terms: Mapped[Optional[str]] = mapped_column(Text)

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

    def __repr__(self) -> str:
        return f"<SalesQuotation {self.quote_number} status={self.status} total={self.total}>"
