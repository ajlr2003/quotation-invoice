"""
Customer — external companies or individuals that receive Quotations.
"""
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.quotation import Quotation


class Customer(AuditMixin, Base):
    """External customer that receives quotations and (eventually) invoices."""

    __tablename__ = "customers"

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
    tax_id: Mapped[Optional[str]]         = mapped_column(String(100))
    payment_terms_days: Mapped[int]       = mapped_column(default=30, nullable=False)
    credit_limit: Mapped[Optional[float]]

    # ── Status ────────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # ── Relationships ─────────────────────────────────────────────────────
    quotations: Mapped[List["Quotation"]] = relationship(
        "Quotation", back_populates="customer"
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.id} company={self.company_name}>"
