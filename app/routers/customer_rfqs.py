# =============================================================================
# app/routers/customer_rfqs.py
# -----------------------------------------------------------------------------
# FastAPI route handlers for the Customer RFQ module — requests for pricing
# received FROM a customer, manually logged. Mounted under
# /api/v1/customer-rfqs by app/main.py.
#
# Endpoint summary:
#   GET   /                — list customer RFQs (optional ?status=)
#   POST  /                — log a new customer RFQ
#   GET   /{id}            — get a single customer RFQ
#   PATCH /{id}/status     — transition status (open/quoted/closed)
#
# All routes require a valid Bearer JWT (get_current_user dependency).
# Write operations require ADMIN, MANAGER, or SALES roles.
# =============================================================================

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import CustomerRFQStatus, UserRole
from app.schemas.customer_rfq import (
    CustomerRFQCreate,
    CustomerRFQListResponse,
    CustomerRFQResponse,
    CustomerRFQStatusUpdate,
)
from app.services import customer_rfq_service

router = APIRouter()

_sales_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES)


@router.get("", response_model=CustomerRFQListResponse, summary="List customer RFQs")
async def list_customer_rfqs(
    status_filter: Optional[CustomerRFQStatus] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await customer_rfq_service.list_customer_rfqs(db, status_filter=status_filter)


@router.post(
    "", response_model=CustomerRFQResponse, status_code=status.HTTP_201_CREATED,
    summary="Log a new customer RFQ",
)
async def create_customer_rfq(
    payload: CustomerRFQCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_sales_roles),
):
    return await customer_rfq_service.create_customer_rfq(db, payload, user_id=current_user.id)


@router.get("/{rfq_id}", response_model=CustomerRFQResponse, summary="Get a customer RFQ")
async def get_customer_rfq(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    rfq = await customer_rfq_service.get_customer_rfq(db, rfq_id)
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer RFQ not found")
    return CustomerRFQResponse.model_validate(rfq)


@router.patch(
    "/{rfq_id}/status", response_model=CustomerRFQResponse,
    summary="Transition a customer RFQ's status",
)
async def update_customer_rfq_status(
    rfq_id: uuid.UUID,
    payload: CustomerRFQStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_sales_roles),
):
    return await customer_rfq_service.update_status(db, rfq_id, payload, user_id=current_user.id)
