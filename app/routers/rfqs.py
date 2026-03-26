"""
app/routers/rfqs.py

RFQ endpoints:
  POST   /api/v1/rfqs                          — create RFQ
  GET    /api/v1/rfqs                          — list RFQs (paginated + filters)
  GET    /api/v1/rfqs/{rfq_id}                 — get RFQ detail
  PATCH  /api/v1/rfqs/{rfq_id}                 — update RFQ (fields + status)
  DELETE /api/v1/rfqs/{rfq_id}                 — delete RFQ (DRAFT only)

RFQ Item endpoints:
  POST   /api/v1/rfqs/{rfq_id}/items           — add item to RFQ
  GET    /api/v1/rfqs/{rfq_id}/items           — list items on RFQ
  DELETE /api/v1/rfqs/{rfq_id}/items/{item_id} — remove item from RFQ

All endpoints require JWT authentication.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.enums import RFQStatus
from app.schemas.rfq import (
    RFQCreateRequest,
    RFQItemCreateRequest,
    RFQItemListResponse,
    RFQItemResponse,
    RFQListResponse,
    RFQResponse,
    RFQUpdateRequest,
)
from app.services import rfq_service

router = APIRouter()


# ============================================================================
# RFQ endpoints
# ============================================================================

@router.post(
    "/",
    response_model=RFQResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new RFQ",
)
async def create_rfq(
    payload: RFQCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new Request for Quotation.
    The RFQ is assigned to the authenticated user and starts in DRAFT status.
    You can optionally include line items in the request body.
    """
    return await rfq_service.create_rfq(db, payload, current_user)


@router.get(
    "/",
    response_model=RFQListResponse,
    summary="List RFQs",
)
async def list_rfqs(
    page: int               = Query(default=1, ge=1),
    page_size: int          = Query(default=20, ge=1, le=100),
    search: Optional[str]   = Query(default=None, description="Search by number, title, or description"),
    status: Optional[RFQStatus] = Query(default=None, description="Filter by status"),
    my_rfqs_only: bool      = Query(default=False, description="Show only RFQs created by me"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return paginated list of RFQs.
    Supports filtering by status, and optionally showing only the current user's RFQs.
    """
    return await rfq_service.list_rfqs(
        db=db,
        current_user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        status_filter=status,
        my_rfqs_only=my_rfqs_only,
    )


@router.get(
    "/{rfq_id}",
    response_model=RFQResponse,
    summary="Get RFQ by ID",
)
async def get_rfq(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Fetch a single RFQ with all its line items and creator info."""
    return await rfq_service.get_rfq(db, rfq_id)


@router.patch(
    "/{rfq_id}",
    response_model=RFQResponse,
    summary="Update RFQ",
)
async def update_rfq(
    rfq_id: uuid.UUID,
    payload: RFQUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Partially update an RFQ.

    **Field edits** (title, description, dates, currency) are only allowed in DRAFT status.

    **Status transitions** allowed:
    - `draft` → `sent` or `cancelled`
    - `sent` → `received` or `cancelled`
    - `received` → `evaluated` or `cancelled`
    - `evaluated` → `closed` or `cancelled`
    """
    return await rfq_service.update_rfq(db, rfq_id, payload, current_user)


@router.delete(
    "/{rfq_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete RFQ",
)
async def delete_rfq(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Permanently delete an RFQ and all its line items.
    Only RFQs in **DRAFT** status can be deleted.
    """
    return await rfq_service.delete_rfq(db, rfq_id, current_user)


# ============================================================================
# RFQ Item endpoints
# ============================================================================

@router.post(
    "/{rfq_id}/items",
    response_model=RFQItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add item to RFQ",
)
async def add_rfq_item(
    rfq_id: uuid.UUID,
    payload: RFQItemCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Add a new line item to an existing RFQ.
    The line number is assigned automatically.
    Only allowed when RFQ is in **DRAFT** status.
    """
    return await rfq_service.add_rfq_item(db, rfq_id, payload, current_user)


@router.get(
    "/{rfq_id}/items",
    response_model=RFQItemListResponse,
    summary="List items on an RFQ",
)
async def list_rfq_items(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Return all line items for a given RFQ, ordered by line number."""
    return await rfq_service.list_rfq_items(db, rfq_id)


@router.delete(
    "/{rfq_id}/items/{item_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove item from RFQ",
)
async def delete_rfq_item(
    rfq_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Remove a line item from an RFQ and re-sequence remaining line numbers.
    Only allowed when RFQ is in **DRAFT** status.
    Items with existing supplier quotes cannot be deleted.
    """
    return await rfq_service.delete_rfq_item(db, rfq_id, item_id, current_user)
