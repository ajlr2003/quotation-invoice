"""
SalesOrder — created from an accepted SalesQuotation via "Convert to Order".
"""
import uuid
from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import SalesOrderStatus

if TYPE_CHECKING:
    from app.models.sales_order_item import SalesOrderItem


class SalesOrder(AuditMixin, Base):
    __tablename__ = "sales_orders"

    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    quotation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sales_quotations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    customer_name: Mapped[Optional[str]] = mapped_column(String(255))
    department: Mapped[Optional[str]] = mapped_column(String(255))
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255))
    delivery_location: Mapped[Optional[str]] = mapped_column(String(255))

    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    vat: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    remarks: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[SalesOrderStatus] = mapped_column(
        Enum(SalesOrderStatus, name="sales_order_status"),
        default=SalesOrderStatus.CONFIRMED,
        nullable=False,
    )

    items: Mapped[List["SalesOrderItem"]] = relationship(
        "SalesOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="SalesOrderItem.line_no",
    )

    def __repr__(self) -> str:
        return f"<SalesOrder {self.order_number} status={self.status}>"
