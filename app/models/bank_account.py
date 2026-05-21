# =============================================================================
# app/models/bank_account.py
# -----------------------------------------------------------------------------
# Bank account used for reconciliation. Three default accounts are seeded on
# first startup (Main Checking, Savings, Credit Card).
# =============================================================================

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.bank_transaction import BankTransaction


class BankAccountType(str, enum.Enum):
    CHECKING    = "checking"
    SAVINGS     = "savings"
    CREDIT_CARD = "credit_card"


class BankAccount(AuditMixin, Base):
    __tablename__ = "bank_accounts"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[BankAccountType] = mapped_column(
        Enum(BankAccountType, name="bank_account_type"), nullable=False
    )
    current_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    transactions: Mapped[list["BankTransaction"]] = relationship(
        "BankTransaction", back_populates="bank_account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BankAccount {self.name} ({self.account_type})>"
