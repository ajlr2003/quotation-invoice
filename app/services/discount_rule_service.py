from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discount_rule import DiscountRule
from app.schemas.discount_rule import (
    DiscountRuleCreate,
    DiscountRuleListResponse,
    DiscountRuleResponse,
    DiscountRuleUpdate,
)


async def _get_or_404(db: AsyncSession, rule_id: uuid.UUID) -> DiscountRule:
    result = await db.execute(select(DiscountRule).where(DiscountRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discount rule not found.")
    return rule


async def list_rules(db: AsyncSession, active_only: bool = False) -> DiscountRuleListResponse:
    stmt = select(DiscountRule).order_by(DiscountRule.created_at.desc())
    if active_only:
        stmt = stmt.where(DiscountRule.is_active.is_(True))
    result = await db.execute(stmt)
    rules = result.scalars().all()
    return DiscountRuleListResponse(
        items=[DiscountRuleResponse.model_validate(r) for r in rules],
        total=len(rules),
    )


async def create_rule(db: AsyncSession, payload: DiscountRuleCreate) -> DiscountRuleResponse:
    rule = DiscountRule(**payload.model_dump())
    db.add(rule)
    await db.flush()
    return DiscountRuleResponse.model_validate(rule)


async def update_rule(db: AsyncSession, rule_id: uuid.UUID, payload: DiscountRuleUpdate) -> DiscountRuleResponse:
    rule = await _get_or_404(db, rule_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    await db.flush()
    return DiscountRuleResponse.model_validate(rule)


async def delete_rule(db: AsyncSession, rule_id: uuid.UUID) -> None:
    rule = await _get_or_404(db, rule_id)
    await db.delete(rule)
