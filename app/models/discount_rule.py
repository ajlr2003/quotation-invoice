from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import AuditMixin


class DiscountRule(AuditMixin, Base):
    """A configurable discount rule shown to sales staff when quoting.

    Rules are informational guidance surfaced in the Sales Quotation
    Builder — e.g. "orders above SAR 50,000 get 10-25% off". They are not
    automatically applied to a quotation's total; staff use them as a
    reference when entering a discount manually.
    """

    __tablename__ = "discount_rules"

    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[Optional[str]] = mapped_column(Text)  # e.g. "Orders above SAR 50,000"
    discount_label: Mapped[str] = mapped_column(String(50))   # e.g. "10-25%" or "15%"
    min_order_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
