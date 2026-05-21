# =============================================================================
# app/schemas/accounting.py
# -----------------------------------------------------------------------------
# Pydantic v2 request/response schemas for the Accounting module.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.account import AccountType
from app.models.bank_account import BankAccountType
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


# ── Bank Reconciliation ───────────────────────────────────────────────────────

class BankAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    account_type: BankAccountType
    current_balance: float
    last_reconciled_at: Optional[datetime]
    is_active: bool
    reconciliation_status: str   # "reconciled" | "pending" | "overdue"
    unreconciled_count: int = 0


class BankTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bank_account_id: uuid.UUID
    transaction_date: date
    description: str
    amount: float
    reference: Optional[str]
    notes: Optional[str]
    is_reconciled: bool
    journal_entry_id: Optional[uuid.UUID]
    created_at: datetime


class BankTransactionListResponse(BaseModel):
    items: List[BankTransactionResponse]
    total: int
    unreconciled: int


class ReconcileRequest(BaseModel):
    transaction_ids: List[uuid.UUID]
    journal_entry_id: Optional[uuid.UUID] = None


# ── Close Period ─────────────────────────────────────────────────────────────

class ClosePeriodRequest(BaseModel):
    year: int
    month: int
    notes: Optional[str] = None


class ClosedPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    year: int
    month: int
    notes: Optional[str]
    created_at: datetime


class ClosePeriodPreview(BaseModel):
    year: int
    month: int
    draft_entries: int
    posted_entries: int
    unreconciled_transactions: int
    net_balance: float
    already_closed: bool


# ── Financial Reports ─────────────────────────────────────────────────────────

class ReportLineItem(BaseModel):
    account_code: str
    account_name: str
    debit: float
    credit: float
    balance: float


class ProfitLossReport(BaseModel):
    period_label: str
    revenue_items: List[ReportLineItem]
    expense_items: List[ReportLineItem]
    total_revenue: float
    total_expenses: float
    net_income: float


class BalanceSheetReport(BaseModel):
    as_of: str
    asset_items: List[ReportLineItem]
    liability_items: List[ReportLineItem]
    equity_items: List[ReportLineItem]
    total_assets: float
    total_liabilities: float
    total_equity: float
    net_income: float
    liabilities_and_equity: float


class TrialBalanceReport(BaseModel):
    as_of: str
    items: List[ReportLineItem]
    total_debits: float
    total_credits: float
    is_balanced: bool


class CashFlowReport(BaseModel):
    period_label: str
    inflows: List[ReportLineItem]
    outflows: List[ReportLineItem]
    total_inflows: float
    total_outflows: float
    net_cash_flow: float
