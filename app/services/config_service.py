from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_settings import AppSettings
from app.models.config_list_item import ConfigListItem
from app.schemas.config_list_item import (
    AppSettingsResponse,
    AppSettingsUpdate,
    ConfigListItemCreate,
    ConfigListItemListResponse,
    ConfigListItemResponse,
    ConfigListItemUpdate,
)

VALID_LIST_TYPES = {"product_category", "unit_of_measure", "packaging", "payment_terms", "project_tag"}


def _validate_list_type(list_type: str) -> None:
    if list_type not in VALID_LIST_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown list_type. Must be one of: {sorted(VALID_LIST_TYPES)}",
        )


async def list_items(db: AsyncSession, list_type: str) -> ConfigListItemListResponse:
    _validate_list_type(list_type)
    result = await db.execute(
        select(ConfigListItem)
        .where(ConfigListItem.list_type == list_type)
        .order_by(ConfigListItem.value)
    )
    items = result.scalars().all()
    return ConfigListItemListResponse(
        items=[ConfigListItemResponse.model_validate(i) for i in items],
        total=len(items),
    )


async def create_item(db: AsyncSession, payload: ConfigListItemCreate) -> ConfigListItemResponse:
    _validate_list_type(payload.list_type)
    item = ConfigListItem(**payload.model_dump())
    db.add(item)
    await db.flush()
    return ConfigListItemResponse.model_validate(item)


async def update_item(db: AsyncSession, item_id: uuid.UUID, payload: ConfigListItemUpdate) -> ConfigListItemResponse:
    result = await db.execute(select(ConfigListItem).where(ConfigListItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    await db.flush()
    return ConfigListItemResponse.model_validate(item)


async def delete_item(db: AsyncSession, item_id: uuid.UUID) -> None:
    result = await db.execute(select(ConfigListItem).where(ConfigListItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    await db.delete(item)


# ── App-wide settings (single row) ──────────────────────────────────────────

async def _get_or_create_settings(db: AsyncSession) -> AppSettings:
    result = await db.execute(select(AppSettings).limit(1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = AppSettings()
        db.add(settings)
        await db.flush()
    return settings


async def get_settings(db: AsyncSession) -> AppSettingsResponse:
    settings = await _get_or_create_settings(db)
    return AppSettingsResponse.model_validate(settings)


async def update_settings(db: AsyncSession, payload: AppSettingsUpdate) -> AppSettingsResponse:
    settings = await _get_or_create_settings(db)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(settings, field, value)
    await db.flush()
    return AppSettingsResponse.model_validate(settings)
