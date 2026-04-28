"""
app/schemas/purchase_order.py
Pydantic schemas for PurchaseOrder.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, computed_field, field_validator

from app.models.enums import PurchaseOrderStatus


class PurchaseOrderCreate(BaseModel):
    rfq_id: uuid.UUID
    # Optional — if omitted the service uses rfq.selected_supplier_id
    supplier_id: Optional[uuid.UUID] = None


class PurchaseOrderResponse(BaseModel):
    id: uuid.UUID
    rfq_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: Optional[str] = None
    status: PurchaseOrderStatus
    # Quantity
    ordered_quantity: float = 0
    received_quantity: float = 0
    # Pricing — unit_price = total_price / ordered_quantity
    unit_price: float = 0
    total_price: float = 0
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def remaining_quantity(self) -> float:
        """Units still outstanding (ordered minus received, floor at 0)."""
        return max(0.0, self.ordered_quantity - self.received_quantity)

    @field_validator("ordered_quantity")
    @classmethod
    def ordered_must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("ordered_quantity must be >= 0")
        return v

    @field_validator("unit_price", "total_price")
    @classmethod
    def price_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("price must be >= 0")
        return v


class PurchaseOrderListResponse(BaseModel):
    items: List[PurchaseOrderResponse]
    total: int
