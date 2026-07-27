from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.project_task import ProjectTask
    from app.models.project_milestone import ProjectMilestone
    from app.models.time_log import TimeLog


class Project(AuditMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # planning | active | at_risk | completed
    status: Mapped[str] = mapped_column(String(20), default="planning", nullable=False)

    budget: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    budget_spent: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    billable: Mapped[bool] = mapped_column(default=True, nullable=False)

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Manual progress override (0-100). If null, computed from tasks.
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    tasks: Mapped[List["ProjectTask"]] = relationship(
        "ProjectTask", back_populates="project", cascade="all, delete-orphan"
    )
    milestones: Mapped[List["ProjectMilestone"]] = relationship(
        "ProjectMilestone", back_populates="project", cascade="all, delete-orphan"
    )
    time_logs: Mapped[List["TimeLog"]] = relationship(
        "TimeLog", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project {self.name} status={self.status}>"
