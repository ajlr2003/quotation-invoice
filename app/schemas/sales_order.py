# =============================================================================
# app/schemas/sales_order.py
# -----------------------------------------------------------------------------
# Pydantic request/response schemas for the Sales Order endpoints. A
# SalesOrder is created by supplying the UUID of an accepted SalesQuotation;
# all other fields are populated by copying data from the quotation.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ── Item response ─────────────────────────────────────────────────────────────

class SalesOrderItemResponse(BaseModel):
    """Response schema for a single SalesOrder line item."""

    id: uuid.UUID
    order_id: uuid.UUID
    line_no: int
    catalog_no: Optional[str] = None
    item_name: Optional[str] = None
    description: Optional[str] = None
    qty: float
    unit: str
    unit_price: float
    discount: float
    net_price: float
    total: float
    model_config = ConfigDict(from_attributes=True)


# ── Create ────────────────────────────────────────────────────────────────────

class SalesOrderCreate(BaseModel):
    """Request body for creating a SalesOrder from an accepted SalesQuotation.

    Only the source quotation UUID is required; all order details are copied
    from that quotation by the service layer.
    """

    quotation_id: uuid.UUID


# ── Response ──────────────────────────────────────────────────────────────────

class SalesOrderResponse(BaseModel):
    """Full response schema for a SalesOrder including all line items."""

    id: uuid.UUID
    order_number: str
    quotation_id: Optional[uuid.UUID] = None
    customer_name: Optional[str] = None
    department: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    subject: Optional[str] = None
    currency: str
    payment_terms: Optional[str] = None
    delivery_location: Optional[str] = None
    subtotal: float
    vat: float
    total: float
    remarks: Optional[str] = None
    status: str
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    updated_by: Optional[uuid.UUID] = None
    items: List[SalesOrderItemResponse] = []
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SalesOrderListResponse(BaseModel):
    """Paginated list response wrapping multiple SalesOrder records."""

    items: List[SalesOrderResponse]
    total: int


# ── Status update ─────────────────────────────────────────────────────────────

class SalesOrderStatusUpdate(BaseModel):
    """Request body for advancing a SalesOrder through the fulfillment workflow.

    Allowed values: ``"confirmed"`` → ``"shipped"`` → ``"delivered"``
    """

    status: str  # "confirmed" | "shipped" | "delivered"
