# =============================================================================
# app/schemas/activity.py
# -----------------------------------------------------------------------------
# Request/response schemas for the generic activity timeline endpoint.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import ActivityEntityType


class ActivityLogResponse(BaseModel):
    """A single timeline entry, e.g. 'Abdulrahman sent RFQ to 3 suppliers'."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: ActivityEntityType
    entity_id: uuid.UUID
    action: str
    message: str
    user_id: Optional[uuid.UUID]
    user_name: Optional[str] = None
    created_at: datetime


class ActivityLogListResponse(BaseModel):
    items: List[ActivityLogResponse]
    total: int
