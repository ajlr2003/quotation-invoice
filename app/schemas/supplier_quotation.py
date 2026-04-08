"""
app/schemas/supplier_quotation.py
Pydantic schemas for SupplierQuotation (supplier bids on RFQs).
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# Request schemas
# ============================================================================

class QuotationCreate(BaseModel):
    rfq_id: uuid.UUID
    supplier_id: uuid.UUID
    price: float = Field(gt=0, description="Total quoted price (must be greater than zero)")
    notes: Optional[str] = None


# ============================================================================
# Response schemas
# ============================================================================

class SupplierSummary(BaseModel):
    id: uuid.UUID
    company_name: str
    contact_name: Optional[str]
    email: str
    phone: Optional[str]

    model_config = {"from_attributes": True}


class QuotationResponse(BaseModel):
    id: uuid.UUID
    rfq_id: uuid.UUID
    supplier_id: uuid.UUID
    price: float
    notes: Optional[str]
    supplier: SupplierSummary
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QuotationListResponse(BaseModel):
    items: list[QuotationResponse]
    total: int
