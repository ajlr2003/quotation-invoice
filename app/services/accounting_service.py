# =============================================================================
# app/services/accounting_service.py
# -----------------------------------------------------------------------------
# Business logic for the full Accounting module:
#   - KPIs from ledger/journal data
#   - Chart of Accounts CRUD (with balance updates on journal post)
#   - Journal Entry CRUD + post (updates account balances)
#   - Bank Reconciliation (accounts, CSV import, reconcile transactions)
#   - Period closing with validation
#   - Financial Reports: P&L, Balance Sheet, Trial Balance, Cash Flow
# =============================================================================

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from typing import List

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account, AccountType
from app.models.bank_account import BankAccount, BankAccountType
from app.models.bank_transaction import BankTransaction
from app.models.closed_period import ClosedPeriod
from app.models.journal_entry import JournalEntry, JournalEntryStatus
from app.schemas.accounting import (
    AccountCreate,
    AccountingKPIResponse,
    AccountListResponse,
    AccountResponse,
    BalanceSheetReport,
    BankAccountResponse,
    BankTransactionListResponse,
    BankTransactionResponse,
    CashFlowReport,
    ClosedPeriodResponse,
    ClosePeriodPreview,
    ClosePeriodRequest,
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
    ProfitLossReport,
    ReconcileRequest,
    ReportLineItem,
    TrialBalanceReport,
)


# ── Seed helpers ──────────────────────────────────────────────────────────────

_DEFAULT_ACCOUNTS = [
    ("1000", "Cash",                    AccountType.ASSET,     "Primary checking account"),
    ("1200", "Accounts Receivable",     AccountType.ASSET,     "Customer invoices outstanding"),
    ("1500", "Inventory",               AccountType.ASSET,     "Stock of goods held for sale"),
    ("2000", "Accounts Payable",        AccountType.LIABILITY, "Vendor bills outstanding"),
    ("2100", "Accrued Liabilities",     AccountType.LIABILITY, "Accrued but unpaid expenses"),
    ("3000", "Owner Equity",            AccountType.EQUITY,    "Retained earnings"),
    ("4000", "Revenue",                 AccountType.REVENUE,   "Sales income"),
    ("5000", "Cost of Goods Sold",      AccountType.EXPENSE,   "Direct product costs"),
    ("6000", "Operating Expenses",      AccountType.EXPENSE,   "General & administrative"),
    ("6100", "Salaries & Wages",        AccountType.EXPENSE,   "Employee compensation"),
]

_DEFAULT_BANK_ACCOUNTS = [
    ("Main Checking",  BankAccountType.CHECKING),
    ("Savings Account", BankAccountType.SAVINGS),
    ("Credit Card",    BankAccountType.CREDIT_CARD),
]


async def seed_default_accounts(db: AsyncSession) -> None:
    """Seed chart of accounts and bank accounts on first startup.

    Runs only when the respective tables are empty, making it safe to call
    on every application start without duplicating records.
    """
    count = (await db.execute(select(func.count()).select_from(Account))).scalar_one()
    if count == 0:
        for code, name, atype, desc in _DEFAULT_ACCOUNTS:
            db.add(Account(code=code, name=name, account_type=atype, description=desc, balance=0.0))
        await db.commit()

    bank_count = (await db.execute(select(func.count()).select_from(BankAccount))).scalar_one()
    if bank_count == 0:
        for name, atype in _DEFAULT_BANK_ACCOUNTS:
            db.add(BankAccount(name=name, account_type=atype, current_balance=0.0))
        await db.commit()


# ── KPI ───────────────────────────────────────────────────────────────────────

