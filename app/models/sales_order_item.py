# =============================================================================
# app/models/sales_order_item.py
# -----------------------------------------------------------------------------
# ORM model for a single line item within a SalesOrder. Items are copied
# verbatim from SalesQuotationItem rows at the moment a quotation is converted
# to an order and are never modified after that point.
# =============================================================================

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.sales_order import SalesOrder


class SalesOrderItem(AuditMixin, Base):
    """A single priced line in a SalesOrder, copied from the source quotation.

    Table: ``sales_order_items``

    Key relationships:
    - ``order`` — parent ``SalesOrder`` (cascade delete on orphan).

    Pricing columns are stored as snapshots from the quotation and are never
    recalculated after order creation.
    """

    __tablename__ = "sales_order_items"

    # ── Parent reference ──────────────────────────────────────────────────────
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Line details ──────────────────────────────────────────────────────────
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_no: Mapped[Optional[str]] = mapped_column(String(100))
    item_name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # ── Quantity & pricing (snapshot from quotation at conversion) ─────────────
    qty: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="EA", nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    discount: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    net_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    order: Mapped["SalesOrder"] = relationship("SalesOrder", back_populates="items")
