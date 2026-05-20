# =============================================================================
# app/services/accounting_service.py
# -----------------------------------------------------------------------------
# Business logic for the Accounting module:
#   - KPI derivation from existing sales/purchase data
#   - Chart of Accounts CRUD
#   - Journal Entry CRUD with auto-generated reference numbers
# =============================================================================

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.journal_entry import JournalEntry, JournalEntryStatus
from app.schemas.accounting import (
    AccountCreate,
    AccountingKPIResponse,
    AccountListResponse,
    AccountResponse,
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
)


# ── Default chart-of-accounts seeded on first startup ────────────────────────

_DEFAULT_ACCOUNTS = [
    ("1000", "Cash",                    AccountType.ASSET,     "Primary checking account",    0.0),
    ("1200", "Accounts Receivable",     AccountType.ASSET,     "Customer invoices outstanding", 0.0),
    ("1500", "Inventory",               AccountType.ASSET,     "Stock of goods held for sale", 0.0),
    ("2000", "Accounts Payable",        AccountType.LIABILITY, "Vendor bills outstanding",     0.0),
    ("2100", "Accrued Liabilities",     AccountType.LIABILITY, "Accrued but unpaid expenses",  0.0),
    ("3000", "Owner Equity",            AccountType.EQUITY,    "Retained earnings",             0.0),
    ("4000", "Revenue",                 AccountType.REVENUE,   "Sales income",                  0.0),
    ("5000", "Cost of Goods Sold",      AccountType.EXPENSE,   "Direct product costs",          0.0),
    ("6000", "Operating Expenses",      AccountType.EXPENSE,   "General & administrative",      0.0),
    ("6100", "Salaries & Wages",        AccountType.EXPENSE,   "Employee compensation",         0.0),
]


async def seed_default_accounts(db: AsyncSession) -> None:
    """Insert default chart-of-accounts rows if the table is empty."""
    count = (await db.execute(select(func.count()).select_from(Account))).scalar_one()
    if count > 0:
        return
    for code, name, atype, desc, bal in _DEFAULT_ACCOUNTS:
        db.add(Account(code=code, name=name, account_type=atype, description=desc, balance=bal))
    await db.commit()


# ── KPI ───────────────────────────────────────────────────────────────────────

async def get_kpis(db: AsyncSession) -> AccountingKPIResponse:
    """KPIs derived purely from the chart of accounts and journal entries."""
    now = datetime.now(timezone.utc)

    total_accounts  = (await db.execute(select(func.count()).select_from(Account))).scalar_one()
    active_accounts = (await db.execute(
        select(func.count()).select_from(Account).where(Account.is_active == True)
    )).scalar_one()

    entries_total = (await db.execute(select(func.count()).select_from(JournalEntry))).scalar_one()

    entries_this_month = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(
            func.extract("year",  JournalEntry.created_at) == now.year,
            func.extract("month", JournalEntry.created_at) == now.month,
        )
    )).scalar_one()

    draft_entries = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(
            JournalEntry.status == JournalEntryStatus.DRAFT
        )
    )).scalar_one()

    posted_entries = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(
            JournalEntry.status == JournalEntryStatus.POSTED
        )
    )).scalar_one()

    total_debits_posted = (await db.execute(
        select(func.coalesce(func.sum(JournalEntry.debit_amount), 0)).where(
            JournalEntry.status == JournalEntryStatus.POSTED
        )
    )).scalar_one()

    total_credits_posted = (await db.execute(
        select(func.coalesce(func.sum(JournalEntry.credit_amount), 0)).where(
            JournalEntry.status == JournalEntryStatus.POSTED
        )
    )).scalar_one()

    return AccountingKPIResponse(
        total_accounts=total_accounts,
        active_accounts=active_accounts,
        entries_this_month=entries_this_month,
        entries_total=entries_total,
        total_debits_posted=round(float(total_debits_posted), 2),
        total_credits_posted=round(float(total_credits_posted), 2),
        draft_entries=draft_entries,
        posted_entries=posted_entries,
    )


# ── Chart of Accounts ─────────────────────────────────────────────────────────

async def list_accounts(db: AsyncSession) -> AccountListResponse:
    rows = (await db.execute(
        select(Account).order_by(Account.code)
    )).scalars().all()
    items = [AccountResponse.model_validate(r) for r in rows]
    return AccountListResponse(items=items, total=len(items))


async def create_account(db: AsyncSession, payload: AccountCreate) -> AccountResponse:
    existing = (await db.execute(
        select(Account).where(Account.code == payload.code)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Account code '{payload.code}' already exists",
        )
    acct = Account(**payload.model_dump())
    db.add(acct)
    await db.commit()
    await db.refresh(acct)
    return AccountResponse.model_validate(acct)


# ── Journal Entries ───────────────────────────────────────────────────────────

async def _next_reference(db: AsyncSession) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"JE-{year}-"
    count = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(
            JournalEntry.reference.like(f"{prefix}%")
        )
    )).scalar_one()
    return f"{prefix}{(count + 1):03d}"


async def list_journal_entries(db: AsyncSession, limit: int = 20) -> JournalEntryListResponse:
    rows = (await db.execute(
        select(JournalEntry)
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
        .limit(limit)
    )).scalars().all()
    items = [_je_to_response(r) for r in rows]
    total = (await db.execute(select(func.count()).select_from(JournalEntry))).scalar_one()
    return JournalEntryListResponse(items=items, total=total)


async def create_journal_entry(db: AsyncSession, payload: JournalEntryCreate) -> JournalEntryResponse:
    if payload.debit_amount == 0 and payload.credit_amount == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Journal entry must have a non-zero debit or credit amount",
        )
    ref = await _next_reference(db)
    entry = JournalEntry(
        reference=ref,
        entry_date=payload.entry_date,
        description=payload.description,
        debit_amount=payload.debit_amount,
        credit_amount=payload.credit_amount,
        notes=payload.notes,
        account_id=payload.account_id,
        status=JournalEntryStatus.DRAFT,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _je_to_response(entry)


async def post_journal_entry(db: AsyncSession, entry_id) -> JournalEntryResponse:
    entry = (await db.execute(
        select(JournalEntry).where(JournalEntry.id == entry_id)
    )).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if entry.status == JournalEntryStatus.POSTED:
        raise HTTPException(status_code=409, detail="Entry is already posted")
    entry.status = JournalEntryStatus.POSTED
    await db.commit()
    await db.refresh(entry)
    return _je_to_response(entry)


def _je_to_response(entry: JournalEntry) -> JournalEntryResponse:
    return JournalEntryResponse(
        id=entry.id,
        reference=entry.reference,
        entry_date=entry.entry_date,
        description=entry.description,
        debit_amount=float(entry.debit_amount),
        credit_amount=float(entry.credit_amount),
        notes=entry.notes,
        status=entry.status,
        account_id=entry.account_id,
        account_code=entry.account.code if entry.account else None,
        account_name=entry.account.name if entry.account else None,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )
