from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.inventory import (
    InventoryKPIs,
    StockItemCreate,
    StockItemListResponse,
    StockItemResponse,
    StockItemUpdate,
    StockMovementCreate,
    StockMovementListResponse,
    StockMovementResponse,
)
from app.services import inventory_service

router = APIRouter()

_inventory_write_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.PURCHASER)

# Changing the cost->sales-price multiplying factor is restricted to a
# narrower group than general inventory editing, since it directly sets
# margin on every item priced that way.
_FACTOR_EDIT_ROLES = {UserRole.ADMIN, UserRole.MANAGER}


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis", response_model=InventoryKPIs)
async def kpis(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await inventory_service.get_kpis(db)


@router.get("/demand-forecast", summary="Real velocity-based demand projection for top-stocked items")
async def demand_forecast(
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await inventory_service.get_demand_forecast(db, limit=limit)


# ── Stock Items ───────────────────────────────────────────────────────────────

@router.get("/items", response_model=StockItemListResponse)
async def list_items(
    search: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    zero_stock_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    items, total = await inventory_service.list_items(
        db, search=search, supplier=supplier, location=location,
        zero_stock_only=zero_stock_only, skip=skip, limit=limit,
    )
    return StockItemListResponse(items=items, total=total)


@router.post("/items", response_model=StockItemResponse, status_code=201)
async def create_item(
    payload: StockItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_inventory_write_roles),
):
    item = await inventory_service.create_item(
        db, payload, allow_factor_edit=current_user.role in _FACTOR_EDIT_ROLES,
    )
    await db.commit()
    return item


@router.put("/items/{item_id}", response_model=StockItemResponse)
async def update_item(
    item_id: uuid.UUID,
    payload: StockItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_inventory_write_roles),
):
    result = await inventory_service.update_item(
        db, item_id, payload, allow_factor_edit=current_user.role in _FACTOR_EDIT_ROLES,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.commit()
    return result


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_inventory_write_roles),
):
    deleted = await inventory_service.delete_item(db, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.commit()


# ── Stock Movements ───────────────────────────────────────────────────────────

@router.get("/movements", response_model=StockMovementListResponse)
async def list_movements(
    movement_type: Optional[str] = Query(None, pattern="^(IN|OUT)$"),
    item_id: Optional[uuid.UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    movements, total = await inventory_service.list_movements(
        db, movement_type=movement_type, item_id=item_id, skip=skip, limit=limit,
    )
    return StockMovementListResponse(items=movements, total=total)


@router.post("/movements", response_model=StockMovementResponse, status_code=201)
async def record_movement(
    payload: StockMovementCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_inventory_write_roles),
):
    try:
        result = await inventory_service.record_movement(db, payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
