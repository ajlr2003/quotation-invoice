"""
app/schemas/invoice.py
Pydantic schemas for the /api/v1/invoices endpoints.

These schemas are the public-facing contract for invoice responses.
The model stores `total_amount`; the API surface exposes it as `amount`
to match the spec and keep the field name simple for consumers.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import PurchaseInvoiceStatus


class InvoiceFromGRNRequest(BaseModel):
    """Input for POST /invoices/from-grn — only grn_id required."""
    grn_id: uuid.UUID


class InvoiceResponse(BaseModel):
    """Full invoice response returned by all invoice endpoints."""
    id: uuid.UUID
    po_id: uuid.UUID
    grn_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: Optional[str] = None
    # received_quantity from the GRN that triggered this invoice
    quantity: float = 0
    unit_price: float = 0
    # total_amount stored in DB, exposed as `amount` in the API
    amount: float = Field(0, alias="total_amount")
    status: PurchaseInvoiceStatus
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,  # allow setting by field name OR alias
    }


class InvoiceListResponse(BaseModel):
    items: List[InvoiceResponse]
    total: int
