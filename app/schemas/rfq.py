"""
app/schemas/rfq.py
Pydantic request/response schemas for RFQ and RFQItem CRUD.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import RFQStatus


# ============================================================================
# RFQ Item schemas
# ============================================================================

class RFQItemCreateRequest(BaseModel):
    product_code: Optional[str]        = Field(default=None, max_length=100)
    product_name: str                  = Field(min_length=1, max_length=255)
    description: Optional[str]         = None
    quantity: float                    = Field(gt=0, description="Must be greater than zero")
    unit_of_measure: str               = Field(default="unit", max_length=50)
    target_unit_price: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str]               = None

    @field_validator("quantity")
    @classmethod
    def quantity_precision(cls, v: float) -> float:
        return round(v, 3)


class RFQItemResponse(BaseModel):
    id: uuid.UUID
    rfq_id: uuid.UUID
    line_number: int
    product_code: Optional[str]
    product_name: str
    description: Optional[str]
    quantity: float
    unit_of_measure: str
    target_unit_price: Optional[float]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RFQItemListResponse(BaseModel):
    items: List[RFQItemResponse]
    total: int


# ============================================================================
# RFQ schemas
# ============================================================================

class RFQCreateRequest(BaseModel):
    title: str                          = Field(min_length=2, max_length=255)
    description: Optional[str]          = None
    currency: str                       = Field(default="USD", min_length=3, max_length=3)
    issue_date: Optional[date]          = None
    deadline: Optional[date]            = None
    # Optionally create items inline on RFQ creation
    items: Optional[List[RFQItemCreateRequest]] = Field(default=None)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def deadline_after_issue(self) -> "RFQCreateRequest":
        if self.issue_date and self.deadline:
            if self.deadline <= self.issue_date:
                raise ValueError("deadline must be after issue_date")
        return self


class RFQUpdateRequest(BaseModel):
    title: Optional[str]                = Field(default=None, min_length=2, max_length=255)
    description: Optional[str]          = None
    currency: Optional[str]             = Field(default=None, min_length=3, max_length=3)
    issue_date: Optional[date]          = None
    deadline: Optional[date]            = None
    status: Optional[RFQStatus]         = None

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v


class RFQStatusUpdateRequest(BaseModel):
    """Dedicated schema for explicit status transitions."""
    status: RFQStatus


# ── Nested summary used inside RFQResponse ───────────────────────────────────
class RFQCreatedByResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str

    model_config = {"from_attributes": True}


class RFQResponse(BaseModel):
    id: uuid.UUID
    rfq_number: str
    title: str
    description: Optional[str]
    status: RFQStatus
    currency: str
    issue_date: Optional[date]
    deadline: Optional[date]
    created_by_id: uuid.UUID
    created_by: RFQCreatedByResponse
    items: List[RFQItemResponse]
    item_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_count(cls, rfq) -> "RFQResponse":
        data = cls.model_validate(rfq)
        data.item_count = len(rfq.items)
        return data


class RFQSummaryResponse(BaseModel):
    """Lighter version used in list view — no nested items."""
    id: uuid.UUID
    rfq_number: str
    title: str
    status: RFQStatus
    currency: str
    issue_date: Optional[date]
    deadline: Optional[date]
    created_by_id: uuid.UUID
    item_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RFQListResponse(BaseModel):
    items: List[RFQSummaryResponse]
    total: int
    page: int
    page_size: int
    pages: int
