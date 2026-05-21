# =============================================================================
# app/models/bank_transaction.py
# -----------------------------------------------------------------------------
# A single row imported from a bank statement CSV. Positive amount = credit
# (money in), negative amount = debit (money out). Reconciled when matched
# to a journal entry.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if TYPE_CHECKING:
    from app.models.bank_account import BankAccount
    from app.models.journal_entry import JournalEntry


class BankTransaction(AuditMixin, Base):
    __tablename__ = "bank_transactions"

    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_reconciled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )

    bank_account: Mapped["BankAccount"] = relationship("BankAccount", back_populates="transactions")
    journal_entry: Mapped["JournalEntry | None"] = relationship("JournalEntry")

    def __repr__(self) -> str:
        return f"<BankTransaction {self.transaction_date} {self.amount}>"
