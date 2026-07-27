from __future__ import annotations

import uuid
from datetime import date as _Date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Stock Item ────────────────────────────────────────────────────────────────

class StockItemCreate(BaseModel):
    warehouse_location: Optional[str] = None
    box_number: Optional[str] = None
    supplier_manufacturer: Optional[str] = None
    part_number: str = Field(min_length=1)
    serial_number: Optional[str] = None
    description: Optional[str] = None
    expiry_date: Optional[_Date] = None
    stock_qty: int = Field(default=0, ge=0)
    received_file_no: Optional[str] = None
    po_number: Optional[str] = None
    unit_price: Optional[float] = Field(default=None, ge=0)
    receiving_delivery_status: Optional[str] = None
    customer_name: Optional[str] = None
    image_url: Optional[str] = None


class StockItemUpdate(StockItemCreate):
    part_number: Optional[str] = None  # allow partial update


class StockItemResponse(StockItemCreate):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class StockItemListResponse(BaseModel):
    items: List[StockItemResponse]
    total: int


# ── Stock Movement ────────────────────────────────────────────────────────────

class StockMovementCreate(BaseModel):
    item_id: uuid.UUID
    movement_type: str = Field(pattern="^(IN|OUT)$")
    quantity: int = Field(gt=0)
    reference_no: Optional[str] = None
    delivery_note_no: Optional[str] = None
    notes: Optional[str] = None


class StockMovementResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    movement_type: str
    quantity: int
    reference_no: Optional[str]
    delivery_note_no: Optional[str]
    notes: Optional[str]
    moved_at: datetime
    created_at: datetime
    # denormalised for display
    part_number: Optional[str] = None
    description: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class StockMovementListResponse(BaseModel):
    items: List[StockMovementResponse]
    total: int


# ── KPIs ──────────────────────────────────────────────────────────────────────

class InventoryKPIs(BaseModel):
    total_items: int
    total_qty: int
    zero_stock_count: int
    low_stock_count: int
    expiring_soon_count: int
    movements_today: int
    total_valuation: float
    movements_this_month: int
