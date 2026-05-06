# =============================================================================
# app/routers/sales_orders.py
# -----------------------------------------------------------------------------
# FastAPI router for Sales Order endpoints. All routes are mounted under
# /api/v1/sales/orders by the application factory. Status transitions require
# ADMIN, MANAGER, or SALES roles; all other routes require any authenticated user.
#
# Routes:
#   POST /                   — create order from an accepted quotation
#   GET  /                   — list all sales orders
#   GET  /revenue            — total revenue from delivered orders
#   GET  /top-products       — top 3 products by revenue
#   PUT  /{id}/status        — advance fulfillment status
#   GET  /{id}               — get single sales order
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.sales_order import SalesOrderCreate, SalesOrderListResponse, SalesOrderResponse
from app.services import sales_order_service

# ── Role guard for status transitions ────────────────────────────────────────
_sales_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES)


# ── Local response models ─────────────────────────────────────────────────────

class RevenueResponse(BaseModel):
    """Response body for the total revenue endpoint."""
    total_revenue: float


class TopProductEntry(BaseModel):
    """A single product entry in the top-products response."""
    name: str
    revenue: float


class TopProductsResponse(BaseModel):
    """Response body for the top-products endpoint."""
    top_products: list[TopProductEntry]


class StatusUpdateRequest(BaseModel):
    """Request body for advancing a SalesOrder through the fulfillment workflow."""
    status: str


router = APIRouter()


# ── Create ────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=SalesOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a sales order from a quotation",
)
async def create_order(
    payload: SalesOrderCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> SalesOrderResponse:
    """Create a SalesOrder by converting an accepted SalesQuotation.

    Args:
        payload:      Request body containing the source ``quotation_id``.
        db:           Injected async database session.

    Returns:
        The newly created SalesOrder with status=CONFIRMED.

    Raises:
        HTTPException: 409 if the quotation is not in ACCEPTED status.
    """
    return await sales_order_service.create_from_quotation(db, payload)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=SalesOrderListResponse,
    summary="List all sales orders",
)
async def list_orders(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> SalesOrderListResponse:
    """Return all SalesOrders ordered by creation date descending.

    Args:
        db: Injected async database session.

    Returns:
        Paginated list of sales orders.
    """
    return await sales_order_service.list_orders(db)


# ── Statistics ────────────────────────────────────────────────────────────────

@router.get(
    "/revenue",
    response_model=RevenueResponse,
    summary="Total revenue from delivered sales orders",
)
async def get_revenue(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> RevenueResponse:
    """Return the sum of ``total`` across all DELIVERED SalesOrders.

    Args:
        db: Injected async database session.

    Returns:
        Total revenue figure.
    """
    total = await sales_order_service.get_total_revenue(db)
    return RevenueResponse(total_revenue=total)


@router.get(
    "/top-products",
    response_model=TopProductsResponse,
    summary="Top 3 products by revenue across all sales orders",
)
async def get_top_products(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> TopProductsResponse:
    """Return the top 3 products ranked by total revenue.

    Args:
        db: Injected async database session.

    Returns:
        List of up to 3 products with their aggregated revenue.
    """
    products = await sales_order_service.get_top_products(db)
    return TopProductsResponse(top_products=products)


# ── Status transition ─────────────────────────────────────────────────────────

@router.put(
    "/{order_id}/status",
    response_model=SalesOrderResponse,
    summary="Advance sales order status: confirmed → shipped → delivered",
)
async def update_order_status(
    order_id: uuid.UUID,
    payload: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_sales_roles),
) -> SalesOrderResponse:
    """Advance a SalesOrder one step through the fulfillment state machine.

    Allowed transitions: ``confirmed → shipped → delivered``.
    Requires ADMIN, MANAGER, or SALES role.

    Args:
        order_id:     UUID of the order to update.
        payload:      Request body containing the target ``status`` string.
        db:           Injected async database session.
        current_user: Authenticated user with a permitted role.

    Returns:
        The updated SalesOrder.
    """
    return await sales_order_service.update_order_status(
        db, order_id, payload.status, user_id=current_user.id
    )


# ── Single order ──────────────────────────────────────────────────────────────

@router.get(
    "/{order_id}",
    response_model=SalesOrderResponse,
    summary="Get a single sales order",
)
async def get_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> SalesOrderResponse:
    """Fetch a SalesOrder by UUID with all line items.

    Args:
        order_id: UUID path parameter identifying the order.
        db:       Injected async database session.

    Returns:
        The requested SalesOrder.

    Raises:
        HTTPException: 404 if not found.
    """
    return await sales_order_service.get_order(db, order_id)
