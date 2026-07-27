# =============================================================================
# app/routers/activity.py
# -----------------------------------------------------------------------------
# HTTP endpoint for the generic activity timeline ("chatter").
#
# GET /api/v1/activity?entity_type=X&entity_id=Y — timeline for one entity
# =============================================================================

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.enums import ActivityEntityType
from app.schemas.activity import ActivityLogListResponse
from app.services import activity_service

router = APIRouter()


@router.get(
    "",
    response_model=ActivityLogListResponse,
    summary="Get the activity timeline for an entity",
)
async def list_activity(
    entity_type: ActivityEntityType = Query(..., description="Entity type, e.g. 'rfq', 'supplier'"),
    entity_id: uuid.UUID = Query(..., description="UUID of the entity"),
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Return every logged activity entry for one entity, most recent first."""
    return await activity_service.list_activity(db, entity_type, entity_id)
