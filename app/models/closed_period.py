# =============================================================================
# app/models/closed_period.py
# -----------------------------------------------------------------------------
# Represents a locked accounting period (year + month). Once a period is
# closed, new journal entries dated within it are rejected.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import AuditMixin


class ClosedPeriod(AuditMixin, Base):
    __tablename__ = "closed_periods"
    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_closed_period_year_month"),
    )

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<ClosedPeriod {self.year}-{self.month:02d}>"
