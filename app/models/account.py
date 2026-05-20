# =============================================================================
# app/models/account.py
# -----------------------------------------------------------------------------
# Chart-of-Accounts entry. Each account has a code, name, type, and a
# running balance. Default accounts are seeded on first startup.
# =============================================================================

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import AuditMixin


class AccountType(str, enum.Enum):
    ASSET     = "Asset"
    LIABILITY = "Liability"
    EQUITY    = "Equity"
    REVENUE   = "Revenue"
    EXPENSE   = "Expense"


class Account(AuditMixin, Base):
    __tablename__ = "accounts"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Account {self.code} – {self.name} ({self.account_type})>"
