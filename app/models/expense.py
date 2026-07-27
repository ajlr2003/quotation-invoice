from __future__ import annotations

import uuid
from datetime import date as _Date
from typing import Optional

from sqlalchemy import Date, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import AuditMixin


class Expense(AuditMixin, Base):
    """An expense submission — hotel, fuel, food, car rental, etc.

    Anyone in the company can submit. Expenses optionally link to a project.
    Status lifecycle: submitted → approved → reimbursed (or rejected).
    """

    __tablename__ = "expenses"

    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(100))  # Hotel, Fuel, Food, Car Rental, Travel, Other
    amount: Mapped[float] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(10), default="SAR")
    expense_date: Mapped[Optional[_Date]] = mapped_column(Date)

    # Who submitted
    submitted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    submitted_by_name: Mapped[Optional[str]] = mapped_column(String(200))

    # Linked project (free-text for now — can FK to Project later)
    project_name: Mapped[Optional[str]] = mapped_column(String(300))

    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Approval
    status: Mapped[str] = mapped_column(String(50), default="submitted")
    # submitted | approved | rejected | reimbursed

    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
