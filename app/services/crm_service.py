# =============================================================================
# app/services/crm_service.py
# -----------------------------------------------------------------------------
# Business logic for the CRM module: lead CRUD, pipeline stage transitions,
# and KPI aggregation. All DB writes use SQLAlchemy async sessions.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_lead import CrmLead
from app.models.enums import CrmLeadStage
from app.schemas.crm import (
    CrmKPIResponse,
    CrmLeadCreate,
    CrmLeadListResponse,
    CrmLeadResponse,
    CrmLeadStageUpdate,
)


# =============================================================================
# KPIs
# =============================================================================

async def get_kpis(db: AsyncSession) -> CrmKPIResponse:
    """Compute dashboard KPIs from the live leads table.

    Args:
        db: Async database session.

    Returns:
        CrmKPIResponse with total_leads, pipeline_value, win_rate, and
        conversion_rate expressed as percentages (0–100).
    """
    total: int = (await db.execute(select(func.count()).select_from(CrmLead))).scalar_one()

    # Pipeline value = sum of deal_value for non-won leads
    pipeline_value: float = (
        await db.execute(
            select(func.coalesce(func.sum(CrmLead.deal_value), 0)).where(
                CrmLead.stage != CrmLeadStage.CLOSED_WON
            )
        )
    ).scalar_one()

    won_count: int = (
        await db.execute(
            select(func.count()).select_from(CrmLead).where(
                CrmLead.stage == CrmLeadStage.CLOSED_WON
            )
        )
    ).scalar_one()

    # Conversion = leads that progressed past "new_leads" stage
    converted_count: int = (
        await db.execute(
            select(func.count()).select_from(CrmLead).where(
                CrmLead.stage != CrmLeadStage.NEW_LEADS
            )
        )
    ).scalar_one()

    win_rate = round((won_count / total * 100), 1) if total else 0.0
    conversion_rate = round((converted_count / total * 100), 1) if total else 0.0

    return CrmKPIResponse(
        total_leads=total,
        pipeline_value=float(pipeline_value),
        win_rate=win_rate,
        conversion_rate=conversion_rate,
    )


# =============================================================================
# Lead CRUD
# =============================================================================

async def list_leads(db: AsyncSession) -> CrmLeadListResponse:
    """Return all CRM leads ordered by creation date descending.

    Args:
        db: Async database session.

    Returns:
        CrmLeadListResponse containing the full lead list and a total count.
    """
    result = await db.execute(select(CrmLead).order_by(CrmLead.created_at.desc()))
    leads = list(result.scalars().all())
    return CrmLeadListResponse(
        items=[CrmLeadResponse.model_validate(l) for l in leads],
        total=len(leads),
    )


async def create_lead(db: AsyncSession, payload: CrmLeadCreate) -> CrmLeadResponse:
    """Create a new CRM lead.

    Args:
        db:      Async database session.
        payload: Validated lead creation payload.

    Returns:
        CrmLeadResponse for the newly created lead.
    """
    lead = CrmLead(**payload.model_dump())
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return CrmLeadResponse.model_validate(lead)


async def update_stage(
    db: AsyncSession, lead_id: uuid.UUID, payload: CrmLeadStageUpdate
) -> CrmLeadResponse:
    """Move a lead to a new pipeline stage.

    Args:
        db:      Async database session.
        lead_id: UUID of the lead to update.
        payload: Contains the target ``stage`` value.

    Returns:
        Updated CrmLeadResponse.

    Raises:
        HTTPException 404: If no lead with ``lead_id`` exists.
    """
    lead = await db.get(CrmLead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    lead.stage = payload.stage
    await db.commit()
    await db.refresh(lead)
    return CrmLeadResponse.model_validate(lead)


async def delete_lead(db: AsyncSession, lead_id: uuid.UUID) -> None:
    """Permanently delete a CRM lead.

    Args:
        db:      Async database session.
        lead_id: UUID of the lead to delete.

    Raises:
        HTTPException 404: If no lead with ``lead_id`` exists.
    """
    lead = await db.get(CrmLead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await db.delete(lead)
    await db.commit()
