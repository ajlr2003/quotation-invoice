# =============================================================================
# app/models/quotation.py
# -----------------------------------------------------------------------------
# ORM model for outbound Quotations sent to Customers. A Quotation is
# typically sourced from an RFQ and progresses through an approval workflow
# before being sent. It may also reference Document attachments and Approval
# records via generic entity_id / entity_type joins.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import QuotationStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.customer import Customer
    from app.models.rfq import RFQ
    from app.models.quotation_item import QuotationItem
    from app.models.approval import Approval
    from app.models.document import Document


class Quotation(AuditMixin, Base):
    """Commercial quotation sent to a Customer, optionally sourced from an RFQ.

    Table: ``quotations``

    Lifecycle:
      ``draft`` → ``pending_approval`` → ``approved`` → ``sent``
               → ``accepted`` / ``rejected`` → ``converted``

    Key relationships:
    - ``customer``  — the Customer this quotation is addressed to.
    - ``rfq``       — optional source RFQ (may be None for ad-hoc quotes).
    - ``created_by``— User who authored the quotation.
    - ``items``     — priced line items (``QuotationItem``) with cascade delete.
    - ``approvals`` — viewonly Approval records linked via generic entity join.
    - ``documents`` — viewonly Document records linked via generic entity join.
    """

    __tablename__ = "quotations"

    # ── Reference & status ────────────────────────────────────────────────────
    quotation_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[QuotationStatus] = mapped_column(
        Enum(QuotationStatus, name="quotation_status"),
        nullable=False,
        default=QuotationStatus.DRAFT,
    )

    # ── Dates ─────────────────────────────────────────────────────────────────
    issue_date: Mapped[Optional[date]] = mapped_column(Date)
    valid_until: Mapped[Optional[date]] = mapped_column(Date)

    # ── Currency & totals (denormalised for fast reads) ───────────────────────
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    discount_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    tax_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    # ── Terms ─────────────────────────────────────────────────────────────────
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255))
    delivery_terms: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text)   # not shown to customer

    # ── Customer rejection ────────────────────────────────────────────────────
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)

    # ── Foreign keys ──────────────────────────────────────────────────────────
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rfq_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("rfqs.id", ondelete="SET NULL"), index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    customer: Mapped["Customer"] = relationship("Customer", back_populates="quotations")
    rfq: Mapped[Optional["RFQ"]] = relationship("RFQ", back_populates="quotations")
    created_by: Mapped["User"] = relationship(
        "User", back_populates="quotations", foreign_keys=[created_by_id]
    )
    items: Mapped[List["QuotationItem"]] = relationship(
        "QuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="QuotationItem.line_number",
    )
    # Viewonly joins via generic entity_id / entity_type pattern
    approvals: Mapped[List["Approval"]] = relationship(
        "Approval",
        primaryjoin="and_(Approval.entity_id == foreign(Quotation.id), "
                    "Approval.entity_type == 'quotation')",
        viewonly=True,
        lazy="select",
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        primaryjoin="and_(Document.entity_id == foreign(Quotation.id), "
                    "Document.entity_type == 'quotation')",
        viewonly=True,
        lazy="select",
    )

    def recalculate_totals(self) -> None:
        """Re-derive subtotal, discount, tax, and total from current line items.

        Iterates over ``self.items`` (must be loaded) and recomputes all
        denormalised financial columns in place.  Should be called whenever
        items are added, removed, or modified.
        """
        self.subtotal = sum(float(i.line_total) for i in self.items)
        self.discount_amount = round(self.subtotal * float(self.discount_percent) / 100, 2)
        taxable = self.subtotal - self.discount_amount
        self.tax_amount = round(taxable * float(self.tax_percent) / 100, 2)
        self.total_amount = round(taxable + self.tax_amount, 2)

    def __repr__(self) -> str:
        return (
            f"<Quotation id={self.id} number={self.quotation_number} "
            f"status={self.status} total={self.total_amount}>"
        )
