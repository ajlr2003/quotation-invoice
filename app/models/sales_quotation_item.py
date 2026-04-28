"""
SalesQuotationItem — a single line in a SalesQuotation.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.sales_quotation import SalesQuotation


class SalesQuotationItem(AuditMixin, Base):
    __tablename__ = "sales_quotation_items"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_no: Mapped[Optional[str]] = mapped_column(String(100))
    item_name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    qty: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="EA", nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    discount: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    net_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    quotation: Mapped["SalesQuotation"] = relationship("SalesQuotation", back_populates="items")
