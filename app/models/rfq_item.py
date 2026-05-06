# =============================================================================
# app/models/rfq_item.py
# -----------------------------------------------------------------------------
# ORM model for a single line item within an RFQ. Each RFQItem describes what
# is being sourced (product, quantity, optional target price) and can receive
# price responses from multiple suppliers via SupplierQuote records.
# =============================================================================

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.rfq import RFQ
    from app.models.supplier_quote import SupplierQuote


class RFQItem(AuditMixin, Base):
    """A single line item within an RFQ specifying what is being sourced.

    Table: ``rfq_items``

    Key relationships:
    - ``rfq``             — parent RFQ (cascade delete).
    - ``supplier_quotes`` — bids received from suppliers for this specific item.

    The ``best_quote`` property returns the single accepted SupplierQuote for
    this item (at most one may be in ACCEPTED status at a time).
    """

    __tablename__ = "rfq_items"

    # ── Parent ────────────────────────────────────────────────────────────────
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Item details ──────────────────────────────────────────────────────────
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_code: Mapped[Optional[str]] = mapped_column(String(100))
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(50), nullable=False, default="unit")

    # ── Budget / target ───────────────────────────────────────────────────────
    target_unit_price: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # ── Relationships ─────────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="items")
    supplier_quotes: Mapped[List["SupplierQuote"]] = relationship(
        "SupplierQuote", back_populates="rfq_item", cascade="all, delete-orphan"
    )

    @property
    def best_quote(self) -> Optional["SupplierQuote"]:
        """Return the accepted SupplierQuote for this item, if one exists.

        Returns:
            The single ``SupplierQuote`` with status=ACCEPTED, or ``None``.
        """
        from app.models.enums import SupplierQuoteStatus
        accepted = [q for q in self.supplier_quotes if q.status == SupplierQuoteStatus.ACCEPTED]
        return accepted[0] if accepted else None

    def __repr__(self) -> str:
        return (
            f"<RFQItem id={self.id} rfq_id={self.rfq_id} "
            f"line={self.line_number} product={self.product_name}>"
        )
