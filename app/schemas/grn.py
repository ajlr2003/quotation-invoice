"""
app/schemas/grn.py
Pydantic schemas for Goods Receipt Note (GRN).
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class GRNCreate(BaseModel):
    po_id: uuid.UUID
    received_quantity: int = Field(gt=0, description="Must be greater than zero")


class GRNResponse(BaseModel):
    id: uuid.UUID
    po_id: uuid.UUID
    supplier_name: str
    po_reference: Optional[str] = None
    received_quantity: int
    created_at: datetime

    model_config = {"from_attributes": True}


class GRNListResponse(BaseModel):
    items: List[GRNResponse]
    total: int
