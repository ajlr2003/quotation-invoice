from __future__ import annotations

import uuid
from datetime import date as _Date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, Numeric, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.stock_movement import StockMovement


class StockItem(AuditMixin, Base):
    """One row in the warehouse permanent stock list.

    Mirrors the columns from Kytos Arabia's Excel stock sheet:
    W.Location / Box# / Supplier-MFG / Part No. / Serial No. /
    Description / Expiry / Qty / Received File No. / PO No. / Unit Price / Status
    """

    __tablename__ = "stock_items"

    # ── Location ──────────────────────────────────────────────────────────────
    warehouse_location: Mapped[Optional[str]] = mapped_column(String(100))
    box_number: Mapped[Optional[str]] = mapped_column(String(20))

    # ── Supplier / item identity ───────────────────────────────────────────────
    supplier_manufacturer: Mapped[Optional[str]] = mapped_column(String(200))
    part_number: Mapped[str] = mapped_column(String(200), index=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    expiry_date: Mapped[Optional[_Date]] = mapped_column(Date)

    # ── Quantities ────────────────────────────────────────────────────────────
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)

    # ── Reference numbers ─────────────────────────────────────────────────────
    received_file_no: Mapped[Optional[str]] = mapped_column(String(200))
    po_number: Mapped[Optional[str]] = mapped_column(String(200))

    # ── Pricing ───────────────────────────────────────────────────────────────
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))

    # ── Status / delivery notes ───────────────────────────────────────────────
    # Free-text field (e.g. "202401156-23759; PO 17087" or "KAUST")
    receiving_delivery_status: Mapped[Optional[str]] = mapped_column(Text)

    # ── Customer reservation ──────────────────────────────────────────────────
    # When Noor separates items for a specific customer on receipt
    customer_name: Mapped[Optional[str]] = mapped_column(String(300))

    # ── Photo ─────────────────────────────────────────────────────────────────
    # Download path of a Document uploaded via /api/v1/documents/upload
    # (e.g. "/api/v1/documents/{id}/download").
    image_url: Mapped[Optional[str]] = mapped_column(String(500))

    # ── Relationships ─────────────────────────────────────────────────────────
    movements: Mapped[List["StockMovement"]] = relationship(
        "StockMovement", back_populates="item", cascade="all, delete-orphan"
    )
