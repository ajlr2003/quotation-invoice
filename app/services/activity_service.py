# =============================================================================
# app/services/activity_service.py
# -----------------------------------------------------------------------------
# Generic activity-timeline logging, used as a side effect of real mutations
# in other services (RFQ, Supplier, SalesQuotation, CrmLead). log_activity()
# only adds to the session — it deliberately doesn't flush/commit, so callers
# can log as part of their existing transaction.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEntityType
from app.schemas.activity import ActivityLogListResponse, ActivityLogResponse


def log_activity(
    db: AsyncSession,
    entity_type: ActivityEntityType,
    entity_id: uuid.UUID,
    action: str,
    message: str,
    user_id: Optional[uuid.UUID] = None,
) -> None:
    """Queue a timeline entry on the current session (caller flushes/commits).

    Args:
        db:          Active async database session.
        entity_type: Which kind of entity this entry belongs to.
        entity_id:   UUID of the specific entity instance.
        action:      Short machine-readable key, e.g. "created", "approved".
        message:     Human-readable description shown in the timeline.
        user_id:     UUID of the acting user, if any (system actions omit this).
    """
    db.add(ActivityLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        message=message,
        user_id=user_id,
    ))


async def list_activity(
    db: AsyncSession,
    entity_type: ActivityEntityType,
    entity_id: uuid.UUID,
) -> ActivityLogListResponse:
    """Return the full timeline for an entity, most recent first.

    Args:
        db:          Active async database session.
        entity_type: Which kind of entity to look up.
        entity_id:   UUID of the specific entity instance.

    Returns:
        ActivityLogListResponse containing matching entries and their count.
    """
    result = await db.execute(
        select(ActivityLog)
        .where(
            ActivityLog.entity_type == entity_type,
            ActivityLog.entity_id == entity_id,
        )
        .options(selectinload(ActivityLog.user))
        .order_by(ActivityLog.created_at.desc())
    )
    entries = result.scalars().all()
    return ActivityLogListResponse(
        items=[ActivityLogResponse.model_validate(e) for e in entries],
        total=len(entries),
    )
