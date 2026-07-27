from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.project import Project


class TimeLog(AuditMixin, Base):
    __tablename__ = "time_logs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logged_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="time_logs")

    def __repr__(self) -> str:
        return f"<TimeLog project={self.project_id} hours={self.hours}>"
