from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, select, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.stock_item import StockItem
from app.models.stock_movement import StockMovement

# Items with 0 < stock_qty <= this are flagged "Low Stock" (distinct from
# "Out of Stock", which is stock_qty == 0).
LOW_STOCK_THRESHOLD = 5
from app.schemas.inventory import (
    InventoryKPIs,
    StockItemCreate,
    StockItemResponse,
    StockItemUpdate,
    StockMovementCreate,
    StockMovementResponse,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _item_to_response(item: StockItem) -> StockItemResponse:
    return StockItemResponse.model_validate(item)


def _movement_to_response(m: StockMovement, item: StockItem | None = None) -> StockMovementResponse:
    data = StockMovementResponse.model_validate(m)
    if item:
        data.part_number = item.part_number
        data.description = item.description
    return data


# ── Stock Items ───────────────────────────────────────────────────────────────

async def list_items(
    db: AsyncSession,
    search: Optional[str] = None,
    supplier: Optional[str] = None,
    location: Optional[str] = None,
    zero_stock_only: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> tuple[List[StockItemResponse], int]:
    q = select(StockItem)

    if search:
        pattern = f"%{search}%"
        q = q.where(
            StockItem.part_number.ilike(pattern)
            | StockItem.description.ilike(pattern)
            | StockItem.serial_number.ilike(pattern)
        )
    if supplier:
        q = q.where(StockItem.supplier_manufacturer.ilike(f"%{supplier}%"))
    if location:
        q = q.where(StockItem.warehouse_location.ilike(f"%{location}%"))
    if zero_stock_only:
        q = q.where(StockItem.stock_qty == 0)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(StockItem.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return [_item_to_response(r) for r in rows], total


async def get_item(db: AsyncSession, item_id: uuid.UUID) -> StockItem | None:
    return (await db.execute(select(StockItem).where(StockItem.id == item_id))).scalar_one_or_none()


async def create_item(db: AsyncSession, payload: StockItemCreate) -> StockItemResponse:
    item = StockItem(**payload.model_dump())
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return _item_to_response(item)


async def update_item(
    db: AsyncSession, item_id: uuid.UUID, payload: StockItemUpdate
) -> StockItemResponse | None:
    item = await get_item(db, item_id)
    if not item:
        return None
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.flush()
    await db.refresh(item)
    return _item_to_response(item)


async def delete_item(db: AsyncSession, item_id: uuid.UUID) -> bool:
    item = await get_item(db, item_id)
    if not item:
        return False
    await db.delete(item)
    await db.flush()
    return True


# ── Stock Movements ───────────────────────────────────────────────────────────

async def list_movements(
    db: AsyncSession,
    movement_type: Optional[str] = None,
    item_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[List[StockMovementResponse], int]:
    q = select(StockMovement)
    if movement_type:
        q = q.where(StockMovement.movement_type == movement_type.upper())
    if item_id:
        q = q.where(StockMovement.item_id == item_id)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(StockMovement.moved_at.desc()).offset(skip).limit(limit))).scalars().all()

    # fetch items for denormalisation
    item_ids = list({r.item_id for r in rows})
    items_map: dict[uuid.UUID, StockItem] = {}
    if item_ids:
        items = (await db.execute(select(StockItem).where(StockItem.id.in_(item_ids)))).scalars().all()
        items_map = {i.id: i for i in items}

    return [_movement_to_response(r, items_map.get(r.item_id)) for r in rows], total


async def record_movement(
    db: AsyncSession, payload: StockMovementCreate
) -> StockMovementResponse:
    item = await get_item(db, payload.item_id)
    if not item:
        raise ValueError(f"Stock item {payload.item_id} not found")

    movement = StockMovement(**payload.model_dump())
    db.add(movement)

    # Update the stock qty
    if payload.movement_type == "IN":
        item.stock_qty += payload.quantity
    else:
        item.stock_qty = max(0, item.stock_qty - payload.quantity)

    await db.flush()
    await db.refresh(movement)
    return _movement_to_response(movement, item)


# ── KPIs ──────────────────────────────────────────────────────────────────────

async def get_kpis(db: AsyncSession) -> InventoryKPIs:
    total_items = (await db.execute(select(func.count()).select_from(StockItem))).scalar_one()
    total_qty = (await db.execute(select(func.coalesce(func.sum(StockItem.stock_qty), 0)))).scalar_one()
    zero_stock = (
        await db.execute(select(func.count()).select_from(StockItem).where(StockItem.stock_qty == 0))
    ).scalar_one()
    low_stock = (
        await db.execute(
            select(func.count()).select_from(StockItem).where(
                StockItem.stock_qty > 0, StockItem.stock_qty <= LOW_STOCK_THRESHOLD,
            )
        )
    ).scalar_one()
    today = date.today()
    expiring_soon = (
        await db.execute(
            select(func.count()).select_from(StockItem).where(
                StockItem.expiry_date.isnot(None),
                StockItem.expiry_date >= today,
                StockItem.expiry_date <= today + timedelta(days=30),
            )
        )
    ).scalar_one()
    valuation = (
        await db.execute(
            select(func.coalesce(
                func.sum(StockItem.unit_price * StockItem.stock_qty), 0
            )).where(StockItem.unit_price.isnot(None))
        )
    ).scalar_one()

    now = datetime.now(timezone.utc)
    movements_month = (
        await db.execute(
            select(func.count()).select_from(StockMovement).where(
                extract("year", StockMovement.moved_at) == now.year,
                extract("month", StockMovement.moved_at) == now.month,
            )
        )
    ).scalar_one()
    movements_today = (
        await db.execute(
            select(func.count()).select_from(StockMovement).where(
                func.date(StockMovement.moved_at) == today,
            )
        )
    ).scalar_one()

    return InventoryKPIs(
        total_items=total_items,
        total_qty=int(total_qty),
        zero_stock_count=zero_stock,
        low_stock_count=low_stock,
        expiring_soon_count=expiring_soon,
        movements_today=movements_today,
        total_valuation=float(valuation),
        movements_this_month=movements_month,
    )


async def get_demand_forecast(db: AsyncSession, limit: int = 5) -> dict:
    """Real velocity-based demand projection: for each of the top-N
    highest-stocked items, predicted_demand is the trailing-90-day average
    monthly OUT quantity from stock_movements — not a synthetic multiplier.
    Items with no OUT history return predicted_demand=0 (honest, not guessed).
    """
    items_result = await db.execute(
        select(StockItem)
        .where(StockItem.stock_qty > 0)
        .order_by(StockItem.stock_qty.desc())
        .limit(limit)
    )
    items = items_result.scalars().all()

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    out_items = []
    for item in items:
        out_result = await db.execute(
            select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
                StockMovement.item_id == item.id,
                StockMovement.movement_type == "OUT",
                StockMovement.moved_at >= cutoff,
            )
        )
        total_out = float(out_result.scalar_one())
        avg_monthly_demand = round(total_out / 3.0, 1)
        out_items.append({
            "id": str(item.id),
            "name": item.part_number,
            "current_stock": item.stock_qty,
            "predicted_demand": avg_monthly_demand,
            "has_movement_history": total_out > 0,
        })

    return {"items": out_items}
