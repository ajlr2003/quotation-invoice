# =============================================================================
# app/services/crm_service.py
# -----------------------------------------------------------------------------
# Business logic for the CRM module: lead CRUD, pipeline stage transitions,
# and KPI aggregation. All DB writes use SQLAlchemy async sessions.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_lead import CrmLead
from app.models.enums import ActivityEntityType, CrmLeadStage
from app.models.rfq import RFQ
from app.schemas.crm import (
    CrmCallLogCreate,
    CrmKPIResponse,
    CrmLeadCreate,
    CrmLeadListResponse,
    CrmLeadResponse,
    CrmLeadStageUpdate,
    LeadRfqListResponse,
    LeadRfqSummary,
)
from app.services import activity_service


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


async def create_lead(
    db: AsyncSession, payload: CrmLeadCreate, user_id: Optional[uuid.UUID] = None
) -> CrmLeadResponse:
    """Create a new CRM lead.

    Args:
        db:      Async database session.
        payload: Validated lead creation payload.
        user_id: UUID of the acting user, if any.

    Returns:
        CrmLeadResponse for the newly created lead.
    """
    lead = CrmLead(**payload.model_dump())
    db.add(lead)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.CRM_LEAD, lead.id, "created",
        f"Lead '{lead.company}' added to pipeline",
        user_id=user_id,
    )
    await db.commit()
    await db.refresh(lead)
    return CrmLeadResponse.model_validate(lead)


async def update_stage(
    db: AsyncSession,
    lead_id: uuid.UUID,
    payload: CrmLeadStageUpdate,
    user_id: Optional[uuid.UUID] = None,
) -> CrmLeadResponse:
    """Move a lead to a new pipeline stage.

    Args:
        db:      Async database session.
        lead_id: UUID of the lead to update.
        payload: Contains the target ``stage`` value.
        user_id: UUID of the acting user, if any.

    Returns:
        Updated CrmLeadResponse.

    Raises:
        HTTPException 404: If no lead with ``lead_id`` exists.
    """
    lead = await db.get(CrmLead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    old_stage = lead.stage
    lead.stage = payload.stage
    if payload.stage != old_stage:
        activity_service.log_activity(
            db, ActivityEntityType.CRM_LEAD, lead.id, "stage_changed",
            f"Moved from {old_stage.value} to {payload.stage.value}",
            user_id=user_id,
        )
    await db.commit()
    await db.refresh(lead)
    return CrmLeadResponse.model_validate(lead)


async def log_call(
    db: AsyncSession,
    lead_id: uuid.UUID,
    payload: CrmCallLogCreate,
    user_id: Optional[uuid.UUID] = None,
) -> CrmLeadResponse:
    """Record a call against a lead as an activity-timeline entry.

    Args:
        db:      Async database session.
        lead_id: UUID of the lead the call was made about.
        payload: Call details (contact, duration, outcome, notes, follow-up).
        user_id: UUID of the acting user, if any.

    Returns:
        The lead as a CrmLeadResponse (unchanged; the call is recorded on
        the activity timeline, not on the lead itself).

    Raises:
        HTTPException 404: If no lead with ``lead_id`` exists.
    """
    lead = await db.get(CrmLead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    message = "Call logged"
    if payload.contact_person:
        message += f" with {payload.contact_person}"
    if payload.duration_minutes is not None:
        message += f" ({payload.duration_minutes} min)"
    if payload.outcome:
        message += f" — {payload.outcome}"
    if payload.notes:
        message += f": {payload.notes}"
    if payload.follow_up_date:
        message += f" (follow up {payload.follow_up_date})"

    activity_service.log_activity(
        db, ActivityEntityType.CRM_LEAD, lead.id, "call_logged",
        message,
        user_id=user_id,
    )
    await db.commit()
    await db.refresh(lead)
    return CrmLeadResponse.model_validate(lead)


async def list_lead_rfqs(db: AsyncSession, lead_id: uuid.UUID) -> LeadRfqListResponse:
    """Return every RFQ linked to a lead, most recent first.

    A lead's items are often split across several supplier RFQs, so this
    lets the lead detail screen show all of them in one place instead of
    hunting through the RFQ list.

    Args:
        db:      Async database session.
        lead_id: UUID of the lead.

    Returns:
        LeadRfqListResponse containing matching RFQs and their total count.

    Raises:
        HTTPException 404: If no lead with ``lead_id`` exists.
    """
    lead = await db.get(CrmLead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    result = await db.execute(
        select(RFQ).where(RFQ.crm_lead_id == lead_id).order_by(RFQ.created_at.desc())
    )
    rfqs = list(result.scalars().all())
    return LeadRfqListResponse(
        items=[LeadRfqSummary.model_validate(r) for r in rfqs],
        total=len(rfqs),
    )


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
