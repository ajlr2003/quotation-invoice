"""
app/schemas/purchase_order.py
Pydantic schemas for PurchaseOrder.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import PurchaseOrderStatus


class PurchaseOrderCreate(BaseModel):
    rfq_id: uuid.UUID
    # Optional — if omitted the service uses rfq.selected_supplier_id
    supplier_id: Optional[uuid.UUID] = None


class PurchaseOrderResponse(BaseModel):
    id: uuid.UUID
    rfq_id: uuid.UUID
    supplier_id: uuid.UUID
    status: PurchaseOrderStatus
    created_at: datetime

    model_config = {"from_attributes": True}