async def get_kpis(db: AsyncSession) -> AccountingKPIResponse:
    """Compute and return the accounting dashboard KPI snapshot.

    Executes 8 aggregation queries in sequence to produce counts and sums
    that power the 4 KPI cards on the frontend dashboard.
    """
    now = datetime.now(timezone.utc)

    total_accounts  = (await db.execute(select(func.count()).select_from(Account))).scalar_one()
    active_accounts = (await db.execute(
        select(func.count()).select_from(Account).where(Account.is_active == True)
    )).scalar_one()
    entries_total   = (await db.execute(select(func.count()).select_from(JournalEntry))).scalar_one()
    entries_this_month = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(
            func.extract("year",  JournalEntry.created_at) == now.year,
            func.extract("month", JournalEntry.created_at) == now.month,
        )
    )).scalar_one()
    draft_entries  = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(JournalEntry.status == JournalEntryStatus.DRAFT)
    )).scalar_one()
    posted_entries = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(JournalEntry.status == JournalEntryStatus.POSTED)
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
    """Return all accounts ordered by account code ascending."""
    rows = (await db.execute(select(Account).order_by(Account.code))).scalars().all()
    return AccountListResponse(
        items=[AccountResponse.model_validate(r) for r in rows],
        total=len(rows),
    )


async def create_account(db: AsyncSession, payload: AccountCreate) -> AccountResponse:
    """Create a new account in the chart of accounts.

    Raises:
        HTTPException 409: If an account with the same code already exists.
    """
    if (await db.execute(select(Account).where(Account.code == payload.code))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Account code '{payload.code}' already exists")
    acct = Account(**payload.model_dump())
    db.add(acct)
    await db.commit()
    await db.refresh(acct)
    return AccountResponse.model_validate(acct)


# ── Journal Entries ───────────────────────────────────────────────────────────

async def _next_reference(db: AsyncSession) -> str:
    """Generate the next sequential journal entry reference for the current year.

    Format: JE-YYYY-NNN (e.g. JE-2026-001). The counter resets each calendar year.
    """
    year   = datetime.now(timezone.utc).year
    prefix = f"JE-{year}-"
    count  = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(JournalEntry.reference.like(f"{prefix}%"))
    )).scalar_one()
    return f"{prefix}{(count + 1):03d}"


async def _assert_period_open(db: AsyncSession, entry_date: date) -> None:
    """Guard that the accounting period for entry_date has not been closed.

    Raises:
        HTTPException 409: If a ClosedPeriod record exists for the same year/month.
    """
    closed = (await db.execute(
        select(ClosedPeriod).where(
            ClosedPeriod.year  == entry_date.year,
            ClosedPeriod.month == entry_date.month,
        )
    )).scalar_one_or_none()
    if closed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Period {entry_date.year}-{entry_date.month:02d} is closed. Cannot create entries.",
        )


async def list_journal_entries(db: AsyncSession, limit: int = 20) -> JournalEntryListResponse:
    """Return the most recent journal entries ordered by entry date descending."""
    rows  = (await db.execute(
        select(JournalEntry)
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
        .limit(limit)
    )).scalars().all()
    total = (await db.execute(select(func.count()).select_from(JournalEntry))).scalar_one()
    return JournalEntryListResponse(items=[_je_to_response(r) for r in rows], total=total)


async def create_journal_entry(db: AsyncSession, payload: JournalEntryCreate) -> JournalEntryResponse:
    """Create a new journal entry in DRAFT status.

    Validates that the amount is non-zero and the period is open before
    persisting. A sequential reference (JE-YYYY-NNN) is auto-assigned.

    Raises:
        HTTPException 400: If both debit and credit amounts are zero.
        HTTPException 409: If the entry date falls within a closed period.
    """
    if payload.debit_amount == 0 and payload.credit_amount == 0:
        raise HTTPException(status_code=400, detail="Entry must have a non-zero debit or credit amount")
    await _assert_period_open(db, payload.entry_date)
    ref   = await _next_reference(db)
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
    """Finalise a DRAFT journal entry by transitioning it to POSTED status.

    Updates the linked account's balance using standard double-entry rules
    (debit increases Assets/Expenses; credit increases Liabilities/Equity/Revenue).

    Raises:
        HTTPException 404: If the entry does not exist.
        HTTPException 409: If the entry is already posted or the period is closed.
    """
    entry = (await db.execute(
        select(JournalEntry).where(JournalEntry.id == entry_id)
    )).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if entry.status == JournalEntryStatus.POSTED:
        raise HTTPException(status_code=409, detail="Entry is already posted")

    await _assert_period_open(db, entry.entry_date)

    # Update account balance using standard double-entry rules
    if entry.account_id:
        account = (await db.execute(
            select(Account).where(Account.id == entry.account_id)
        )).scalar_one_or_none()
        if account:
            _apply_balance(account, float(entry.debit_amount), float(entry.credit_amount))

    entry.status = JournalEntryStatus.POSTED
    await db.commit()
    await db.refresh(entry)
    return _je_to_response(entry)


