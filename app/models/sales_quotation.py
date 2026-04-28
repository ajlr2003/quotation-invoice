"""
SalesQuotation — commercial offer sent TO a customer via the Quotation Builder.
"""
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, DateTime, Enum, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import SalesQuotationStatus

if TYPE_CHECKING:
    from app.models.sales_quotation_item import SalesQuotationItem


class SalesQuotation(AuditMixin, Base):
    __tablename__ = "sales_quotations"

    quote_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    date: Mapped[Optional[date]] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    validity: Mapped[Optional[str]] = mapped_column(String(100))
    delivery_time: Mapped[Optional[str]] = mapped_column(String(100))
    delivery_location: Mapped[Optional[str]] = mapped_column(String(255))
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255))

    customer_name: Mapped[Optional[str]] = mapped_column(String(255))
    department: Mapped[Optional[str]] = mapped_column(String(255))
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[Optional[str]] = mapped_column(String(500))

    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    vat: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    remarks: Mapped[Optional[str]] = mapped_column(Text)
    terms: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[SalesQuotationStatus] = mapped_column(
        Enum(SalesQuotationStatus, name="sales_quotation_status"),
        default=SalesQuotationStatus.DRAFT,
        nullable=False,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[List["SalesQuotationItem"]] = relationship(
        "SalesQuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="SalesQuotationItem.line_no",
    )

    def __repr__(self) -> str:
        return f"<SalesQuotation {self.quote_number} status={self.status} total={self.total}>"
