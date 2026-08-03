from __future__ import annotations

from typing import Optional

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import AuditMixin


class AppSettings(AuditMixin, Base):
    """Single-row table of app-wide default settings.

    Only one row is ever expected to exist — general_settings_service
    creates it on first read if missing, then always updates that same
    row. Simpler than a real key-value settings store since the set of
    tunable defaults is small and known ahead of time.
    """

    __tablename__ = "app_settings"

    default_currency: Mapped[str] = mapped_column(String(10), default="SAR")
    default_payment_terms: Mapped[Optional[str]] = mapped_column(String(100), default="Net 30")
    default_tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=15)
