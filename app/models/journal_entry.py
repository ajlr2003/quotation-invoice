# =============================================================================
# app/models/journal_entry.py
# -----------------------------------------------------------------------------
# Manual journal entry. Each entry records a single debit or credit against
# an account. Lifecycle: draft → posted (posted entries are immutable).
# =============================================================================

from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin

if __name__ == "__main__":  # TYPE_CHECKING guard-free import
    from app.models.account import Account


class JournalEntryStatus(str, enum.Enum):
    DRAFT  = "draft"
    POSTED = "posted"


class JournalEntry(AuditMixin, Base):
    __tablename__ = "journal_entries"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    debit_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    credit_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[JournalEntryStatus] = mapped_column(
        Enum(JournalEntryStatus, name="journal_entry_status"),
        default=JournalEntryStatus.DRAFT,
        nullable=False,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    account: Mapped["Account"] = relationship("Account", lazy="joined")

    def __repr__(self) -> str:
        return f"<JournalEntry {self.reference} {self.status}>"
