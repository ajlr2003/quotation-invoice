from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StripeSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class PayPalOrderResponse(BaseModel):
    order_id: str
    approve_url: str


class PayPalCaptureRequest(BaseModel):
    order_id: str
    quotation_id: uuid.UUID


class PaymentStatusResponse(BaseModel):
    id: uuid.UUID
    quotation_id: uuid.UUID
    gateway: str
    gateway_session_id: Optional[str]
    gateway_ref: Optional[str]
    amount: float
    currency: str
    status: str
    paid_at: Optional[datetime]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
