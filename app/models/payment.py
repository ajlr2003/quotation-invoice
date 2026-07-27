from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import AuditMixin


class Payment(AuditMixin, Base):
    """Records a payment attempt / completion against a SalesQuotation.

    One quotation can have multiple attempts but only one succeeds (status='paid').
    Gateway-specific IDs are stored for reconciliation and refunds.
    """

    __tablename__ = "payments"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sales_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # stripe | paypal
    gateway: Mapped[str] = mapped_column(String(20), nullable=False)

    # Stripe: Checkout Session ID (cs_...)  |  PayPal: Order ID
    gateway_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Stripe: PaymentIntent ID (pi_...)  |  PayPal: Capture ID
    gateway_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)

    # pending | paid | failed | refunded
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Payment {self.gateway} {self.status} {self.amount} {self.currency}>"