def _apply_balance(account: Account, debit: float, credit: float) -> None:
    """Apply debit/credit to account balance per standard accounting rules."""
    if account.account_type in (AccountType.ASSET, AccountType.EXPENSE):
        # Normal debit balance: debit increases, credit decreases
        account.balance = float(account.balance) + debit - credit
    else:
        # Normal credit balance (Liability, Equity, Revenue): credit increases, debit decreases
        account.balance = float(account.balance) + credit - debit


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


# ── Bank Reconciliation ───────────────────────────────────────────────────────

def _reconciliation_status(bank: BankAccount) -> str:
    """Derive reconciliation status from the number of days since last reconciliation.

    Returns:
        "reconciled" — reconciled within the last 31 days
        "pending"    — 32–62 days since last reconciliation
        "overdue"    — never reconciled or more than 62 days ago
    """
    if bank.last_reconciled_at is None:
        return "overdue"
    now   = datetime.now(timezone.utc)
    delta = (now - bank.last_reconciled_at).days
    if delta <= 31:
        return "reconciled"
    if delta <= 62:
        return "pending"
    return "overdue"


async def list_bank_accounts(db: AsyncSession) -> list[BankAccountResponse]:
    """Return all active bank accounts with reconciliation status and unreconciled count."""
    banks = (await db.execute(
        select(BankAccount).where(BankAccount.is_active == True).order_by(BankAccount.name)
    )).scalars().all()

    result = []
    for b in banks:
        unreconciled = (await db.execute(
            select(func.count()).select_from(BankTransaction).where(
                BankTransaction.bank_account_id == b.id,
                BankTransaction.is_reconciled == False,
            )
        )).scalar_one()
        result.append(BankAccountResponse(
            id=b.id,
            name=b.name,
            account_type=b.account_type,
            current_balance=float(b.current_balance),
            last_reconciled_at=b.last_reconciled_at,
            is_active=b.is_active,
            reconciliation_status=_reconciliation_status(b),
            unreconciled_count=unreconciled,
        ))
    return result


async def get_bank_transactions(db: AsyncSession, bank_account_id) -> BankTransactionListResponse:
    """Return all transactions for a bank account ordered by date descending."""
    rows = (await db.execute(
        select(BankTransaction)
        .where(BankTransaction.bank_account_id == bank_account_id)
        .order_by(BankTransaction.transaction_date.desc())
    )).scalars().all()
    unreconciled = sum(1 for r in rows if not r.is_reconciled)
    return BankTransactionListResponse(
        items=[BankTransactionResponse.model_validate(r) for r in rows],
        total=len(rows),
        unreconciled=unreconciled,
    )


