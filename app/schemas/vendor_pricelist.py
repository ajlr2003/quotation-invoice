# =============================================================================
# app/schemas/vendor_pricelist.py
# -----------------------------------------------------------------------------
# Request/response models for Vendor Pricelist CRUD endpoints.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date as _Date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class VendorPricelistCreate(BaseModel):
    supplier_id: uuid.UUID
    vendor_product_name: Optional[str] = None
    vendor_product_code: Optional[str] = None
    lead_time_days: int = Field(default=1, ge=0)
    stock_item_id: Optional[uuid.UUID] = None
    quantity: float = Field(default=1, gt=0)
    unit_price: float = Field(default=0, ge=0)
    valid_from: Optional[_Date] = None
    valid_to: Optional[_Date] = None
    discount_pct: float = Field(default=0, ge=0, le=100)


class VendorPricelistUpdate(VendorPricelistCreate):
    pass


class VendorPricelistResponse(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: Optional[str] = None
    vendor_product_name: Optional[str] = None
    vendor_product_code: Optional[str] = None
    lead_time_days: int
    stock_item_id: Optional[uuid.UUID] = None
    product_name: Optional[str] = None
    quantity: float
    unit_price: float
    valid_from: Optional[_Date] = None
    valid_to: Optional[_Date] = None
    discount_pct: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VendorPricelistListResponse(BaseModel):
    items: List[VendorPricelistResponse]
    total: int
