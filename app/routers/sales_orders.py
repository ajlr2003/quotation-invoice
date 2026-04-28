"""
app/routers/sales_orders.py

  POST /api/v1/sales/orders        — create order from quotation
  GET  /api/v1/sales/orders        — list all sales orders
  GET  /api/v1/sales/orders/<id>   — get single order
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.sales_order import SalesOrderCreate, SalesOrderListResponse, SalesOrderResponse
from app.services import sales_order_service
from pydantic import BaseModel


class RevenueResponse(BaseModel):
    total_revenue: float


class TopProductEntry(BaseModel):
    name: str
    revenue: float


class TopProductsResponse(BaseModel):
    top_products: list[TopProductEntry]

router = APIRouter()


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
):
    return await sales_order_service.create_from_quotation(db, payload)


@router.get(
    "",
    response_model=SalesOrderListResponse,
    summary="List all sales orders",
)
async def list_orders(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_order_service.list_orders(db)


@router.get(
    "/revenue",
    response_model=RevenueResponse,
    summary="Total revenue from delivered sales orders",
)
async def get_revenue(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
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
):
    products = await sales_order_service.get_top_products(db)
    return TopProductsResponse(top_products=products)


@router.get(
    "/{order_id}",
    response_model=SalesOrderResponse,
    summary="Get a single sales order",
)
async def get_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_order_service.get_order(db, order_id)
