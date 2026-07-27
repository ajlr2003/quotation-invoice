from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.stock_item import StockItem


class StockMovement(AuditMixin, Base):
    """Records every stock IN or OUT transaction against a StockItem."""

    __tablename__ = "stock_movements"

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stock_items.id", ondelete="CASCADE"), index=True
    )

    # "IN" = material received from supplier; "OUT" = delivered to customer/site
    movement_type: Mapped[str] = mapped_column(String(10))  # "IN" | "OUT"
    quantity: Mapped[int] = mapped_column(Integer)

    # The SO or PO number this movement references
    reference_no: Mapped[Optional[str]] = mapped_column(String(200))

    # Physical delivery note number (required for OUT movements per Noor)
    delivery_note_no: Mapped[Optional[str]] = mapped_column(String(200))

    notes: Mapped[Optional[str]] = mapped_column(Text)

    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    item: Mapped["StockItem"] = relationship("StockItem", back_populates="movements")
