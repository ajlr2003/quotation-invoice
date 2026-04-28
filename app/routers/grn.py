"""
app/routers/grn.py

Goods Receipt Note endpoints:
  POST /api/v1/grn/  — record goods received against a PO
  GET  /api/v1/grn/  — list all GRNs
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.grn import GRNCreate, GRNListResponse, GRNResponse
from app.services import grn_service

router = APIRouter()

@router.post(
    "",
    response_model=GRNResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record goods received against a purchase order",
)
async def create_grn(
    payload: GRNCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Create a Goods Receipt Note for a Purchase Order.

    **Rules:**
    - PO must exist.
    - received_quantity must be greater than zero.
    """
    return await grn_service.create_grn(db, payload)


@router.get(
    "",
    response_model=GRNListResponse,
    summary="List goods receipt notes",
)
async def list_grns(
    po_id: Optional[uuid.UUID] = Query(None, description="Filter by purchase order ID"),
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Return GRNs ordered by creation date descending. Pass `po_id` to filter by PO."""
    return await grn_service.list_grns(db, po_id=po_id)
