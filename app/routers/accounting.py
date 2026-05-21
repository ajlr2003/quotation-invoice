# =============================================================================
# app/routers/accounting.py
# -----------------------------------------------------------------------------
# GET  /kpis
# GET/POST /accounts
# GET/POST /journal-entries
# POST /journal-entries/{id}/post
# GET  /bank-accounts
# GET  /bank-accounts/{id}/transactions
# POST /bank-accounts/{id}/import          — CSV upload
# POST /bank-accounts/{id}/reconcile
# GET  /close-period/preview?year=&month=
# POST /close-period
# GET  /closed-periods
# GET  /reports/profit-loss
# GET  /reports/balance-sheet
# GET  /reports/trial-balance
# GET  /reports/cash-flow
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


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis", response_model=AccountingKPIResponse)
async def get_kpis(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.get_kpis(db)


# ── Chart of Accounts ─────────────────────────────────────────────────────────

@router.get("/accounts", response_model=AccountListResponse)
async def list_accounts(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.list_accounts(db)


@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(payload: AccountCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.create_account(db, payload)


# ── Journal Entries ───────────────────────────────────────────────────────────

@router.get("/journal-entries", response_model=JournalEntryListResponse)
async def list_journal_entries(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.list_journal_entries(db, limit=limit)


@router.post("/journal-entries", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(payload: JournalEntryCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.create_journal_entry(db, payload)


@router.post("/journal-entries/{entry_id}/post", response_model=JournalEntryResponse)
async def post_journal_entry(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.post_journal_entry(db, entry_id)


# ── Bank Reconciliation ───────────────────────────────────────────────────────

@router.get("/bank-accounts", response_model=list[BankAccountResponse])
async def list_bank_accounts(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.list_bank_accounts(db)


@router.get("/bank-accounts/{bank_account_id}/transactions", response_model=BankTransactionListResponse)
async def get_bank_transactions(bank_account_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.get_bank_transactions(db, bank_account_id)


@router.post("/bank-accounts/{bank_account_id}/import")
async def import_bank_statement(
    bank_account_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.import_bank_statement(db, bank_account_id, file)


@router.post("/bank-accounts/{bank_account_id}/reconcile")
async def reconcile_transactions(
    bank_account_id: uuid.UUID,
    payload: ReconcileRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.reconcile_transactions(db, bank_account_id, payload)


# ── Close Period ─────────────────────────────────────────────────────────────

@router.get("/close-period/preview", response_model=ClosePeriodPreview)
async def close_period_preview(
    year: int = Query(...),
    month: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await accounting_service.get_close_period_preview(db, year, month)


@router.post("/close-period", response_model=ClosedPeriodResponse, status_code=201)
async def close_period(
    payload: ClosePeriodRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await accounting_service.close_period(db, payload, user_id=current_user.get("id"))


@router.get("/closed-periods", response_model=list[ClosedPeriodResponse])
async def list_closed_periods(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.list_closed_periods(db)


# ── Financial Reports ─────────────────────────────────────────────────────────

@router.get("/reports/profit-loss", response_model=ProfitLossReport)
async def report_profit_loss(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.get_profit_loss(db)


@router.get("/reports/balance-sheet", response_model=BalanceSheetReport)
async def report_balance_sheet(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.get_balance_sheet(db)


@router.get("/reports/trial-balance", response_model=TrialBalanceReport)
async def report_trial_balance(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.get_trial_balance(db)


@router.get("/reports/cash-flow", response_model=CashFlowReport)
async def report_cash_flow(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await accounting_service.get_cash_flow(db)