async def import_bank_statement(
    db: AsyncSession, bank_account_id, file: UploadFile
) -> dict:
    """Parse a CSV bank statement and create BankTransaction records.

    Supported CSV formats (auto-detected from headers):
      - Date, Description, Amount          (positive=credit, negative=debit)
      - Date, Description, Debit, Credit   (separate columns)
      - Date, Narration, Withdrawals, Deposits (common bank export format)
    """
    bank = (await db.execute(
        select(BankAccount).where(BankAccount.id == bank_account_id)
    )).scalar_one_or_none()
    if bank is None:
        raise HTTPException(status_code=404, detail="Bank account not found")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader  = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]

    if "date" not in headers and "transaction date" not in headers:
        raise HTTPException(
            status_code=400,
            detail="Invalid CSV: must contain a 'Date' column. Supported formats: Date/Description/Amount or Date/Description/Debit/Credit.",
        )

    created  = 0
    skipped  = 0

    # Detect format
    has_debit_credit = any(h in headers for h in ("debit", "withdrawals", "withdrawal"))

    for row in reader:
        row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
        try:
            # ── Parse date ────────────────────────────────────────────────────
            raw_date = row.get("date") or row.get("transaction date") or ""
            if not raw_date:
                skipped += 1; continue
            txn_date = _parse_date(raw_date)

            # ── Parse amount ──────────────────────────────────────────────────
            if has_debit_credit:
                debit_val  = _parse_amount(row.get("debit") or row.get("withdrawals") or row.get("withdrawal") or "0")
                credit_val = _parse_amount(row.get("credit") or row.get("deposits") or row.get("deposit") or "0")
                amount = credit_val - debit_val
            else:
                amount = _parse_amount(row.get("amount") or "0")

            desc = (
                row.get("description") or row.get("narration") or
                row.get("particulars") or row.get("memo") or "Import"
            )[:255]
            ref = row.get("reference") or row.get("ref") or row.get("cheque") or None

            db.add(BankTransaction(
                bank_account_id=bank_account_id,
                transaction_date=txn_date,
                description=desc,
                amount=amount,
                reference=ref[:80] if ref else None,
                is_reconciled=False,
            ))
            # Update running balance
            bank.current_balance = float(bank.current_balance) + amount
            created += 1

        except (ValueError, KeyError):
            skipped += 1
            continue

    await db.commit()
    return {"imported": created, "skipped": skipped, "bank_account": bank.name}


def _parse_date(s: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")


def _parse_amount(s: str) -> float:
    cleaned = s.replace(",", "").replace(" ", "").replace("(", "-").replace(")", "")
    return float(cleaned) if cleaned else 0.0


async def reconcile_transactions(
    db: AsyncSession, bank_account_id, payload: ReconcileRequest
) -> dict:
    """Mark the specified transactions as reconciled and update the bank account timestamp.

    Passing an empty transaction_ids list is valid — it still updates
    last_reconciled_at, which resets the reconciliation status to "reconciled".

    Raises:
        HTTPException 404: If the bank account does not exist.

    Returns:
        dict with key "reconciled" — count of transactions updated.
    """
    bank = (await db.execute(
        select(BankAccount).where(BankAccount.id == bank_account_id)
    )).scalar_one_or_none()
    if bank is None:
        raise HTTPException(status_code=404, detail="Bank account not found")

    rows = (await db.execute(
        select(BankTransaction).where(
            BankTransaction.id.in_(payload.transaction_ids),
            BankTransaction.bank_account_id == bank_account_id,
        )
    )).scalars().all()

    for txn in rows:
        txn.is_reconciled = True
        if payload.journal_entry_id:
            txn.journal_entry_id = payload.journal_entry_id

    bank.last_reconciled_at = datetime.now(timezone.utc)
    await db.commit()
    return {"reconciled": len(rows)}


# ── Close Period ─────────────────────────────────────────────────────────────

async def get_close_period_preview(db: AsyncSession, year: int, month: int) -> ClosePeriodPreview:
    """Return a pre-close summary for the given year/month without making any changes.

    Provides the accountant with a checklist before committing to a period close:
    posted entry count, open draft count, unreconciled bank transactions,
    net balance, and whether the period is already closed.
    """
    already_closed = (await db.execute(
        select(ClosedPeriod).where(ClosedPeriod.year == year, ClosedPeriod.month == month)
    )).scalar_one_or_none() is not None

    draft_entries = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(
            JournalEntry.status == JournalEntryStatus.DRAFT,
            func.extract("year",  JournalEntry.entry_date) == year,
            func.extract("month", JournalEntry.entry_date) == month,
        )
    )).scalar_one()

    posted_entries = (await db.execute(
        select(func.count()).select_from(JournalEntry).where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            func.extract("year",  JournalEntry.entry_date) == year,
            func.extract("month", JournalEntry.entry_date) == month,
        )
    )).scalar_one()

    unreconciled = (await db.execute(
        select(func.count()).select_from(BankTransaction).where(
            BankTransaction.is_reconciled == False,
            func.extract("year",  BankTransaction.transaction_date) == year,
            func.extract("month", BankTransaction.transaction_date) == month,
        )
    )).scalar_one()

    debits = (await db.execute(
        select(func.coalesce(func.sum(JournalEntry.debit_amount), 0)).where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            func.extract("year",  JournalEntry.entry_date) == year,
            func.extract("month", JournalEntry.entry_date) == month,
        )
    )).scalar_one()

    credits = (await db.execute(
        select(func.coalesce(func.sum(JournalEntry.credit_amount), 0)).where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            func.extract("year",  JournalEntry.entry_date) == year,
            func.extract("month", JournalEntry.entry_date) == month,
        )
    )).scalar_one()

    return ClosePeriodPreview(
        year=year,
        month=month,
        draft_entries=draft_entries,
        posted_entries=posted_entries,
        unreconciled_transactions=unreconciled,
        net_balance=round(float(credits) - float(debits), 2),
        already_closed=already_closed,
    )


