from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.expense import (
    ExpenseCreate, ExpenseKPIs, ExpenseListResponse,
    ExpenseResponse, ExpenseStatusUpdate,
)
from app.services import expense_service

router = APIRouter()

_finance_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.FINANCE)


@router.get("/kpis", response_model=ExpenseKPIs)
async def kpis(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await expense_service.get_kpis(db)


@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    items, total = await expense_service.list_expenses(db, status=status, category=category, skip=skip, limit=limit)
    return ExpenseListResponse(items=items, total=total)


@router.post("", response_model=ExpenseResponse, status_code=201)
async def create_expense(
    payload: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_finance_roles),
):
    result = await expense_service.create_expense(db, payload, user_id=user.id)
    await db.commit()
    return result


@router.patch("/{expense_id}/status", response_model=ExpenseResponse)
async def update_status(
    expense_id: uuid.UUID,
    payload: ExpenseStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_finance_roles),
):
    result = await expense_service.update_status(db, expense_id, payload)
    if not result:
        raise HTTPException(status_code=404, detail="Expense not found")
    await db.commit()
    return result


@router.delete("/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_finance_roles),
):
    deleted = await expense_service.delete_expense(db, expense_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Expense not found")
    await db.commit()
