# =============================================================================
# app/routers/accounting.py
# -----------------------------------------------------------------------------
# FastAPI route handlers for the Accounting module.
# All routes are mounted under /api/v1/accounting by app/main.py.
#
# Endpoint summary:
#   GET  /kpis                                  — dashboard KPI snapshot
#   GET  /accounts                              — list chart of accounts
#   POST /accounts                              — create a new account
#   GET  /journal-entries                       — list recent journal entries
#   POST /journal-entries                       — create a draft journal entry
#   POST /journal-entries/{id}/post             — post a draft entry (finalise)
#   GET  /bank-accounts                         — list bank accounts with status
#   GET  /bank-accounts/{id}/transactions       — list transactions for an account
#   POST /bank-accounts/{id}/import             — import CSV bank statement
#   POST /bank-accounts/{id}/reconcile          — mark transactions as reconciled
#   GET  /close-period/preview                  — preview period close summary
#   POST /close-period                          — lock an accounting period
#   GET  /closed-periods                        — list all locked periods
#   GET  /reports/profit-loss                   — Profit & Loss report
#   GET  /reports/balance-sheet                 — Balance Sheet report
#   GET  /reports/trial-balance                 — Trial Balance report
#   GET  /reports/cash-flow                     — Cash Flow report
#
# All routes require a valid Bearer JWT (get_current_user dependency).
# =============================================================================

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.accounting import (
    AccountCreate,
    AccountingKPIResponse,
    AccountListResponse,
    AccountResponse,
    BalanceSheetReport,
    BankAccountResponse,
    BankTransactionListResponse,
    CashFlowReport,
    ClosedPeriodResponse,
    ClosePeriodPreview,
    ClosePeriodRequest,
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
    ProfitLossReport,
    ReconcileRequest,
    TrialBalanceReport,
)
from app.services import accounting_service

router = APIRouter()


# =============================================================================
# KPIs
# =============================================================================

