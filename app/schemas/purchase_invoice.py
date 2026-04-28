"""
app/schemas/purchase_invoice.py
Pydantic schemas for PurchaseInvoice.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.models.enums import PurchaseInvoiceStatus


class PurchaseInvoiceCreate(BaseModel):
    """Input: only grn_id — everything else is derived from the GRN → PO chain."""
    grn_id: uuid.UUID


class PurchaseInvoiceResponse(BaseModel):
    id: uuid.UUID
    po_id: uuid.UUID
    grn_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: Optional[str] = None
    # Quantity and pricing snapshot
    quantity: float = 0.0
    unit_price: float
    total_amount: float
    status: PurchaseInvoiceStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class PurchaseInvoiceListResponse(BaseModel):
    items: List[PurchaseInvoiceResponse]
    total: int
