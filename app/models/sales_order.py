# =============================================================================
# app/models/sales_order.py
# -----------------------------------------------------------------------------
# ORM model for Sales Orders created when an accepted SalesQuotation is
# converted via the "Convert to Order" action. Line items are copied from the
# source quotation at conversion time. The order then progresses through a
# simple fulfillment workflow: confirmed → shipped → delivered.
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
from app.models.enums import SalesOrderStatus

if TYPE_CHECKING:
    from app.models.sales_order_item import SalesOrderItem


class SalesOrder(AuditMixin, Base):
    """Sales Order created from an accepted SalesQuotation.

    Table: ``sales_orders``

    Key relationships:
    - ``items`` — line items (``SalesOrderItem``) copied from the source
      quotation at conversion time; cascade delete on orphan.

    Lifecycle states (see ``SalesOrderStatus``):
    ``confirmed`` → ``shipped`` → ``delivered``  (or ``cancelled``)
    """

    __tablename__ = "sales_orders"

    # ── Reference ─────────────────────────────────────────────────────────────
    order_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    # Optional FK back to the source quotation (SET NULL if quotation is deleted)
    quotation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sales_quotations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Customer contact details (snapshot from quotation at conversion) ───────
    customer_name: Mapped[Optional[str]] = mapped_column(String(255))
    department: Mapped[Optional[str]] = mapped_column(String(255))
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[Optional[str]] = mapped_column(String(500))

    # ── Commercial terms (snapshot from quotation) ─────────────────────────────
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255))
    delivery_location: Mapped[Optional[str]] = mapped_column(String(255))

    # ── Financials (snapshot from quotation at conversion) ─────────────────────
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    vat: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    # ── Notes ─────────────────────────────────────────────────────────────────
    remarks: Mapped[Optional[str]] = mapped_column(Text)

    # ── Status & audit timestamps ──────────────────────────────────────────────
    status: Mapped[SalesOrderStatus] = mapped_column(
        Enum(SalesOrderStatus, name="sales_order_status"),
        default=SalesOrderStatus.CONFIRMED,
        nullable=False,
    )
    shipped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # UUID of the user who last advanced the status (not a FK to keep it lightweight)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    items: Mapped[List["SalesOrderItem"]] = relationship(
        "SalesOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="SalesOrderItem.line_no",
    )

    def __repr__(self) -> str:
        return f"<SalesOrder {self.order_number} status={self.status}>"
