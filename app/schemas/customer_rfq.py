# =============================================================================
# app/schemas/customer_rfq.py
# -----------------------------------------------------------------------------
# Request/response schemas for the Customer RFQ module — a request for
# pricing received FROM a customer, manually logged (no email/portal
# ingestion), as distinct from the outbound RFQ Kytos sends TO suppliers.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date as _Date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CustomerRFQStatus


class CustomerRFQCreate(BaseModel):
    customer_reference: str = Field(..., min_length=1, max_length=100, description="The customer's own reference number for this request")
    customer_name: str = Field(..., min_length=1, max_length=255)
    source: Optional[str] = Field(None, max_length=100, description="e.g. 'SAP Ariba', 'Email'")
    date_received: Optional[_Date] = None
    subject: Optional[str] = Field(None, description="What the customer is asking for")
    crm_lead_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class CustomerRFQStatusUpdate(BaseModel):
    status: CustomerRFQStatus


class CustomerRFQResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_reference: str
    customer_name: str
    source: Optional[str]
    date_received: Optional[_Date]
    subject: Optional[str]
    status: CustomerRFQStatus
    crm_lead_id: Optional[uuid.UUID]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class CustomerRFQListResponse(BaseModel):
    items: List[CustomerRFQResponse]
    total: int
