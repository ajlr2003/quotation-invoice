# =============================================================================
# app/models/purchase_order.py
# -----------------------------------------------------------------------------
# ORM model for a Purchase Order (PO) raised against an awarded RFQ. One PO
# is created per RFQ/supplier pair (unique constraint). The PO tracks ordered
# and received quantities so that its status can be automatically advanced from
# CREATED → PARTIAL → COMPLETED as GRNs are recorded against it.
# =============================================================================

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import PurchaseOrderStatus

if TYPE_CHECKING:
    from app.models.grn import GRN
    from app.models.rfq import RFQ
    from app.models.supplier import Supplier


class PurchaseOrder(AuditMixin, Base):
    """Formal purchase order issued to the winning supplier of an RFQ.

    Table: ``purchase_orders``

    Constraints:
    - At most one PO per RFQ/supplier combination
      (``uq_po_rfq_supplier``).

    Key relationships:
    - ``rfq``      — the RFQ this PO is derived from.
    - ``supplier`` — the vendor the PO is addressed to.
    - ``grns``     — Goods Receipt Notes recorded against this PO (cascade delete).

    Quantity notes:
    - ``ordered_quantity``  — sum of all RFQ item quantities at PO creation time.
    - ``received_quantity`` — running total incremented each time a GRN is created.
    - ``unit_price``        — quotation_total / ordered_quantity (per-unit cost).
    - ``total_price``       — snapshot of the full SupplierQuotation price at creation.
    """

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("rfq_id", "supplier_id", name="uq_po_rfq_supplier"),
    )

    # ── Parents ───────────────────────────────────────────────────────────────
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rfqs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ── Quantity & pricing ────────────────────────────────────────────────────
    ordered_quantity: Mapped[float] = mapped_column(
        Numeric(14, 3), nullable=False, default=0, server_default="0"
    )
    received_quantity: Mapped[float] = mapped_column(
        Numeric(14, 3), nullable=False, default=0, server_default="0"
    )
    unit_price: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    total_price: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )

    # ── Status ────────────────────────────────────────────────────────────────
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        Enum(PurchaseOrderStatus, name="purchase_order_status"),
        nullable=False,
        default=PurchaseOrderStatus.CREATED,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="purchase_orders")
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="purchase_orders")
    grns: Mapped[list["GRN"]] = relationship(
        "GRN", back_populates="purchase_order", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<PurchaseOrder id={self.id} rfq_id={self.rfq_id} "
            f"supplier_id={self.supplier_id} status={self.status}>"
        )