async def close_period(
    db: AsyncSession, payload: ClosePeriodRequest, user_id=None
) -> ClosedPeriodResponse:
    """Permanently lock an accounting period.

    Once closed, no journal entries can be created or posted for dates
    within the locked month. This operation is irreversible.

    Args:
        user_id: UUID of the authenticated user performing the close (audit trail).

    Raises:
        HTTPException 409: If the period is already closed.
    """
    existing = (await db.execute(
        select(ClosedPeriod).where(
            ClosedPeriod.year == payload.year, ClosedPeriod.month == payload.month
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Period {payload.year}-{payload.month:02d} is already closed",
        )

    cp = ClosedPeriod(
        year=payload.year,
        month=payload.month,
        closed_by=user_id,
        notes=payload.notes,
    )
    db.add(cp)
    await db.commit()
    await db.refresh(cp)
    return ClosedPeriodResponse.model_validate(cp)


async def list_closed_periods(db: AsyncSession) -> list[ClosedPeriodResponse]:
    """Return all closed periods ordered by year and month descending."""
    rows = (await db.execute(
        select(ClosedPeriod).order_by(ClosedPeriod.year.desc(), ClosedPeriod.month.desc())
    )).scalars().all()
    return [ClosedPeriodResponse.model_validate(r) for r in rows]


# ── Financial Reports ─────────────────────────────────────────────────────────

async def _account_report_lines(db: AsyncSession, account_types: list[AccountType]) -> list[ReportLineItem]:
    """Build report line items for the given account types.

    For each active account of the requested type, sums all posted debit and
    credit journal entry amounts and returns only accounts with non-zero activity.
    """
    rows = (await db.execute(
        select(Account).where(
            Account.account_type.in_(account_types),
            Account.is_active == True,
        ).order_by(Account.code)
    )).scalars().all()

    lines = []
    for acct in rows:
        # Sum posted journal entries for this account
        debit = float((await db.execute(
            select(func.coalesce(func.sum(JournalEntry.debit_amount), 0)).where(
                JournalEntry.account_id == acct.id,
                JournalEntry.status == JournalEntryStatus.POSTED,
            )
        )).scalar_one())
        credit = float((await db.execute(
            select(func.coalesce(func.sum(JournalEntry.credit_amount), 0)).where(
                JournalEntry.account_id == acct.id,
                JournalEntry.status == JournalEntryStatus.POSTED,
            )
        )).scalar_one())
        # Balance = account's own stored balance (updated when entries are posted)
        balance = float(acct.balance)
        if debit > 0 or credit > 0 or balance != 0:
            lines.append(ReportLineItem(
                account_code=acct.code,
                account_name=acct.name,
                debit=round(debit, 2),
                credit=round(credit, 2),
                balance=round(balance, 2),
            ))
    return lines


async def get_profit_loss(db: AsyncSession) -> ProfitLossReport:
    """Compute the year-to-date Profit & Loss report from posted journal entries."""
    now = datetime.now(timezone.utc)
    revenue_items = await _account_report_lines(db, [AccountType.REVENUE])
    expense_items = await _account_report_lines(db, [AccountType.EXPENSE])
    total_revenue  = sum(i.balance for i in revenue_items)
    total_expenses = sum(i.balance for i in expense_items)
    return ProfitLossReport(
        period_label=f"Jan – {now.strftime('%b %Y')}",
        revenue_items=revenue_items,
        expense_items=expense_items,
        total_revenue=round(total_revenue, 2),
        total_expenses=round(total_expenses, 2),
        net_income=round(total_revenue - total_expenses, 2),
    )


async def get_balance_sheet(db: AsyncSession) -> BalanceSheetReport:
    """Compute the Balance Sheet as of today.

    Liabilities + Equity + Net Income should equal Total Assets (accounting equation).
    """
    asset_items     = await _account_report_lines(db, [AccountType.ASSET])
    liability_items = await _account_report_lines(db, [AccountType.LIABILITY])
    equity_items    = await _account_report_lines(db, [AccountType.EQUITY])

    pl = await get_profit_loss(db)
    total_assets      = sum(i.balance for i in asset_items)
    total_liabilities = sum(i.balance for i in liability_items)
    total_equity      = sum(i.balance for i in equity_items)

    return BalanceSheetReport(
        as_of=datetime.now(timezone.utc).strftime("%d %b %Y"),
        asset_items=asset_items,
        liability_items=liability_items,
        equity_items=equity_items,
        total_assets=round(total_assets, 2),
        total_liabilities=round(total_liabilities, 2),
        total_equity=round(total_equity, 2),
        net_income=pl.net_income,
        liabilities_and_equity=round(total_liabilities + total_equity + pl.net_income, 2),
    )


async def get_trial_balance(db: AsyncSession) -> TrialBalanceReport:
    """Compute the Trial Balance across all account types.

    is_balanced=true confirms that total debits equal total credits,
    verifying the integrity of the double-entry ledger.
    """
    all_items = await _account_report_lines(
        db, [AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY,
             AccountType.REVENUE, AccountType.EXPENSE]
    )
    total_debits  = sum(i.debit  for i in all_items)
    total_credits = sum(i.credit for i in all_items)
    return TrialBalanceReport(
        as_of=datetime.now(timezone.utc).strftime("%d %b %Y"),
        items=all_items,
        total_debits=round(total_debits, 2),
        total_credits=round(total_credits, 2),
        is_balanced=round(total_debits, 2) == round(total_credits, 2),
    )


async def get_cash_flow(db: AsyncSession) -> CashFlowReport:
    """Compute the Cash Flow report from imported bank transactions.

    Inflows  = transactions with a positive amount (money received).
    Outflows = transactions with a negative amount (money paid out).
    Returns an empty report if no bank statements have been imported yet.
    """
    now = datetime.now(timezone.utc)
    # Cash flow = bank transaction movements (credits = inflows, debits = outflows)
    inflow_rows = (await db.execute(
        select(BankTransaction).where(BankTransaction.amount > 0)
        .order_by(BankTransaction.transaction_date.desc())
        .limit(50)
    )).scalars().all()

    outflow_rows = (await db.execute(
        select(BankTransaction).where(BankTransaction.amount < 0)
        .order_by(BankTransaction.transaction_date.desc())
        .limit(50)
    )).scalars().all()

    inflows = [
        ReportLineItem(
            account_code=str(r.transaction_date),
            account_name=r.description,
            debit=0.0,
            credit=float(r.amount),
            balance=float(r.amount),
        ) for r in inflow_rows
    ]
    outflows = [
        ReportLineItem(
            account_code=str(r.transaction_date),
            account_name=r.description,
            debit=abs(float(r.amount)),
            credit=0.0,
            balance=float(r.amount),
        ) for r in outflow_rows
    ]

    total_in  = sum(i.credit for i in inflows)
    total_out = sum(i.debit  for i in outflows)
    return CashFlowReport(
        period_label=f"Jan – {now.strftime('%b %Y')}",
        inflows=inflows,
        outflows=outflows,
        total_inflows=round(total_in, 2),
        total_outflows=round(total_out, 2),
        net_cash_flow=round(total_in - total_out, 2),
    )
