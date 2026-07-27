# =============================================================================
# app/models/supplier_quotation_item.py
# -----------------------------------------------------------------------------
# Line-item model for a supplier's multi-item bid on an RFQ. Each
# SupplierQuotation may have one or more SupplierQuotationItems.
# =============================================================================

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.supplier_quotation import SupplierQuotation


class SupplierQuotationItem(AuditMixin, Base):
    """A single line item within a supplier's bid on an RFQ.

    Table: ``supplier_quotation_items``
    """

    __tablename__ = "supplier_quotation_items"

    supplier_quotation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("supplier_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), default=1, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    quotation: Mapped["SupplierQuotation"] = relationship(
        "SupplierQuotation", back_populates="items"
    )

    def __repr__(self) -> str:
        return (
            f"<SupplierQuotationItem id={self.id} "
            f"supplier_quotation_id={self.supplier_quotation_id} "
            f"product_name={self.product_name!r} total={self.total}>"
        )
