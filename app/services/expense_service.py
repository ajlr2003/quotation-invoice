from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.schemas.expense import (
    ExpenseCreate, ExpenseKPIs, ExpenseResponse, ExpenseStatusUpdate,
)


def _to_resp(e: Expense) -> ExpenseResponse:
    return ExpenseResponse.model_validate(e)


async def list_expenses(
    db: AsyncSession,
    status: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[List[ExpenseResponse], int]:
    q = select(Expense)
    if status:
        q = q.where(Expense.status == status)
    if category:
        q = q.where(Expense.category == category)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(Expense.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return [_to_resp(r) for r in rows], total


async def create_expense(
    db: AsyncSession, payload: ExpenseCreate, user_id: Optional[uuid.UUID] = None
) -> ExpenseResponse:
    expense = Expense(**payload.model_dump(), submitted_by_id=user_id)
    db.add(expense)
    await db.flush()
    await db.refresh(expense)
    return _to_resp(expense)


async def update_status(
    db: AsyncSession, expense_id: uuid.UUID, payload: ExpenseStatusUpdate
) -> ExpenseResponse | None:
    expense = (await db.execute(select(Expense).where(Expense.id == expense_id))).scalar_one_or_none()
    if not expense:
        return None
    expense.status = payload.status
    if payload.rejection_reason:
        expense.rejection_reason = payload.rejection_reason
    await db.flush()
    await db.refresh(expense)
    return _to_resp(expense)


async def delete_expense(db: AsyncSession, expense_id: uuid.UUID) -> bool:
    expense = (await db.execute(select(Expense).where(Expense.id == expense_id))).scalar_one_or_none()
    if not expense:
        return False
    await db.delete(expense)
    await db.flush()
    return True


async def get_kpis(db: AsyncSession) -> ExpenseKPIs:
    all_rows = (await db.execute(select(Expense))).scalars().all()

    total_submitted = len(all_rows)
    pending   = [e for e in all_rows if e.status == "submitted"]
    approved  = [e for e in all_rows if e.status == "approved"]
    reimbursed = [e for e in all_rows if e.status == "reimbursed"]
    rejected  = [e for e in all_rows if e.status == "rejected"]

    # Category breakdown
    cat_map: dict[str, float] = {}
    for e in all_rows:
        cat_map[e.category] = cat_map.get(e.category, 0) + float(e.amount)
    category_breakdown = [{"category": k, "total": v} for k, v in sorted(cat_map.items(), key=lambda x: -x[1])]

    return ExpenseKPIs(
        total_submitted=total_submitted,
        pending_count=len(pending),
        pending_amount=sum(float(e.amount) for e in pending),
        approved_amount=sum(float(e.amount) for e in approved),
        reimbursed_amount=sum(float(e.amount) for e in reimbursed),
        rejected_count=len(rejected),
        category_breakdown=category_breakdown,
    )
