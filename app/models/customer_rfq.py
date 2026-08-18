# =============================================================================
# app/models/customer_rfq.py
# -----------------------------------------------------------------------------
# ORM model for a Customer RFQ — a request for pricing RECEIVED FROM a
# customer (via a portal such as SAP Ariba, or email), as distinct from the
# RFQ model in app/models/rfq.py, which Kytos SENDS OUT to suppliers.
#
# There is no automatic ingestion of customer emails/portal messages — this
# is a manually-logged record of "customer X asked for a quote on Y". A
# Sales Quotation can link to it (SalesQuotation.customer_rfq_id) so the
# quotation traces back to what the customer actually asked for, rather than
# to the (unrelated) outbound RFQ Kytos may or may not have sent a supplier
# to source pricing for it.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date as _Date
from typing import Optional

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import CustomerRFQStatus


class CustomerRFQ(AuditMixin, Base):
    """A request for pricing received from a customer.

    Table: ``customer_rfqs``

    Lifecycle (see ``CustomerRFQStatus``): ``open`` -> ``quoted`` -> ``closed``.
    Moves to ``quoted`` automatically when a Sales Quotation is created
    against it; ``closed`` is a manual action.
    """

    __tablename__ = "customer_rfqs"

    # ── Identity ──────────────────────────────────────────────────────────────
    # The customer's own reference number for this request (e.g. their SAP
    # Ariba number, or whatever they quote in the email) — not globally
    # unique, since different customers may reuse numbering schemes.
    customer_reference: Mapped[str] = mapped_column(String(100), index=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # How the request arrived — free text (e.g. "SAP Ariba", "Email"),
    # not an enum, since customers use varying portals/channels.
    source: Mapped[Optional[str]] = mapped_column(String(100))
    date_received: Mapped[Optional[_Date]] = mapped_column(Date)

    subject: Mapped[Optional[str]] = mapped_column(Text)  # what they're asking for

    status: Mapped[CustomerRFQStatus] = mapped_column(
        Enum(CustomerRFQStatus, name="customer_rfq_status"),
        nullable=False,
        default=CustomerRFQStatus.OPEN,
    )

    crm_lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("crm_leads.id"), nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return (
            f"<CustomerRFQ id={self.id} ref={self.customer_reference!r} "
            f"customer={self.customer_name!r} status={self.status}>"
        )
