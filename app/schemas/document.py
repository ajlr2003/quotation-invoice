from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    original_filename: str
    mime_type: str
    file_size_bytes: Optional[int]
    document_type: str
    description: Optional[str]
    entity_type: Optional[str]
    entity_id: Optional[uuid.UUID]
    version: int
    uploaded_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int


class DocumentKPIs(BaseModel):
    total_documents: int
    total_size_bytes: int
    by_type: dict[str, int]
