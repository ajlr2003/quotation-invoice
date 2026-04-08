"""
PurchaseOrder — a formal order raised against a won RFQ.
One purchase order is created per awarded RFQ/supplier pair.
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import PurchaseOrderStatus

if TYPE_CHECKING:
    from app.models.rfq import RFQ
    from app.models.supplier import Supplier


class PurchaseOrder(AuditMixin, Base):
    """
    Formal purchase order issued to the winning supplier of an RFQ.

    Constraints:
    - At most one PO per RFQ/supplier combination.
    """

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("rfq_id", "supplier_id", name="uq_po_rfq_supplier"),
    )

    # ── Parents ───────────────────────────────────────────────────────────
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rfqs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ── Status ────────────────────────────────────────────────────────────
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        Enum(PurchaseOrderStatus, name="purchase_order_status"),
        nullable=False,
        default=PurchaseOrderStatus.CREATED,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="purchase_orders")
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="purchase_orders")

    def __repr__(self) -> str:
        return (
            f"<PurchaseOrder id={self.id} rfq_id={self.rfq_id} "
            f"supplier_id={self.supplier_id} status={self.status}>"
        )
