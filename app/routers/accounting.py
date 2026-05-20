# =============================================================================
# app/routers/accounting.py
# -----------------------------------------------------------------------------
# HTTP endpoints for the Accounting module.
#
# GET  /api/v1/accounting/kpis                 — dashboard KPI summary
# GET  /api/v1/accounting/accounts             — chart of accounts
# POST /api/v1/accounting/accounts             — create account
# GET  /api/v1/accounting/journal-entries      — list recent journal entries
# POST /api/v1/accounting/journal-entries      — create journal entry
# POST /api/v1/accounting/journal-entries/{id}/post — post a draft entry
# =============================================================================

import uuid

from fastapi import APIRouter, Depends

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.accounting import (
    AccountCreate,
    AccountingKPIResponse,
    AccountListResponse,
    AccountResponse,
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
)
from app.services import accounting_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/kpis", response_model=AccountingKPIResponse)
async def get_kpis(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    return await accounting_service.get_kpis(db)


@router.get("/accounts", response_model=AccountListResponse)
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    return await accounting_service.list_accounts(db)


@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(
    payload: AccountCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    return await accounting_service.create_account(db, payload)


@router.get("/journal-entries", response_model=JournalEntryListResponse)
async def list_journal_entries(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    return await accounting_service.list_journal_entries(db, limit=limit)


@router.post("/journal-entries", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(
    payload: JournalEntryCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    return await accounting_service.create_journal_entry(db, payload)


@router.post("/journal-entries/{entry_id}/post", response_model=JournalEntryResponse)
async def post_journal_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    return await accounting_service.post_journal_entry(db, entry_id)
