"""
RFQ (Request for Quotation) — internal procurement request.
RFQItem — individual line items within an RFQ.

Workflow:
  RFQ (draft) → sent to Suppliers → SupplierQuotes received
             → evaluated → best quote selected → Quotation generated
"""
import uuid
from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Column, Date, Enum, ForeignKey, Numeric, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import RFQStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.rfq_item import RFQItem
    from app.models.quotation import Quotation
    from app.models.document import Document
    from app.models.supplier import Supplier
    from app.models.supplier_quotation import SupplierQuotation
    from app.models.purchase_order import PurchaseOrder


# Association table — RFQ ↔ Supplier (many-to-many)
rfq_suppliers = Table(
    "rfq_suppliers",
    Base.metadata,
    Column("rfq_id", ForeignKey("rfqs.id", ondelete="CASCADE"), primary_key=True),
    Column("supplier_id", ForeignKey("suppliers.id", ondelete="CASCADE"), primary_key=True),
)


class RFQ(AuditMixin, Base):
    """Request for Quotation — kicked off by a purchaser."""

    __tablename__ = "rfqs"

    # ── Reference & status ───────────────────────────────────────────────
    rfq_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str]      = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[RFQStatus] = mapped_column(
        Enum(RFQStatus, name="rfq_status"),
        nullable=False,
        default=RFQStatus.DRAFT,
    )

    # ── Dates ─────────────────────────────────────────────────────────────
    issue_date: Mapped[Optional[date]]    = mapped_column(Date)
    deadline: Mapped[Optional[date]]      = mapped_column(Date)   # supplier response deadline

    # ── Currency ──────────────────────────────────────────────────────────
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    # ── Selected supplier (awarded) ───────────────────────────────────────
    selected_supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── Ownership ─────────────────────────────────────────────────────────
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────
    created_by: Mapped["User"] = relationship(
        "User", back_populates="rfqs", foreign_keys=[created_by_id]
    )
    items: Mapped[List["RFQItem"]] = relationship(
        "RFQItem", back_populates="rfq", cascade="all, delete-orphan"
    )
    suppliers: Mapped[List["Supplier"]] = relationship(
        "Supplier", secondary=rfq_suppliers, lazy="noload"
    )
    selected_supplier: Mapped[Optional["Supplier"]] = relationship(
        "Supplier",
        foreign_keys=[selected_supplier_id],
        lazy="noload",
    )
    quotations: Mapped[List["Quotation"]] = relationship(
        "Quotation", back_populates="rfq"
    )
    supplier_quotations: Mapped[List["SupplierQuotation"]] = relationship(
        "SupplierQuotation", back_populates="rfq", cascade="all, delete-orphan"
    )
    purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(
        "PurchaseOrder", back_populates="rfq"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        primaryjoin="and_(Document.entity_id == foreign(RFQ.id), "
                    "Document.entity_type == 'rfq')",
        viewonly=True,
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<RFQ id={self.id} number={self.rfq_number} status={self.status}>"
