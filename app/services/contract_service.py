# =============================================================================
# app/services/contract_service.py
# -----------------------------------------------------------------------------
# Business logic for the Contracts (PO payment-milestone tracker) module.
# Deliberately simple CRUD — unlike SalesInvoice there's no lifecycle/locking
# here, since this module exists to let staff freely track and correct
# collection status as it evolves, not to produce a legal document.
#
# Services only flush — the request-scoped session in get_db() commits.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.contract import Contract, ContractMilestone
from app.models.enums import ActivityEntityType, ContractMilestoneStatus
from app.schemas.contract import (
    ContractCreate,
    ContractKPIs,
    ContractListResponse,
    ContractMilestoneCreate,
    ContractResponse,
    ContractUpdate,
)
from app.services import activity_service

_LOAD_MILESTONES = selectinload(Contract.milestones)


def _r2(n) -> float:
    """Round to 2dp, treating None as 0 — every money value passes through this."""
    return round(float(n or 0), 2)


def _apply_fields(c: Contract, payload: ContractCreate) -> None:
    c.file_ref = payload.file_ref.strip()
    c.customer = payload.customer.strip()
    c.po_number = (payload.po_number or "").strip() or None
    c.po_value = _r2(payload.po_value)
    c.po_date = payload.po_date
    c.po_expiry_date = payload.po_expiry_date
    c.title = (payload.title or "").strip() or None
    c.contract_value = _r2(payload.contract_value) if payload.contract_value is not None else None
    c.risk = payload.risk


async def _load(db: AsyncSession, contract_id: uuid.UUID) -> Contract:
    """Fetch one contract with its milestones eagerly loaded, or 404."""
    result = await db.execute(
        select(Contract).where(Contract.id == contract_id)
        .options(_LOAD_MILESTONES).execution_options(populate_existing=True)
    )
    c = result.scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return c


async def list_contracts(
    db: AsyncSession, search: Optional[str] = None, skip: int = 0, limit: int = 200,
) -> ContractListResponse:
    """List contracts (newest first), optionally filtered by a text search
    against the file reference, customer name or PO number."""
    q = select(Contract).options(_LOAD_MILESTONES)
    if search:
        pattern = f"%{search.strip()}%"
        q = q.where(or_(
            Contract.file_ref.ilike(pattern),
            Contract.customer.ilike(pattern),
            Contract.po_number.ilike(pattern),
        ))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(Contract.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return ContractListResponse(items=[ContractResponse.model_validate(r) for r in rows], total=total)


async def get_contract(db: AsyncSession, contract_id: uuid.UUID) -> ContractResponse:
    return ContractResponse.model_validate(await _load(db, contract_id))


async def create_contract(
    db: AsyncSession, payload: ContractCreate, user_id: Optional[uuid.UUID]
) -> ContractResponse:
    c = Contract()
    _apply_fields(c, payload)
    db.add(c)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.CONTRACT, c.id, "created",
        f"Contract {c.file_ref} created for {c.customer}", user_id,
    )
    await db.flush()
    return await get_contract(db, c.id)


async def update_contract(
    db: AsyncSession, contract_id: uuid.UUID, payload: ContractUpdate, user_id: Optional[uuid.UUID]
) -> ContractResponse:
    c = await _load(db, contract_id)
    _apply_fields(c, payload)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.CONTRACT, c.id, "updated", f"Contract {c.file_ref} edited", user_id,
    )
    await db.flush()
    return await get_contract(db, c.id)


async def delete_contract(db: AsyncSession, contract_id: uuid.UUID) -> None:
    c = await _load(db, contract_id)
    await db.delete(c)
    await db.flush()


async def add_milestone(
    db: AsyncSession, contract_id: uuid.UUID, payload: ContractMilestoneCreate, user_id: Optional[uuid.UUID]
) -> ContractResponse:
    c = await _load(db, contract_id)
    c.milestones.append(ContractMilestone(
        name=payload.name.strip(), pct=_r2(payload.pct), amount=_r2(payload.amount),
        due_date=payload.due_date, status=payload.status,
        planned_date=payload.planned_date, achieved_date=payload.achieved_date,
        invoice_number=(payload.invoice_number or "").strip() or None,
        invoice_date=payload.invoice_date, received_date=payload.received_date,
    ))
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.CONTRACT, c.id, "milestone_added",
        f"Milestone \"{payload.name}\" added to {c.file_ref}", user_id,
    )
    await db.flush()
    return await get_contract(db, c.id)


async def update_milestone(
    db: AsyncSession, contract_id: uuid.UUID, milestone_id: uuid.UUID,
    payload: ContractMilestoneCreate, user_id: Optional[uuid.UUID],
) -> ContractResponse:
    c = await _load(db, contract_id)
    m = next((x for x in c.milestones if x.id == milestone_id), None)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    m.name = payload.name.strip()
    m.pct = _r2(payload.pct)
    m.amount = _r2(payload.amount)
    m.due_date = payload.due_date
    m.status = payload.status
    m.planned_date = payload.planned_date
    m.achieved_date = payload.achieved_date
    m.invoice_number = (payload.invoice_number or "").strip() or None
    m.invoice_date = payload.invoice_date
    m.received_date = payload.received_date
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.CONTRACT, c.id, "milestone_updated",
        f"Milestone \"{m.name}\" updated on {c.file_ref}", user_id,
    )
    await db.flush()
    return await get_contract(db, c.id)


async def delete_milestone(
    db: AsyncSession, contract_id: uuid.UUID, milestone_id: uuid.UUID, user_id: Optional[uuid.UUID]
) -> ContractResponse:
    c = await _load(db, contract_id)
    m = next((x for x in c.milestones if x.id == milestone_id), None)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    c.milestones.remove(m)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.CONTRACT, c.id, "milestone_removed",
        f"Milestone \"{m.name}\" removed from {c.file_ref}", user_id,
    )
    await db.flush()
    return await get_contract(db, c.id)


async def get_kpis(db: AsyncSession) -> ContractKPIs:
    """Headline totals across every contract, in SAR — mirrors the maths the
    frontend used to do client-side over its localStorage copy."""
    contracts = (await db.execute(select(Contract).options(_LOAD_MILESTONES))).scalars().all()
    total_contract_value = sum(c.effective_value for c in contracts)

    totals = {s: 0.0 for s in ContractMilestoneStatus}
    for c in contracts:
        for m in c.milestones:
            totals[m.status] += float(m.amount or 0)

    return ContractKPIs(
        total_contract_value=_r2(total_contract_value),
        received=_r2(totals[ContractMilestoneStatus.RECEIVED]),
        invoiced_pending=_r2(totals[ContractMilestoneStatus.INVOICED]),
        not_yet_invoiced=_r2(totals[ContractMilestoneStatus.PENDING]),
        overdue=_r2(totals[ContractMilestoneStatus.OVERDUE]),
    )
