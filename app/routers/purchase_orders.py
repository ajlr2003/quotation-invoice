# =============================================================================
# app/routers/purchase_orders.py
# -----------------------------------------------------------------------------
# HTTP endpoints for Purchase Orders.
#
# GET   /api/v1/purchase-orders/       — paginated list of all POs
# POST  /api/v1/purchase-orders/       — create a PO for an awarded RFQ
# GET   /api/v1/purchase-orders/{id}   — full PO detail with pricing/qty
# =============================================================================

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderListResponse,
    PurchaseOrderResponse,
)
from app.services import purchase_order_service

router = APIRouter()

_purchase_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.PURCHASER)


@router.get(
    "",
    response_model=PurchaseOrderListResponse,
    summary="List all purchase orders",
)
async def list_purchase_orders(
    supplier_id: Optional[uuid.UUID] = Query(default=None, description="Filter to POs issued to this supplier"),
    rfq_id: Optional[uuid.UUID] = Query(default=None, description="Filter to POs raised from this RFQ"),
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Return all purchase orders ordered by creation date descending, including supplier name."""
    return await purchase_order_service.list_purchase_orders(db, supplier_id=supplier_id, rfq_id=rfq_id)


@router.post(
    "",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a purchase order for an awarded RFQ",
)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(_purchase_roles),
):
    """
    Issue a purchase order against an awarded RFQ.

    **Rules:**
    - RFQ must be in **AWARDED** status.
    - The supplier must already be linked to the RFQ.
    - Only one PO is allowed per RFQ/supplier pair.
    - `total_price` is seeded from the supplier's quotation; `unit_price = total_price / ordered_quantity`.
    """
    return await purchase_order_service.create_purchase_order(db, payload)


@router.get(
    "/{po_id}",
    response_model=PurchaseOrderResponse,
    summary="Get a purchase order by ID",
)
async def get_purchase_order(
    po_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Return a single purchase order by its UUID, including:
    - `ordered_quantity`, `received_quantity`, `remaining_quantity` (computed)
    - `unit_price`, `total_price`
    - `supplier_name`
    """
    return await purchase_order_service.get_purchase_order(db, po_id)
