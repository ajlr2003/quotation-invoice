# =============================================================================
# app/models/supplier_quote.py
# -----------------------------------------------------------------------------
# ORM model for a Supplier's price response to a single RFQItem. Multiple
# suppliers can quote on the same RFQ line item; at most one quote per item
# may be in ACCEPTED status (enforced at the service layer). A unique
# constraint prevents the same supplier from quoting twice on the same item.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import SupplierQuoteStatus

if TYPE_CHECKING:
    from app.models.supplier import Supplier
    from app.models.rfq_item import RFQItem
    from app.models.document import Document


class SupplierQuote(AuditMixin, Base):
    """A single supplier's bid for one RFQ line item.

    Table: ``supplier_quotes``

    Constraints:
    - A supplier can submit at most one quote per RFQ item
      (``uq_supplier_quote_item_supplier``).
    - Only one quote per RFQ item may have status=ACCEPTED
      (enforced by the service layer, not the DB).

    Key relationships:
    - ``rfq_item`` — the RFQItem being priced.
    - ``supplier`` — the vendor who submitted this quote.

    The ``total_price`` property computes ``unit_price × quantity_available``
    as a convenience for comparison views.
    """

    __tablename__ = "supplier_quotes"
    __table_args__ = (
        UniqueConstraint(
            "rfq_item_id", "supplier_id", name="uq_supplier_quote_item_supplier"
        ),
    )

    # ── Parents ───────────────────────────────────────────────────────────────
    rfq_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rfq_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ── Quote details ─────────────────────────────────────────────────────────
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    quantity_available: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    lead_time_days: Mapped[Optional[int]]
    valid_until: Mapped[Optional[date]] = mapped_column(Date)
    delivery_terms: Mapped[Optional[str]] = mapped_column(String(255))
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # ── Status ────────────────────────────────────────────────────────────────
    status: Mapped[SupplierQuoteStatus] = mapped_column(
        Enum(SupplierQuoteStatus, name="supplier_quote_status"),
        nullable=False,
        default=SupplierQuoteStatus.PENDING,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)

    # ── Relationships ─────────────────────────────────────────────────────────
    rfq_item: Mapped["RFQItem"] = relationship("RFQItem", back_populates="supplier_quotes")
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="quotes")

    @property
    def total_price(self) -> float:
        """Convenience total: ``unit_price × quantity_available``.

        Returns:
            The product of unit price and available quantity, or 0.0 if
            ``quantity_available`` is not set.
        """
        qty = self.quantity_available or 0
        return float(self.unit_price) * float(qty)

    def __repr__(self) -> str:
        return (
            f"<SupplierQuote id={self.id} supplier_id={self.supplier_id} "
            f"unit_price={self.unit_price} status={self.status}>"
        )
