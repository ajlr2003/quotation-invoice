from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.config_list_item import (
    AppSettingsResponse,
    AppSettingsUpdate,
    ConfigListItemCreate,
    ConfigListItemListResponse,
    ConfigListItemResponse,
    ConfigListItemUpdate,
)
from app.services import config_service

router = APIRouter()

_admin_manager_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER)


@router.get("/lists", response_model=ConfigListItemListResponse)
async def list_config_items(
    list_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await config_service.list_items(db, list_type)


@router.post("/lists", response_model=ConfigListItemResponse, status_code=status.HTTP_201_CREATED)
async def create_config_item(
    payload: ConfigListItemCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin_manager_roles),
):
    return await config_service.create_item(db, payload)


@router.patch("/lists/{item_id}", response_model=ConfigListItemResponse)
async def update_config_item(
    item_id: uuid.UUID,
    payload: ConfigListItemUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin_manager_roles),
):
    return await config_service.update_item(db, item_id, payload)


@router.delete("/lists/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin_manager_roles),
):
    await config_service.delete_item(db, item_id)


@router.get("/settings", response_model=AppSettingsResponse)
async def get_app_settings(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await config_service.get_settings(db)


@router.patch("/settings", response_model=AppSettingsResponse)
async def update_app_settings(
    payload: AppSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_admin_manager_roles),
):
    return await config_service.update_settings(db, payload)
