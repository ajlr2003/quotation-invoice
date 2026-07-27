# =============================================================================
# app/schemas/supplier_quotation.py
# -----------------------------------------------------------------------------
# Request/response models for supplier bids (SupplierQuotation) on RFQs.
# Supports multi-item bids where each item has its own price.
# =============================================================================

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Item schemas
# ============================================================================

class SupplierQuotationItemCreate(BaseModel):
    product_name: str = Field(min_length=1)
    description: Optional[str] = None
    quantity: float = Field(default=1.0, gt=0)
    unit_price: float = Field(gt=0)


class SupplierQuotationItemResponse(BaseModel):
    id: uuid.UUID
    supplier_quotation_id: uuid.UUID
    product_name: str
    description: Optional[str]
    quantity: float
    unit_price: float
    total: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================================
# Request schemas
# ============================================================================

class QuotationCreate(BaseModel):
    rfq_id: uuid.UUID
    supplier_id: uuid.UUID
    notes: Optional[str] = None
    # Multi-item support — at least one item is required
    items: List[SupplierQuotationItemCreate] = Field(
        default=[],
        description="Line items for this supplier bid. unit_price at top level is computed from items.",
    )
    # Kept for single-price backward compatibility; ignored when items are provided
    unit_price: Optional[float] = Field(default=None, gt=0)


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
    unit_price: float
    notes: Optional[str]
    supplier: SupplierSummary
    items: List[SupplierQuotationItemResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QuotationListResponse(BaseModel):
    items: list[QuotationResponse]
    total: int
