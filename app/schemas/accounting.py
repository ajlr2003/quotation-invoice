# =============================================================================
# app/schemas/accounting.py
# -----------------------------------------------------------------------------
# Pydantic v2 request/response schemas for the Accounting module:
# KPI summary, Chart of Accounts, and Journal Entries.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.account import AccountType
from app.models.journal_entry import JournalEntryStatus


# ── KPI ───────────────────────────────────────────────────────────────────────

class AccountingKPIResponse(BaseModel):
    total_accounts: int
    active_accounts: int
    entries_this_month: int
    entries_total: int
    total_debits_posted: float
    total_credits_posted: float
    draft_entries: int
    posted_entries: int


# ── Chart of Accounts ─────────────────────────────────────────────────────────

class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    account_type: AccountType
    description: Optional[str]
    balance: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AccountCreate(BaseModel):
    code: str
    name: str
    account_type: AccountType
    description: Optional[str] = None
    balance: float = 0.0


class AccountListResponse(BaseModel):
    items: List[AccountResponse]
    total: int


# ── Journal Entries ───────────────────────────────────────────────────────────

class JournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    entry_date: date
    description: str
    debit_amount: float
    credit_amount: float
    notes: Optional[str]
    status: JournalEntryStatus
    account_id: Optional[uuid.UUID]
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JournalEntryCreate(BaseModel):
    entry_date: date
    description: str
    debit_amount: float = 0.0
    credit_amount: float = 0.0
    notes: Optional[str] = None
    account_id: Optional[uuid.UUID] = None


class JournalEntryListResponse(BaseModel):
    items: List[JournalEntryResponse]
    total: int
