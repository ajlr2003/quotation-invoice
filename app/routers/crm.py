# =============================================================================
# app/routers/crm.py
# -----------------------------------------------------------------------------
# FastAPI route handlers for the CRM module.
# All routes are mounted under /api/v1/crm by app/main.py.
#
# Endpoint summary:
#   GET  /kpis                    — dashboard KPI snapshot
#   GET  /leads                   — list all leads
#   POST /leads                   — create a new lead
#   PATCH /leads/{id}/stage       — move a lead to a new pipeline stage
#   DELETE /leads/{id}            — delete a lead
#
# All routes require a valid Bearer JWT (get_current_user dependency).
# =============================================================================

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.crm import (
    CrmKPIResponse,
    CrmLeadCreate,
    CrmLeadListResponse,
    CrmLeadResponse,
    CrmLeadStageUpdate,
)
from app.services import crm_service

router = APIRouter()


# =============================================================================
# KPIs
# =============================================================================

@router.get(
    "/kpis",
    response_model=CrmKPIResponse,
    summary="CRM dashboard KPIs",
    description=(
        "Returns a real-time snapshot of CRM metrics: total lead count, "
        "active pipeline value (sum of deal values for non-won leads), "
        "win rate (% of leads closed won), and conversion rate "
        "(% of leads that progressed past the initial New Leads stage)."
    ),
)
async def get_kpis(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await crm_service.get_kpis(db)


# =============================================================================
# Leads
# =============================================================================

@router.get(
    "/leads",
    response_model=CrmLeadListResponse,
    summary="List all CRM leads",
    description="Returns all leads ordered by creation date descending.",
)
async def list_leads(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await crm_service.list_leads(db)


@router.post(
    "/leads",
    response_model=CrmLeadResponse,
    status_code=201,
    summary="Create a new CRM lead",
    description=(
        "Adds a new lead to the pipeline. "
        "Company and contact_person are required. "
        "Stage defaults to 'new_leads' if not provided."
    ),
)
async def create_lead(
    payload: CrmLeadCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await crm_service.create_lead(db, payload)


@router.patch(
    "/leads/{lead_id}/stage",
    response_model=CrmLeadResponse,
    summary="Move a lead to a new pipeline stage",
    description=(
        "Updates the pipeline stage of the given lead. "
        "Valid stages: new_leads, qualified, proposal, closed_won. "
        "Returns 404 if the lead does not exist."
    ),
)
async def update_lead_stage(
    lead_id: uuid.UUID,
    payload: CrmLeadStageUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await crm_service.update_stage(db, lead_id, payload)


@router.delete(
    "/leads/{lead_id}",
    status_code=204,
    summary="Delete a CRM lead",
    description="Permanently removes the lead from the pipeline. Returns 404 if not found.",
)
async def delete_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    await crm_service.delete_lead(db, lead_id)
