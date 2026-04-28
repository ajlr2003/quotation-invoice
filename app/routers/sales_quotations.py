"""
app/routers/sales_quotations.py

Sales quotation endpoints (builder flow — outbound to customers):
  POST   /api/v1/sales/quotations            — create quotation
  GET    /api/v1/sales/quotations            — list quotations (optional ?status=)
  GET    /api/v1/sales/quotations/<id>       — get single
  PUT    /api/v1/sales/quotations/<id>       — update (draft only)
  PATCH  /api/v1/sales/quotations/<id>/status — transition status
  GET    /api/v1/sales/quotations/<id>/pdf   — download PDF
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.sales_order import SalesOrderResponse
from app.schemas.sales_quotation import (
    SalesQuotationCreate,
    SalesQuotationListResponse,
    SalesQuotationResponse,
    SalesQuotationStatusUpdate,
    SalesQuotationUpdate,
)
from app.services import sales_quotation_service
from pydantic import BaseModel


class ActiveQuotesResponse(BaseModel):
    active_quotes: int


class ConversionRateResponse(BaseModel):
    conversion_rate: float


router = APIRouter()


@router.post(
    "",
    response_model=SalesQuotationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a sales quotation",
)
async def create_quotation(
    payload: SalesQuotationCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.create_quotation(db, payload)


@router.get(
    "",
    response_model=SalesQuotationListResponse,
    summary="List all sales quotations",
)
async def list_quotations(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.list_quotations(db, status_filter)


@router.get(
    "/stats/conversion-rate",
    response_model=ConversionRateResponse,
    summary="Conversion rate: converted quotations / total quotations * 100",
)
async def get_conversion_rate(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    rate = await sales_quotation_service.get_conversion_rate(db)
    return ConversionRateResponse(conversion_rate=rate)


@router.get(
    "/stats/active",
    response_model=ActiveQuotesResponse,
    summary="Count of active (draft + sent) quotations",
)
async def get_active_quotes(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    count = await sales_quotation_service.get_active_quotes_count(db)
    return ActiveQuotesResponse(active_quotes=count)


@router.get(
    "/{quote_id}",
    response_model=SalesQuotationResponse,
    summary="Get a single sales quotation",
)
async def get_quotation(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.get_quotation(db, quote_id)


@router.put(
    "/{quote_id}",
    response_model=SalesQuotationResponse,
    summary="Update a sales quotation (draft only)",
)
async def update_quotation(
    quote_id: uuid.UUID,
    payload: SalesQuotationUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.update_quotation(db, quote_id, payload)


@router.patch(
    "/{quote_id}/status",
    response_model=SalesQuotationResponse,
    summary="Transition quotation status (sent → accepted / rejected, etc.)",
)
async def update_status(
    quote_id: uuid.UUID,
    payload: SalesQuotationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.update_status(db, quote_id, payload.status)


@router.put(
    "/{quote_id}/send",
    response_model=SalesQuotationResponse,
    summary="Mark quotation as sent to client",
)
async def send_quotation(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.update_status(db, quote_id, "sent")


@router.put(
    "/{quote_id}/accept",
    response_model=SalesQuotationResponse,
    summary="Mark quotation as accepted by client",
)
async def accept_quotation(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.update_status(db, quote_id, "accepted")


@router.put(
    "/{quote_id}/reject",
    response_model=SalesQuotationResponse,
    summary="Mark quotation as rejected by client",
)
async def reject_quotation(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.update_status(db, quote_id, "rejected")


@router.post(
    "/{quote_id}/convert",
    response_model=SalesOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Convert an accepted quotation into a sales order",
)
async def convert_to_order(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.convert_to_order(db, quote_id)


@router.get(
    "/{quote_id}/pdf",
    summary="Download quotation as PDF",
)
async def download_pdf(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await sales_quotation_service.generate_pdf(db, quote_id)
