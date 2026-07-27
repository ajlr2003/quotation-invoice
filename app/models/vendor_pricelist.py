# =============================================================================
# app/models/vendor_pricelist.py
# -----------------------------------------------------------------------------
# A price quoted by a specific supplier for a specific product (or generically
# for the vendor if no product is picked) — mirrors Odoo's Vendor Pricelist
# (product.supplierinfo). Used by Purchasing to know which vendor offers a
# product, at what price/quantity break, and for how long that price holds.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date as _Date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.stock_item import StockItem
    from app.models.supplier import Supplier


class VendorPricelist(AuditMixin, Base):
    """One vendor/product price entry.

    Table: ``vendor_pricelists``

    ``stock_item_id`` is optional — a pricelist row may describe a vendor's
    general pricing (e.g. a catalog code / lead time) without pinning it to
    one internal product yet.
    """

    __tablename__ = "vendor_pricelists"

    # ── Vendor ────────────────────────────────────────────────────────────────
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_product_name: Mapped[Optional[str]] = mapped_column(String(255))
    vendor_product_code: Mapped[Optional[str]] = mapped_column(String(100))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # ── Pricelist ─────────────────────────────────────────────────────────────
    stock_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("stock_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(14, 2), default=1, server_default="1")
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    valid_from: Mapped[Optional[_Date]] = mapped_column(Date)
    valid_to: Mapped[Optional[_Date]] = mapped_column(Date)
    discount_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0, server_default="0")

    # ── Relationships ─────────────────────────────────────────────────────────
    supplier: Mapped["Supplier"] = relationship("Supplier", lazy="noload")
    stock_item: Mapped[Optional["StockItem"]] = relationship("StockItem", lazy="noload")

    def __repr__(self) -> str:
        return f"<VendorPricelist supplier_id={self.supplier_id} unit_price={self.unit_price}>"
