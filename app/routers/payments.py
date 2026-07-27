"""Payment gateway endpoints — Stripe and PayPal."""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.payment import (
    PaymentStatusResponse,
    PayPalCaptureRequest,
    PayPalOrderResponse,
    StripeSessionResponse,
)
from app.services import payment_service

router = APIRouter()

_finance_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.FINANCE)


# ── Public config (no auth — safe to expose publishable keys) ─────────────────

@router.get("/config", summary="Return publishable gateway keys for the frontend")
async def payment_config():
    return {
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "paypal_client_id": settings.PAYPAL_CLIENT_ID,
        "paypal_mode": settings.PAYPAL_MODE,
    }


# ── Stripe ────────────────────────────────────────────────────────────────────

@router.post(
    "/stripe/create-session",
    response_model=StripeSessionResponse,
    summary="Create a Stripe Checkout session for a sales quotation",
)
async def stripe_create_session(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_finance_roles),
):
    try:
        result = await payment_service.create_stripe_session(db, quotation_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe error: {exc}")
    return result


@router.post(
    "/stripe/webhook",
    summary="Stripe webhook receiver (no auth — verified by signature)",
    include_in_schema=False,
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    payload = await request.body()
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")
    try:
        result = await payment_service.handle_stripe_webhook(db, payload, stripe_signature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


# ── PayPal ────────────────────────────────────────────────────────────────────

@router.post(
    "/paypal/create-order",
    response_model=PayPalOrderResponse,
    summary="Create a PayPal order for a sales quotation",
)
async def paypal_create_order(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_finance_roles),
):
    try:
        result = await payment_service.create_paypal_order(db, quotation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PayPal error: {exc}")
    return result


@router.post(
    "/paypal/capture",
    summary="Capture an approved PayPal order",
)
async def paypal_capture(
    body: PayPalCaptureRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_finance_roles),
):
    try:
        result = await payment_service.capture_paypal_order(db, body.order_id, body.quotation_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PayPal capture error: {exc}")
    return result


# ── Status ────────────────────────────────────────────────────────────────────

@router.get(
    "/{quotation_id}",
    response_model=List[PaymentStatusResponse],
    summary="List all payment attempts for a quotation",
)
async def get_payment_status(
    quotation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await payment_service.get_payments_for_quotation(db, quotation_id)
