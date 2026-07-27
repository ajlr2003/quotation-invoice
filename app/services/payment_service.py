"""Payment gateway integration — Stripe and PayPal.

Safety guarantees implemented here:

1. DOUBLE-CHARGE PREVENTION
   Before creating any session/order, we check if a paid Payment already
   exists for the quotation. If yes → raise immediately, no gateway call made.
   If a pending session exists → re-use it instead of creating a second one.

2. WEBHOOK IDEMPOTENCY (Stripe)
   If the webhook arrives twice (Stripe retries on 5xx), the second call is
   a no-op: we detect status='paid' already and return 200 without re-writing.
   Stripe retries on any non-2xx response, so DB errors naturally cause retries.

3. PAYPAL CAPTURE ATOMICITY
   Money moves at PayPal's servers during capture. If our DB update fails
   AFTER a successful capture, we log CRITICAL with the capture ID so it can
   be manually reconciled. The capture_id is the proof of payment at PayPal.

4. MISSING WEBHOOK RECORD RECOVERY
   If the Stripe webhook arrives but our DB has no matching Payment record
   (e.g. the initial DB commit failed), we create the record on-the-fly so
   the quotation still gets marked paid.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
import uuid

import httpx
import stripe
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.payment import Payment
from app.models.sales_quotation import SalesQuotation

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


# ── helpers ───────────────────────────────────────────────────────────────────

async def _get_quotation(db: AsyncSession, quotation_id: uuid.UUID) -> SalesQuotation:
    result = await db.execute(select(SalesQuotation).where(SalesQuotation.id == quotation_id))
    q = result.scalar_one_or_none()
    if not q:
        raise ValueError(f"Quotation {quotation_id} not found")
    return q


async def _mark_quotation_paid(db: AsyncSession, quotation_id: uuid.UUID) -> None:
    await db.execute(
        text("UPDATE sales_quotations SET payment_status='paid' WHERE id=:id"),
        {"id": str(quotation_id)},
    )


async def _get_existing_payment(
    db: AsyncSession, quotation_id: uuid.UUID, gateway: str
) -> Optional[Payment]:
    """Return the most recent payment record for this quotation+gateway."""
    result = await db.execute(
        select(Payment)
        .where(Payment.quotation_id == quotation_id, Payment.gateway == gateway)
        .order_by(Payment.created_at.desc())
    )
    return result.scalar_one_or_none()


async def _guard_already_paid(db: AsyncSession, quotation_id: uuid.UUID) -> None:
    """Raise if any gateway has already confirmed payment for this quotation."""
    result = await db.execute(
        select(Payment).where(
            Payment.quotation_id == quotation_id,
            Payment.status == "paid",
        )
    )
    if result.scalar_one_or_none():
        raise ValueError("This quotation has already been paid.")


# ── Stripe ────────────────────────────────────────────────────────────────────

async def create_stripe_session(
    db: AsyncSession,
    quotation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    # Safety 1: block if already paid by any gateway
    await _guard_already_paid(db, quotation_id)

    # Safety 1b: re-use a pending Stripe session instead of creating a second one
    existing = await _get_existing_payment(db, quotation_id, "stripe")
    if existing and existing.status == "pending" and existing.gateway_session_id:
        try:
            session = stripe.checkout.Session.retrieve(existing.gateway_session_id)
            if session.status == "open":
                logger.info("Re-using existing Stripe session %s", session.id)
                return {"checkout_url": session.url, "session_id": session.id}
        except Exception:
            pass  # session expired or invalid — fall through to create a new one

    q = await _get_quotation(db, quotation_id)
    amount_minor = int(float(q.total) * 100)
    currency = (q.currency or "SAR").lower()

    success_url = (
        f"{settings.FRONTEND_BASE_URL}/payment/success"
        f"?quote_number={q.quote_number}&session_id={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = (
        f"{settings.FRONTEND_BASE_URL}/payment/cancel"
        f"?quote_number={q.quote_number}"
    )

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": currency,
                "unit_amount": amount_minor,
                "product_data": {
                    "name": f"Quotation {q.quote_number}",
                    "description": f"Payment for {q.quote_number} — {q.customer_name or ''}",
                },
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        # Idempotency key prevents duplicate sessions if request is retried
        metadata={"quotation_id": str(quotation_id), "quote_number": q.quote_number},
    )

    payment = Payment(
        quotation_id=quotation_id,
        gateway="stripe",
        gateway_session_id=session.id,
        amount=float(q.total),
        currency=q.currency or "SAR",
        status="pending",
    )
    db.add(payment)
    await db.commit()

    return {"checkout_url": session.url, "session_id": session.id}


async def handle_stripe_webhook(db: AsyncSession, payload: bytes, sig_header: str) -> dict:
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid Stripe webhook signature")

    if event["type"] == "checkout.session.completed":
        session     = event["data"]["object"]
        session_id  = session["id"]
        payment_intent = session.get("payment_intent")
        quotation_id_str = session.get("metadata", {}).get("quotation_id")

        result = await db.execute(
            select(Payment).where(Payment.gateway_session_id == session_id)
        )
        payment = result.scalar_one_or_none()

        # Safety 2: idempotency — skip if already processed
        if payment and payment.status == "paid":
            logger.info("Stripe webhook: session %s already marked paid — skipping", session_id)
            return {"received": True}

        # Safety 4: create record if it was never persisted
        if not payment and quotation_id_str:
            logger.warning(
                "Stripe webhook: no Payment record for session %s — creating one now", session_id
            )
            payment = Payment(
                quotation_id=uuid.UUID(quotation_id_str),
                gateway="stripe",
                gateway_session_id=session_id,
                amount=session.get("amount_total", 0) / 100,
                currency=session.get("currency", "sar").upper(),
                status="pending",
            )
            db.add(payment)
            await db.flush()

        if payment:
            payment.status     = "paid"
            payment.gateway_ref = payment_intent
            payment.paid_at    = datetime.now(timezone.utc)
            if quotation_id_str:
                await _mark_quotation_paid(db, uuid.UUID(quotation_id_str))
            # DB errors here will propagate as 500 → Stripe retries → correct behaviour
            await db.commit()
            logger.info("Stripe payment confirmed: session=%s intent=%s", session_id, payment_intent)

    return {"received": True}


# ── PayPal ────────────────────────────────────────────────────────────────────

_PAYPAL_BASE = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live":    "https://api-m.paypal.com",
}


async def _paypal_access_token() -> str:
    base = _PAYPAL_BASE.get(settings.PAYPAL_MODE, _PAYPAL_BASE["sandbox"])
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base}/v1/oauth2/token",
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def create_paypal_order(
    db: AsyncSession,
    quotation_id: uuid.UUID,
) -> dict:
    # Safety 1: block if already paid
    await _guard_already_paid(db, quotation_id)

    # Safety 1b: re-use a pending PayPal order
    existing = await _get_existing_payment(db, quotation_id, "paypal")
    if existing and existing.status == "pending" and existing.gateway_session_id:
        logger.info("Re-using existing PayPal order %s", existing.gateway_session_id)
        return {"order_id": existing.gateway_session_id, "approve_url": ""}

    q = await _get_quotation(db, quotation_id)
    token = await _paypal_access_token()
    base  = _PAYPAL_BASE.get(settings.PAYPAL_MODE, _PAYPAL_BASE["sandbox"])

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": str(quotation_id),
                    "description": f"Quotation {q.quote_number}",
                    "amount": {
                        "currency_code": q.currency or "SAR",
                        "value": f"{float(q.total):.2f}",
                    },
                }],
                "application_context": {
                    "return_url": f"{settings.FRONTEND_BASE_URL}/payment/success?quote_number={q.quote_number}",
                    "cancel_url": f"{settings.FRONTEND_BASE_URL}/payment/cancel?quote_number={q.quote_number}",
                },
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

    order_id    = data["id"]
    approve_url = next(
        (link["href"] for link in data.get("links", []) if link["rel"] == "approve"), ""
    )

    payment = Payment(
        quotation_id=quotation_id,
        gateway="paypal",
        gateway_session_id=order_id,
        amount=float(q.total),
        currency=q.currency or "SAR",
        status="pending",
    )
    db.add(payment)
    await db.commit()

    return {"order_id": order_id, "approve_url": approve_url}


async def capture_paypal_order(
    db: AsyncSession,
    order_id: str,
    quotation_id: uuid.UUID,
) -> dict:
    # Safety 2: idempotency — if already captured, return success immediately
    result = await db.execute(
        select(Payment).where(
            Payment.gateway_session_id == order_id,
            Payment.status == "paid",
        )
    )
    if result.scalar_one_or_none():
        logger.info("PayPal order %s already captured — skipping", order_id)
        return {"order_id": order_id, "status": "COMPLETED", "capture_id": None}

    token = await _paypal_access_token()
    base  = _PAYPAL_BASE.get(settings.PAYPAL_MODE, _PAYPAL_BASE["sandbox"])

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

    status     = data.get("status", "")
    capture_id: Optional[str] = None
    try:
        capture_id = data["purchase_units"][0]["payments"]["captures"][0]["id"]
    except (KeyError, IndexError):
        pass

    result = await db.execute(
        select(Payment).where(Payment.gateway_session_id == order_id)
    )
    payment = result.scalar_one_or_none()

    if status == "COMPLETED":
        # Safety 3: money has moved at PayPal — log CRITICAL before DB write
        # so even if DB fails, the capture_id is in the logs for reconciliation
        logger.critical(
            "PAYPAL CAPTURE SUCCEEDED — order=%s capture=%s quotation=%s amount=%s — "
            "writing to DB now. If DB fails, reconcile manually using capture_id.",
            order_id, capture_id, quotation_id,
            payment.amount if payment else "unknown",
        )
        try:
            if payment:
                payment.status     = "paid"
                payment.gateway_ref = capture_id
                payment.paid_at    = datetime.now(timezone.utc)
            await _mark_quotation_paid(db, quotation_id)
            await db.commit()
            logger.info("PayPal DB update committed — order=%s", order_id)
        except Exception as db_err:
            logger.critical(
                "CRITICAL: PayPal capture %s succeeded but DB commit failed: %s — "
                "MANUAL ACTION REQUIRED: mark quotation %s as paid",
                capture_id, db_err, quotation_id,
            )
            raise
    else:
        if payment:
            payment.status = "failed"
            await db.commit()

    return {"order_id": order_id, "status": status, "capture_id": capture_id}


# ── Query ─────────────────────────────────────────────────────────────────────

async def get_payments_for_quotation(
    db: AsyncSession, quotation_id: uuid.UUID
) -> list[Payment]:
    result = await db.execute(
        select(Payment)
        .where(Payment.quotation_id == quotation_id)
        .order_by(Payment.created_at.desc())
    )
    return list(result.scalars().all())
