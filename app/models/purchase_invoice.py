"""
app/models/purchase_invoice.py
PurchaseInvoice — a supplier invoice raised from a Goods Receipt Note.

Workflow:
  GRN created → Invoice drafted → approved → paid

Rules:
- One invoice per GRN (unique constraint on grn_id).
- total_amount is computed at creation: GRN.received_quantity * PO.unit_price.
- Status transitions: draft → approved → paid.
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import PurchaseInvoiceStatus

if TYPE_CHECKING:
    from app.models.grn import GRN
    from app.models.purchase_order import PurchaseOrder
    from app.models.supplier import Supplier


class PurchaseInvoice(AuditMixin, Base):
    """
    Supplier-side invoice generated from a GRN.

    Constraints:
    - At most one invoice per GRN.
    """

    __tablename__ = "purchase_invoices"
    __table_args__ = (
        UniqueConstraint("grn_id", name="uq_purchase_invoice_grn"),
    )

    # ── Parents ───────────────────────────────────────────────────────────
    po_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    grn_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("grns.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Financials ────────────────────────────────────────────────────────
    # unit_price: snapshot of PO.unit_price at invoice creation time
    # total_amount: received_quantity * unit_price
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    # ── Status ────────────────────────────────────────────────────────────
    status: Mapped[PurchaseInvoiceStatus] = mapped_column(
        Enum(PurchaseInvoiceStatus, name="purchase_invoice_status"),
        nullable=False,
        default=PurchaseInvoiceStatus.DRAFT,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder")
    grn: Mapped["GRN"] = relationship("GRN")
    supplier: Mapped["Supplier"] = relationship("Supplier")

    def __repr__(self) -> str:
        return (
            f"<PurchaseInvoice id={self.id} grn_id={self.grn_id} "
            f"total={self.total_amount} status={self.status}>"
        )
