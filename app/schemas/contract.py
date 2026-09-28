# =============================================================================
# app/schemas/contract.py
# -----------------------------------------------------------------------------
# Pydantic request/response schemas for the Contracts (PO payment-milestone
# tracker) module. Field names use snake_case even though the original
# localStorage-only version of this module used camelCase in the browser —
# the frontend maps between the two, same as every other module.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date as _Date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ContractMilestoneStatus, ContractRiskStatus


# ── Milestones ────────────────────────────────────────────────────────────────

class ContractMilestoneCreate(BaseModel):
    """One billing stage under a contract."""

    name: str = Field(min_length=1, max_length=255)
    pct: float = Field(default=0, ge=0, le=100)
    amount: float = Field(default=0, ge=0)
    due_date: Optional[_Date] = None
    status: ContractMilestoneStatus = ContractMilestoneStatus.PENDING
    planned_date: Optional[_Date] = None
    achieved_date: Optional[_Date] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[_Date] = None
    received_date: Optional[_Date] = None


class ContractMilestoneResponse(ContractMilestoneCreate):
    id: uuid.UUID
    contract_id: uuid.UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Contracts ─────────────────────────────────────────────────────────────────

class ContractCreate(BaseModel):
    """A tracked Purchase Order. Milestones are managed via their own
    endpoints once the contract exists, not nested in this payload."""

    file_ref: str = Field(min_length=1, max_length=100)
    customer: str = Field(min_length=1, max_length=255)
    po_number: Optional[str] = None
    po_value: float = Field(default=0, ge=0)
    po_date: Optional[_Date] = None
    po_expiry_date: Optional[_Date] = None
    title: Optional[str] = None
    contract_value: Optional[float] = Field(default=None, ge=0)
    risk: ContractRiskStatus = ContractRiskStatus.ON_TRACK


class ContractUpdate(ContractCreate):
    """Same fields as create; kept separate so the two can diverge."""


class ContractResponse(BaseModel):
    id: uuid.UUID
    file_ref: str
    customer: str
    po_number: Optional[str] = None
    po_value: float
    po_date: Optional[_Date] = None
    po_expiry_date: Optional[_Date] = None
    title: Optional[str] = None
    contract_value: Optional[float] = None
    effective_value: float   # contract_value if set, else po_value
    risk: ContractRiskStatus
    milestones: List[ContractMilestoneResponse] = []
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ContractListResponse(BaseModel):
    items: List[ContractResponse]
    total: int


class ContractKPIs(BaseModel):
    """Headline totals across every tracked contract, in SAR."""

    total_contract_value: float
    received: float
    invoiced_pending: float
    not_yet_invoiced: float
    overdue: float
