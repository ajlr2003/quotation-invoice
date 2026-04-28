"""
app/models/grn.py
Goods Receipt Note — records physical receipt of goods against a PO.
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.purchase_order import PurchaseOrder


class GRN(AuditMixin, Base):
    """Goods Receipt Note issued when goods are received against a Purchase Order."""

    __tablename__ = "grns"

    # ── Parent ────────────────────────────────────────────────────────────
    po_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Quantity received ─────────────────────────────────────────────────
    received_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────
    purchase_order: Mapped["PurchaseOrder"] = relationship(
        "PurchaseOrder", back_populates="grns"
    )

    def __repr__(self) -> str:
        return (
            f"<GRN id={self.id} po_id={self.po_id} "
            f"received_quantity={self.received_quantity}>"
        )
