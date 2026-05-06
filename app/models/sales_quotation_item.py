# =============================================================================
# app/models/sales_quotation_item.py
# -----------------------------------------------------------------------------
# ORM model for a single line item within a SalesQuotation. Each item stores
# quantity, pricing, and discount; net_price and total are always recomputed
# server-side in the service layer and never trusted from client input.
# =============================================================================

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.sales_quotation import SalesQuotation


class SalesQuotationItem(AuditMixin, Base):
    """A single priced line in a SalesQuotation.

    Table: ``sales_quotation_items``

    Key relationships:
    - ``quotation`` — parent ``SalesQuotation`` (cascade delete on orphan).

    Pricing note:
    ``net_price = unit_price × (1 - discount / 100)``
    ``total     = qty × net_price``
    Both are computed by the service layer; any client-supplied values are
    discarded.
    """

    __tablename__ = "sales_quotation_items"

    # ── Parent reference ──────────────────────────────────────────────────────
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Line details ──────────────────────────────────────────────────────────
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_no: Mapped[Optional[str]] = mapped_column(String(100))
    item_name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # ── Quantity & pricing ────────────────────────────────────────────────────
    qty: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="EA", nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    discount: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    # Server-computed fields (not trusted from client)
    net_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    quotation: Mapped["SalesQuotation"] = relationship(
        "SalesQuotation", back_populates="items"
    )