@router.get(
    "/kpis",
    response_model=AccountingKPIResponse,
    summary="Accounting dashboard KPIs",
    description=(
        "Returns a snapshot of key accounting metrics: active account count, "
        "journal entry counts (this month / all-time / draft / posted), and "
        "total debits/credits from posted entries."
    ),
)
async def get_kpis(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.get_kpis(db)


# =============================================================================
# Chart of Accounts
# =============================================================================

@router.get(
    "/accounts",
    response_model=AccountListResponse,
    summary="List all accounts",
    description="Returns the full chart of accounts ordered by account code.",
)
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.list_accounts(db)


@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=201,
    summary="Create a new account",
    description=(
        "Adds a new account to the chart of accounts. "
        "Account codes must be unique — returns 409 if the code already exists."
    ),
)
async def create_account(
    payload: AccountCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.create_account(db, payload)


# =============================================================================
# Journal Entries
# =============================================================================

@router.get(
    "/journal-entries",
    response_model=JournalEntryListResponse,
    summary="List journal entries",
    description="Returns the most recent journal entries ordered by date descending. Use `limit` to control page size.",
)
async def list_journal_entries(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.list_journal_entries(db, limit=limit)


@router.post(
    "/journal-entries",
    response_model=JournalEntryResponse,
    status_code=201,
    summary="Create a journal entry",
    description=(
        "Creates a new journal entry in DRAFT status. "
        "Returns 400 if both debit and credit are zero. "
        "Returns 409 if the entry date falls within a closed period."
    ),
)
async def create_journal_entry(
    payload: JournalEntryCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.create_journal_entry(db, payload)


@router.post(
    "/journal-entries/{entry_id}/post",
    response_model=JournalEntryResponse,
    summary="Post a draft journal entry",
    description=(
        "Transitions a DRAFT entry to POSTED status, updating the linked "
        "account balance using standard double-entry accounting rules. "
        "Returns 409 if the entry is already posted or the period is closed."
    ),
)
async def post_journal_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.post_journal_entry(db, entry_id)


# =============================================================================
# Bank Reconciliation
# =============================================================================

@router.get(
    "/bank-accounts",
    response_model=list[BankAccountResponse],
    summary="List bank accounts",
    description=(
        "Returns all active bank accounts with their current balance, "
        "last reconciliation date, unreconciled transaction count, "
        "and a computed reconciliation status (reconciled / pending / overdue)."
    ),
)
async def list_bank_accounts(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.list_bank_accounts(db)


@router.get(
    "/bank-accounts/{bank_account_id}/transactions",
    response_model=BankTransactionListResponse,
    summary="List transactions for a bank account",
    description="Returns all imported bank transactions for the given account, ordered by date descending.",
)
async def get_bank_transactions(
    bank_account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.get_bank_transactions(db, bank_account_id)


@router.post(
    "/bank-accounts/{bank_account_id}/import",
    summary="Import a CSV bank statement",
    description=(
        "Parses an uploaded CSV file and creates BankTransaction records. "
        "Auto-detects column format: Date/Description/Amount or Date/Description/Debit/Credit. "
        "Returns 400 if the file does not contain a recognisable Date column. "
        "Returns a count of imported and skipped rows."
    ),
)
async def import_bank_statement(
    bank_account_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.import_bank_statement(db, bank_account_id, file)


@router.post(
    "/bank-accounts/{bank_account_id}/reconcile",
    summary="Reconcile bank transactions",
    description=(
        "Marks the specified transactions as reconciled and updates the "
        "bank account's last_reconciled_at timestamp. "
        "Pass an empty transaction_ids list to update the reconciliation date only."
    ),
)
async def reconcile_transactions(
    bank_account_id: uuid.UUID,
    payload: ReconcileRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.reconcile_transactions(db, bank_account_id, payload)


# =============================================================================
# Period Closing
# =============================================================================

@router.get(
    "/close-period/preview",
    response_model=ClosePeriodPreview,
    summary="Preview period close",
    description=(
        "Returns a summary for the given year/month before closing: "
        "posted entry count, draft entry count, unreconciled transactions, "
        "net balance, and whether the period is already closed."
    ),
)
async def close_period_preview(
    year: int = Query(..., description="4-digit year, e.g. 2026"),
    month: int = Query(..., ge=1, le=12, description="Month number 1–12"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.get_close_period_preview(db, year, month)


@router.post(
    "/close-period",
    response_model=ClosedPeriodResponse,
    status_code=201,
    summary="Close an accounting period",
    description=(
        "Locks the specified month/year so that no new journal entries can be "
        "created for dates within that period. This action cannot be undone. "
        "Returns 409 if the period is already closed."
    ),
)
async def close_period(
    payload: ClosePeriodRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await accounting_service.close_period(db, payload, user_id=current_user.id)


@router.get(
    "/closed-periods",
    response_model=list[ClosedPeriodResponse],
    summary="List all closed periods",
    description="Returns all locked accounting periods ordered by year and month descending.",
)
async def list_closed_periods(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.list_closed_periods(db)


# =============================================================================
# Financial Reports
# =============================================================================

@router.get(
    "/reports/profit-loss",
    response_model=ProfitLossReport,
    summary="Profit & Loss report",
    description=(
        "Returns year-to-date revenue and expense totals derived from posted "
        "journal entries, grouped by account. Net income = total revenue − total expenses."
    ),
)
async def report_profit_loss(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.get_profit_loss(db)


@router.get(
    "/reports/balance-sheet",
    response_model=BalanceSheetReport,
    summary="Balance Sheet report",
    description=(
        "Returns a snapshot of assets, liabilities, and equity as of today. "
        "Liabilities + Equity + Net Income should equal Total Assets."
    ),
)
async def report_balance_sheet(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.get_balance_sheet(db)


@router.get(
    "/reports/trial-balance",
    response_model=TrialBalanceReport,
    summary="Trial Balance report",
    description=(
        "Returns total debits and credits from all posted journal entries "
        "across all accounts. is_balanced=true confirms the ledger is in balance."
    ),
)
async def report_trial_balance(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.get_trial_balance(db)


@router.get(
    "/reports/cash-flow",
    response_model=CashFlowReport,
    summary="Cash Flow report",
    description=(
        "Returns cash inflows (positive bank transactions) and outflows "
        "(negative bank transactions) year-to-date. Requires bank statement "
        "data to have been imported via the /import endpoint."
    ),
)
async def report_cash_flow(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.get_cash_flow(db)
