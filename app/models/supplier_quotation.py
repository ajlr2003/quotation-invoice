# =============================================================================
# app/models/supplier_quotation.py
# -----------------------------------------------------------------------------
# ORM model for a Supplier's top-level bid on an entire RFQ. This is distinct
# from SupplierQuote which operates at the individual RFQ line-item level.
# One supplier may submit at most one SupplierQuotation per RFQ (enforced by
# a unique constraint on rfq_id + supplier_id).
# =============================================================================

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.rfq import RFQ
    from app.models.supplier import Supplier


class SupplierQuotation(AuditMixin, Base):
    """A supplier's price offer for an RFQ as a whole (single unit price).

    Table: ``supplier_quotations``

    Constraints:
    - One quotation per supplier per RFQ
      (``uq_supplier_quotation_rfq_supplier``).

    Key relationships:
    - ``rfq``      — the RFQ this quotation responds to.
    - ``supplier`` — the vendor who submitted this bid.
    """

    __tablename__ = "supplier_quotations"
    __table_args__ = (
        UniqueConstraint(
            "rfq_id", "supplier_id", name="uq_supplier_quotation_rfq_supplier"
        ),
    )

    # ── Parents ───────────────────────────────────────────────────────────────
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ── Quote details ─────────────────────────────────────────────────────────
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # ── Relationships ─────────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="supplier_quotations")
    supplier: Mapped["Supplier"] = relationship(
        "Supplier", back_populates="supplier_quotations"
    )

    def __repr__(self) -> str:
        return (
            f"<SupplierQuotation id={self.id} rfq_id={self.rfq_id} "
            f"supplier_id={self.supplier_id} unit_price={self.unit_price}>"
        )
