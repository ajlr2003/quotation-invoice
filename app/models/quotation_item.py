"""
QuotationItem — a priced line item inside a Quotation.
Optionally references the RFQItem + accepted SupplierQuote it was sourced from.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.quotation import Quotation
    from app.models.rfq_item import RFQItem
    from app.models.supplier_quote import SupplierQuote


class QuotationItem(AuditMixin, Base):
    """Priced line item within a Quotation."""

    __tablename__ = "quotation_items"

    # ── Parent ────────────────────────────────────────────────────────────
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Source traceability ───────────────────────────────────────────────
    rfq_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("rfq_items.id", ondelete="SET NULL"), index=True
    )
    supplier_quote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("supplier_quotes.id", ondelete="SET NULL"), index=True
    )

    # ── Item details ─────────────────────────────────────────────────────
    line_number: Mapped[int]           = mapped_column(Integer, nullable=False)
    product_code: Mapped[Optional[str]] = mapped_column(String(100))
    product_name: Mapped[str]           = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]]  = mapped_column(Text)
    quantity: Mapped[float]             = mapped_column(Numeric(12, 3), nullable=False)
    unit_of_measure: Mapped[str]        = mapped_column(String(50), default="unit", nullable=False)

    # ── Pricing ───────────────────────────────────────────────────────────
    unit_price: Mapped[float]           = mapped_column(Numeric(14, 4), nullable=False)
    cost_price: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))  # internal cost
    discount_percent: Mapped[float]     = mapped_column(Numeric(5, 2), default=0, nullable=False)
    tax_percent: Mapped[float]          = mapped_column(Numeric(5, 2), default=0, nullable=False)
    line_total: Mapped[float]           = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[Optional[str]]        = mapped_column(Text)

    # ── Relationships ─────────────────────────────────────────────────────
    quotation: Mapped["Quotation"]               = relationship("Quotation", back_populates="items")
    rfq_item: Mapped[Optional["RFQItem"]]        = relationship("RFQItem")
    supplier_quote: Mapped[Optional["SupplierQuote"]] = relationship("SupplierQuote")

    def calculate_line_total(self) -> float:
        """Compute line total: qty × unit_price × (1 - discount%) × (1 + tax%)."""
        gross = float(self.quantity) * float(self.unit_price)
        after_discount = gross * (1 - float(self.discount_percent) / 100)
        after_tax = after_discount * (1 + float(self.tax_percent) / 100)
        self.line_total = round(after_tax, 2)
        return self.line_total

    @property
    def margin_percent(self) -> Optional[float]:
        """Gross margin as a percentage (requires cost_price)."""
        if self.cost_price and self.unit_price:
            return round((float(self.unit_price) - float(self.cost_price))
                         / float(self.unit_price) * 100, 2)
        return None

    def __repr__(self) -> str:
        return (
            f"<QuotationItem id={self.id} line={self.line_number} "
            f"product={self.product_name} total={self.line_total}>"
        )
