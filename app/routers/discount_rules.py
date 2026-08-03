from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.discount_rule import (
    DiscountRuleCreate,
    DiscountRuleListResponse,
    DiscountRuleResponse,
    DiscountRuleUpdate,
)
from app.services import discount_rule_service

router = APIRouter()

_sales_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES)


@router.get("", response_model=DiscountRuleListResponse)
async def list_discount_rules(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await discount_rule_service.list_rules(db, active_only)


@router.post("", response_model=DiscountRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_discount_rule(
    payload: DiscountRuleCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_sales_roles),
):
    return await discount_rule_service.create_rule(db, payload)


@router.patch("/{rule_id}", response_model=DiscountRuleResponse)
async def update_discount_rule(
    rule_id: uuid.UUID,
    payload: DiscountRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_sales_roles),
):
    return await discount_rule_service.update_rule(db, rule_id, payload)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_discount_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_sales_roles),
):
    await discount_rule_service.delete_rule(db, rule_id)
