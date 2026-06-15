# =============================================================================
# app/schemas/crm.py
# -----------------------------------------------------------------------------
# Pydantic v2 request/response schemas for the CRM module.
# Covers leads CRUD, pipeline stage transitions, and dashboard KPIs.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CrmLeadStage


# =============================================================================
# Lead schemas
# =============================================================================

class CrmLeadCreate(BaseModel):
    """Payload for creating a new CRM lead."""

    company: str = Field(..., min_length=1, max_length=255, description="Company / account name")
    contact_person: str = Field(..., min_length=1, max_length=255, description="Primary contact full name")
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    deal_value: Optional[float] = Field(None, ge=0, description="Estimated deal value in the default currency")
    industry: Optional[str] = Field(None, max_length=255, description="Industry or solution type, e.g. 'ERP Implementation'")
    source: Optional[str] = Field(None, max_length=100, description="Lead source: website, referral, cold_outreach, trade_show, linkedin")
    owner: Optional[str] = Field(None, max_length=255, description="Salesperson name responsible for this lead")
    stage: CrmLeadStage = Field(CrmLeadStage.NEW_LEADS, description="Initial pipeline stage")
    notes: Optional[str] = None


class CrmLeadStageUpdate(BaseModel):
    """Payload for moving a lead to a new pipeline stage."""

    stage: CrmLeadStage = Field(..., description="Target pipeline stage")


class CrmLeadResponse(BaseModel):
    """Full lead representation returned by list and detail endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company: str
    contact_person: str
    email: Optional[str]
    phone: Optional[str]
    deal_value: Optional[float]
    industry: Optional[str]
    source: Optional[str]
    owner: Optional[str]
    stage: CrmLeadStage
    quote_number: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class CrmLeadListResponse(BaseModel):
    """Paginated list of CRM leads."""

    items: List[CrmLeadResponse]
    total: int


# =============================================================================
# KPI schema
# =============================================================================

class CrmKPIResponse(BaseModel):
    """Dashboard KPI snapshot for the CRM pipeline.

    Fields:
        total_leads:      Total number of leads across all stages.
        pipeline_value:   Sum of deal_value for active (non-won) leads.
        win_rate:         Percentage of all leads that reached closed_won.
        conversion_rate:  Percentage of leads that progressed past new_leads.
    """

    total_leads: int
    pipeline_value: float
    win_rate: float        # 0–100
    conversion_rate: float  # 0–100
