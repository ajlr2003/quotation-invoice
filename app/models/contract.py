# =============================================================================
# app/models/contract.py
# -----------------------------------------------------------------------------
# ORM models for the Contracts module — tracks a customer Purchase Order as a
# "contract" broken into billing milestones (Advance, DEP, FAT, Delivery, …),
# each with its own percentage, amount, due date and invoicing/receipt status.
# This is the payment-collection tracker used internally, separate from
# SalesOrder (fulfillment) and SalesInvoice (the actual tax invoice) — a
# contract's milestones typically correspond to invoices raised over time as
# the PO is delivered.
#
#   contracts             — one row per tracked PO
#   contract_milestones   — the billing stages under a contract
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import ContractMilestoneStatus, ContractRiskStatus

if TYPE_CHECKING:
    pass


class Contract(AuditMixin, Base):
    """A tracked customer Purchase Order (``contracts``)."""

    __tablename__ = "contracts"

    file_ref: Mapped[str] = mapped_column(String(100), nullable=False, index=True)   # "Alsinan File Ref"
    customer: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    po_number: Mapped[Optional[str]] = mapped_column(String(100))
    po_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    po_date: Mapped[Optional[date]] = mapped_column(Date)
    po_expiry_date: Mapped[Optional[date]] = mapped_column(Date)

    title: Mapped[Optional[str]] = mapped_column(Text)
    # Falls back to po_value when unset — see ContractResponse / effective_value.
    contract_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    risk: Mapped[ContractRiskStatus] = mapped_column(
        Enum(ContractRiskStatus, name="contract_risk_status"),
        default=ContractRiskStatus.ON_TRACK,
        nullable=False,
    )

    milestones: Mapped[List["ContractMilestone"]] = relationship(
        "ContractMilestone",
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="ContractMilestone.created_at",
    )

    @property
    def effective_value(self) -> float:
        """Contract value if set, otherwise the PO value — mirrors the UI's
        long-standing `c.contractValue || c.poValue` fallback."""
        return float(self.contract_value) if self.contract_value is not None else float(self.po_value or 0)

    def __repr__(self) -> str:
        return f"<Contract {self.file_ref} customer={self.customer!r}>"


class ContractMilestone(AuditMixin, Base):
    """A billing stage under a Contract (``contract_milestones``)."""

    __tablename__ = "contract_milestones"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[ContractMilestoneStatus] = mapped_column(
        Enum(ContractMilestoneStatus, name="contract_milestone_status"),
        default=ContractMilestoneStatus.PENDING,
        nullable=False,
        index=True,
    )

    planned_date: Mapped[Optional[date]] = mapped_column(Date)
    achieved_date: Mapped[Optional[date]] = mapped_column(Date)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100))
    invoice_date: Mapped[Optional[date]] = mapped_column(Date)
    received_date: Mapped[Optional[date]] = mapped_column(Date)

    contract: Mapped["Contract"] = relationship("Contract", back_populates="milestones")

    def __repr__(self) -> str:
        return f"<ContractMilestone {self.name} status={self.status}>"
