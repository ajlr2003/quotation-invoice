from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConfigListItemCreate(BaseModel):
    list_type: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=150)
    is_active: bool = True


class ConfigListItemUpdate(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=150)
    is_active: Optional[bool] = None


class ConfigListItemResponse(BaseModel):
    id: uuid.UUID
    list_type: str
    value: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ConfigListItemListResponse(BaseModel):
    items: List[ConfigListItemResponse]
    total: int


class AppSettingsResponse(BaseModel):
    default_currency: str
    default_payment_terms: Optional[str]
    default_tax_rate: float
    model_config = ConfigDict(from_attributes=True)


class AppSettingsUpdate(BaseModel):
    default_currency: Optional[str] = Field(default=None, min_length=1, max_length=10)
    default_payment_terms: Optional[str] = Field(default=None, max_length=100)
    default_tax_rate: Optional[float] = Field(default=None, ge=0, le=100)
