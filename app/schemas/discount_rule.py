from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DiscountRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: Optional[str] = None
    discount_label: str = Field(min_length=1, max_length=50)
    min_order_value: Optional[float] = Field(default=None, ge=0)
    is_active: bool = True


class DiscountRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    description: Optional[str] = None
    discount_label: Optional[str] = Field(default=None, min_length=1, max_length=50)
    min_order_value: Optional[float] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class DiscountRuleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    discount_label: str
    min_order_value: Optional[float]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DiscountRuleListResponse(BaseModel):
    items: List[DiscountRuleResponse]
    total: int
