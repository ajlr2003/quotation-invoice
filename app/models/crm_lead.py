# =============================================================================
# app/models/crm_lead.py
# -----------------------------------------------------------------------------
# ORM model for a CRM Lead / Opportunity. A lead progresses through pipeline
# stages (new_leads → qualified → proposal → closed_won) and may be linked to
# a SalesQuotation via quote_number for full traceability from first contact
# through to confirmed order.
# =============================================================================

from __future__ import annotations

from typing import Optional

from sqlalchemy import Enum, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import CrmLeadStage


class CrmLead(AuditMixin, Base):
    """A sales lead or opportunity tracked in the CRM pipeline.

    Table: ``crm_leads``

    Lifecycle stages (see ``CrmLeadStage``):
    ``new_leads`` → ``qualified`` → ``proposal`` → ``closed_won``

    The ``quote_number`` field links this lead to a ``SalesQuotation`` once a
    formal quotation is raised, enabling traceability from first contact
    through quotation and order execution.
    """

    __tablename__ = "crm_leads"

    # ── Identity ──────────────────────────────────────────────────────────────
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_person: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))

    # ── Commercial ────────────────────────────────────────────────────────────
    deal_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    industry: Mapped[Optional[str]] = mapped_column(String(255))   # UI "type" field
    source: Mapped[Optional[str]] = mapped_column(String(100))     # website / referral / etc.
    owner: Mapped[Optional[str]] = mapped_column(String(255))      # salesperson name

    # ── Pipeline ──────────────────────────────────────────────────────────────
    stage: Mapped[CrmLeadStage] = mapped_column(
        Enum(CrmLeadStage, name="crm_lead_stage"),
        nullable=False,
        default=CrmLeadStage.NEW_LEADS,
    )

    # ── Quotation link (Enhancement 3 — Quotation Number Integration) ─────────
    # Populated when a SalesQuotation is raised for this lead so the pipeline
    # card can display the quote reference and allow quick navigation.
    quote_number: Mapped[Optional[str]] = mapped_column(String(50), index=True)

    notes: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return (
            f"<CrmLead id={self.id} company={self.company!r} "
            f"stage={self.stage} value={self.deal_value}>"
        )
