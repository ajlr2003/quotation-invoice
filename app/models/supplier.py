"""
Supplier — vendors that respond to RFQs with SupplierQuotes.
"""
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.supplier_quote import SupplierQuote


class Supplier(AuditMixin, Base):
    """Vendor that bids on RFQ line items via SupplierQuotes."""

    __tablename__ = "suppliers"

    # ── Identity ─────────────────────────────────────────────────────────
    company_name: Mapped[str]            = mapped_column(String(255), nullable=False, index=True)
    contact_name: Mapped[Optional[str]]  = mapped_column(String(255))
    email: Mapped[str]                   = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[Optional[str]]         = mapped_column(String(50))

    # ── Address ───────────────────────────────────────────────────────────
    address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    address_line2: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]]          = mapped_column(String(100))
    state: Mapped[Optional[str]]         = mapped_column(String(100))
    postal_code: Mapped[Optional[str]]   = mapped_column(String(20))
    country: Mapped[Optional[str]]       = mapped_column(String(100))

    # ── Finance ───────────────────────────────────────────────────────────
    tax_id: Mapped[Optional[str]]          = mapped_column(String(100))
    payment_terms_days: Mapped[int]        = mapped_column(default=30, nullable=False)
    currency: Mapped[str]                  = mapped_column(String(3), default="USD", nullable=False)
    bank_details: Mapped[Optional[str]]    = mapped_column(Text)

    # ── Evaluation ────────────────────────────────────────────────────────
    rating: Mapped[Optional[float]]        # 0.0 – 5.0
    is_preferred: Mapped[bool]             = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool]                = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]]           = mapped_column(Text)

    # ── Relationships ─────────────────────────────────────────────────────
    quotes: Mapped[List["SupplierQuote"]] = relationship(
        "SupplierQuote", back_populates="supplier"
    )

    def __repr__(self) -> str:
        return f"<Supplier id={self.id} company={self.company_name}>"
