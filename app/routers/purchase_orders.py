"""
app/routers/purchase_orders.py

Purchase order endpoints:
  POST /api/v1/purchase-orders/   — create a PO for an awarded RFQ
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderResponse
from app.services import purchase_order_service

router = APIRouter(redirect_slashes=False)


@router.post(
    "/",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a purchase order for an awarded RFQ",
)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Issue a purchase order against an awarded RFQ.

    **Rules:**
    - RFQ must be in **AWARDED** status.
    - The supplier must already be linked to the RFQ.
    - Only one PO is allowed per RFQ/supplier pair.
    """
    return await purchase_order_service.create_purchase_order(db, payload)
