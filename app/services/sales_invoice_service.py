# =============================================================================
# app/services/sales_invoice_service.py
# -----------------------------------------------------------------------------
# Business logic for customer (sales) invoices — the in-house replacement for
# the Odoo-backed invoicing. Rules worth knowing:
#
#   * Totals, net prices and the derived "Overdue" status are computed here,
#     never trusted from the client.
#   * The invoice number is either typed by the user (e.g. "2025/1838/5", must
#     be unique) or, if left blank, assigned as INV-YYYY-NNNN when the invoice
#     is posted — under an advisory lock so concurrent posts can't collide or
#     leave gaps. A posted invoice is immutable and can never be deleted (only
#     cancelled), so numbers are never reused.
#   * Payments are recorded manually; the invoice flips to PAID when they
#     cover the total, and back to POSTED if a payment is voided.
#
# Services only flush — the request-scoped session in get_db() commits.
# =============================================================================

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Integer, and_, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import ActivityEntityType, SalesInvoiceStatus
from app.models.sales_invoice import SalesInvoice, SalesInvoiceItem, SalesInvoicePayment
from app.models.sales_order import SalesOrder
from app.config import settings
from app.schemas.sales_invoice import (
    SalesInvoiceCreate,
    SalesInvoiceKPIs,
    SalesInvoiceListResponse,
    SalesInvoicePaymentCreate,
    SalesInvoiceResponse,
    SellerProfile,
    BankAccountInfo,
    SalesInvoiceSummary,
    SalesInvoiceUpdate,
)
from app.services import activity_service
from app.services.sales_invoice_pdf import build_invoice_pdf
from app.utils.email import send_email_with_pdf

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
BASE_CURRENCY = "SAR"
# SAR per 1 unit — USD and AED are pegged, so their rate needn't be typed.
PEGGED_RATES = {"SAR": 1.0, "USD": 3.75, "AED": 1.0211}
DEFAULT_DUE_DAYS = 30
_CENT = 0.005                    # float tolerance when comparing money
_INVOICE_SEQ_LOCK = 7_204_113    # arbitrary constant key for pg_advisory_xact_lock

_LOAD_OPTIONS = (
    selectinload(SalesInvoice.items),
    selectinload(SalesInvoice.payments),
    selectinload(SalesInvoice.created_by),
    selectinload(SalesInvoice.sales_order),
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _r2(n: float) -> float:
    """Round to 2dp, treating ``None`` as 0 — every money value passes through this."""
    return round(float(n or 0), 2)


def _item_amounts(qty: float, unit_price: float, discount: float) -> tuple[float, float]:
    """Return ``(net_price, line_total)`` for one line, rounded to 2dp."""
    disc = min(100.0, max(0.0, float(discount or 0)))
    net = _r2(float(unit_price) * (1 - disc / 100))
    return net, _r2(net * float(qty))


def _terms_days(terms: Optional[str]) -> Optional[int]:
    """Parse a payment-terms label into a due-in-days number, if it has one.

    "Net 30" → 30, "Due on Receipt" → 0; anything else (e.g. "50% Advance,
    50% on Delivery") is not a simple day count → None.
    """
    if not terms:
        return None
    t = terms.strip().lower()
    if "on receipt" in t:
        return 0
    m = re.fullmatch(r"net\s*(\d{1,3})", t)
    return int(m.group(1)) if m else None


def _resolve_exchange_rate(currency: str, given: Optional[float]) -> float:
    """SAR is always 1:1. USD/AED fall back to their peg if not given explicitly;
    any other currency must supply a rate — there's nothing sensible to default to.
    """
    if currency == BASE_CURRENCY:
        return 1.0
    rate = given if given else PEGGED_RATES.get(currency)
    if not rate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Enter the {currency} to SAR exchange rate (needed for the SAR amounts on the invoice)",
        )
    return float(rate)


def _blank(v: Optional[str]) -> Optional[str]:
    """Normalise an optional text field: trims whitespace, empty string -> None."""
    return (v or "").strip() or None


def _apply_fields(inv: SalesInvoice, payload: SalesInvoiceCreate) -> None:
    """Copy header fields from a create/update payload and rebuild the lines."""
    inv.invoice_number = _blank(payload.invoice_number)
    inv.customer_name = payload.customer_name.strip()
    inv.customer_building_no = _blank(payload.customer_building_no)
    inv.customer_street = _blank(payload.customer_street)
    inv.customer_district = _blank(payload.customer_district)
    inv.customer_city = _blank(payload.customer_city)
    inv.customer_country = _blank(payload.customer_country)
    inv.customer_postal_code = _blank(payload.customer_postal_code)
    inv.customer_tax_id = _blank(payload.customer_tax_id)
    inv.customer_cr_no = _blank(payload.customer_cr_no)
    inv.email = _blank(payload.email)
    inv.contact_person = _blank(payload.contact_person)
    inv.delivery_note_no = _blank(payload.delivery_note_no)
    inv.delivery_date = payload.delivery_date
    inv.your_ref = _blank(payload.your_ref)
    inv.vendor_number = _blank(payload.vendor_number)
    inv.internal_reference = _blank(payload.internal_reference)
    inv.gr_ses = _blank(payload.gr_ses)
    inv.currency = payload.currency.upper()
    inv.exchange_rate = _resolve_exchange_rate(inv.currency, payload.exchange_rate)
    inv.invoice_date = payload.invoice_date
    inv.due_date = payload.due_date
    inv.payment_terms = _blank(payload.payment_terms)
    inv.vat_rate = payload.vat_rate
    inv.remarks = _blank(payload.remarks)
    inv.sales_order_id = payload.sales_order_id

    items: list[SalesInvoiceItem] = []
    gross = discount = vat = 0.0
    for idx, it in enumerate(payload.items, start=1):
        net, line_total = _item_amounts(it.qty, it.unit_price, it.discount)
        line_gross = _r2(float(it.qty) * float(it.unit_price))
        gross += line_gross
        discount += line_gross - line_total
        vat += _r2(line_total * float(payload.vat_rate) / 100)   # per-line, as printed
        items.append(SalesInvoiceItem(
            line_no=idx,
            catalog_no=_blank(it.catalog_no),
            item_name=it.item_name.strip(),
            description=_blank(it.description),
            qty=it.qty,
            unit=(it.unit or "Units").strip() or "Units",
            unit_price=it.unit_price,
            discount=it.discount,
            net_price=net,
            total=line_total,
        ))
    inv.items = items          # delete-orphan cascade drops the old lines on flush

    inv.subtotal = _r2(gross)
    inv.discount = _r2(discount)
    inv.vat = _r2(vat)
    inv.total = _r2(inv.subtotal - inv.discount + inv.vat)

    # A due date the user didn't pick can still be derived from "Net N" terms.
    if inv.due_date is None and inv.invoice_date is not None:
        days = _terms_days(inv.payment_terms)
        if days is not None:
            inv.due_date = inv.invoice_date + timedelta(days=days)


async def _check_number_free(
    db: AsyncSession, number: Optional[str], own_id: Optional[uuid.UUID] = None
) -> None:
    """A hand-typed invoice number must not collide with any other invoice."""
    if not number:
        return
    q = select(SalesInvoice.id).where(SalesInvoice.invoice_number == number)
    if own_id is not None:
        q = q.where(SalesInvoice.id != own_id)
    if (await db.execute(q)).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invoice number {number} is already used by another invoice",
        )


async def _check_sales_order(db: AsyncSession, order_id: Optional[uuid.UUID]) -> None:
    """404 if a sales_order_id was given but doesn't exist. A no-op when None."""
    if order_id is None:
        return
    exists = (await db.execute(select(SalesOrder.id).where(SalesOrder.id == order_id))).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales order not found")


async def _load(db: AsyncSession, invoice_id: uuid.UUID) -> SalesInvoice:
    """Fetch one invoice with its items/payments/relations eagerly loaded, or 404.

    Uses ``populate_existing`` because a re-load after our own writes must
    refresh the already-identity-mapped instance (items, payments, derived
    fields) rather than silently return SQLAlchemy's cached version.
    """
    result = await db.execute(
        select(SalesInvoice).where(SalesInvoice.id == invoice_id)
        .options(*_LOAD_OPTIONS).execution_options(populate_existing=True)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return inv


async def _reload_response(db: AsyncSession, invoice_id: uuid.UUID) -> SalesInvoiceResponse:
    """Re-read the invoice fresh so relationships/derived fields are current."""
    return SalesInvoiceResponse.model_validate(await _load(db, invoice_id))


async def _next_invoice_number(db: AsyncSession, on_date: date) -> str:
    """Next ``INV-YYYY-NNNN``; serialised so concurrent posts can't collide."""
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _INVOICE_SEQ_LOCK})
    prefix = f"INV-{on_date.year}-"
    max_n = (await db.execute(
        select(func.max(cast(func.substr(SalesInvoice.invoice_number, len(prefix) + 1), Integer)))
        .where(SalesInvoice.invoice_number.like(f"{prefix}%"))
    )).scalar_one_or_none() or 0
    return f"{prefix}{max_n + 1:04d}"


def _require_status(inv: SalesInvoice, *allowed: SalesInvoiceStatus, action: str) -> None:
    """409 unless the invoice is in one of the allowed statuses for ``action``."""
    if inv.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot {action} a {inv.status.value} invoice",
        )


# ── Public API ────────────────────────────────────────────────────────────────

_DISPLAY_FILTERS = ("Draft", "Open", "Overdue", "Paid", "Cancelled")


def _display_status_condition(name: str):
    """SQL filter for one status-tab name (Draft/Open/Overdue/Paid/Cancelled).

    "Open" and "Overdue" are both derived from a POSTED row plus its due date —
    there's no separate stored status for them.
    """
    today = date.today()
    S = SalesInvoiceStatus
    if name == "Draft":
        return SalesInvoice.status == S.DRAFT
    if name == "Paid":
        return SalesInvoice.status == S.PAID
    if name == "Cancelled":
        return SalesInvoice.status == S.CANCELLED
    if name == "Overdue":
        return and_(SalesInvoice.status == S.POSTED,
                    SalesInvoice.due_date.isnot(None), SalesInvoice.due_date < today)
    if name == "Open":
        return and_(SalesInvoice.status == S.POSTED,
                    or_(SalesInvoice.due_date.is_(None), SalesInvoice.due_date >= today))
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown status filter '{name}'. Use one of: {', '.join(_DISPLAY_FILTERS)}",
    )


async def list_invoices(
    db: AsyncSession,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> SalesInvoiceListResponse:
    """List invoices (optionally filtered by status tab and/or a text search),
    plus the per-tab counts shown on the status sidebar.

    Args:
        db:            Active async database session.
        status_filter: One of Draft/Open/Overdue/Paid/Cancelled, or None for all.
        search:        Case-insensitive match against customer name or invoice number.
        skip, limit:   Pagination.

    Returns:
        A page of invoice summaries, the total matching count, and the counts
        for every status tab (independent of the current filter/search).
    """
    q = select(SalesInvoice).options(selectinload(SalesInvoice.sales_order))
    if status_filter:
        q = q.where(_display_status_condition(status_filter))
    if search:
        pattern = f"%{search.strip()}%"
        q = q.where(or_(SalesInvoice.customer_name.ilike(pattern),
                        SalesInvoice.invoice_number.ilike(pattern)))

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(
        q.order_by(SalesInvoice.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()

    counts_row = (await db.execute(select(*[
        func.count().filter(_display_status_condition(n)) for n in _DISPLAY_FILTERS
    ]))).one()
    counts = dict(zip(_DISPLAY_FILTERS, (int(c) for c in counts_row)))

    return SalesInvoiceListResponse(
        items=[SalesInvoiceSummary.model_validate(r) for r in rows],
        total=total,
        counts=counts,
    )


async def get_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> SalesInvoiceResponse:
    """Fetch the full invoice, including line items and payments, or 404."""
    return SalesInvoiceResponse.model_validate(await _load(db, invoice_id))


async def create_invoice(
    db: AsyncSession, payload: SalesInvoiceCreate, user_id: Optional[uuid.UUID]
) -> SalesInvoiceResponse:
    """Create a new draft invoice.

    Args:
        db:      Active async database session.
        payload: Invoice header, buyer details and line items.
        user_id: UUID of the creating user, stored as ``created_by_id``.

    Returns:
        The newly created draft, with totals already computed.

    Raises:
        HTTPException: 404 if ``sales_order_id`` doesn't exist.
        HTTPException: 409 if a hand-typed ``invoice_number`` is already in use.
    """
    await _check_sales_order(db, payload.sales_order_id)
    await _check_number_free(db, _blank(payload.invoice_number))
    inv = SalesInvoice(status=SalesInvoiceStatus.DRAFT, created_by_id=user_id)
    _apply_fields(inv, payload)
    if inv.invoice_date is None:
        inv.invoice_date = date.today()
        if inv.due_date is None and (days := _terms_days(inv.payment_terms)) is not None:
            inv.due_date = inv.invoice_date + timedelta(days=days)
    db.add(inv)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.SALES_INVOICE, inv.id, "created",
        f"Draft invoice created for {inv.customer_name}", user_id,
    )
    await db.flush()
    return await _reload_response(db, inv.id)


async def update_invoice(
    db: AsyncSession, invoice_id: uuid.UUID, payload: SalesInvoiceUpdate, user_id: Optional[uuid.UUID]
) -> SalesInvoiceResponse:
    """Replace a draft invoice's fields and line items wholesale.

    Args:
        db:         Active async database session.
        invoice_id: UUID of the draft to edit.
        payload:    Full replacement invoice data (same shape as create).
        user_id:    UUID of the acting user, for the activity log.

    Returns:
        The updated draft, with totals recomputed.

    Raises:
        HTTPException: 404 if the invoice or its ``sales_order_id`` doesn't exist.
        HTTPException: 409 if the invoice isn't a draft, or the invoice number
            collides with a different invoice.
    """
    inv = await _load(db, invoice_id)
    _require_status(inv, SalesInvoiceStatus.DRAFT, action="edit")
    await _check_sales_order(db, payload.sales_order_id)
    await _check_number_free(db, _blank(payload.invoice_number), own_id=inv.id)
    _apply_fields(inv, payload)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.SALES_INVOICE, inv.id, "updated", "Draft invoice edited", user_id,
    )
    await db.flush()
    return await _reload_response(db, inv.id)


async def delete_draft(db: AsyncSession, invoice_id: uuid.UUID) -> None:
    """Permanently delete a draft invoice.

    Raises:
        HTTPException: 404 if not found; 409 if it isn't a draft (posted
            invoices are cancelled, never deleted — see ``cancel_invoice``).
    """
    inv = await _load(db, invoice_id)
    _require_status(inv, SalesInvoiceStatus.DRAFT, action="delete")
    await db.delete(inv)
    await db.flush()


async def post_invoice(
    db: AsyncSession, invoice_id: uuid.UUID, user_id: Optional[uuid.UUID]
) -> SalesInvoiceResponse:
    """Confirm a draft: assign the sequential number and lock it against edits."""
    inv = await _load(db, invoice_id)
    _require_status(inv, SalesInvoiceStatus.DRAFT, action="post")
    if not inv.items or float(inv.total) <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An invoice needs at least one line and a total above zero before it can be posted",
        )

    if inv.invoice_date is None:
        inv.invoice_date = date.today()
    if inv.due_date is None:
        days = _terms_days(inv.payment_terms)
        inv.due_date = inv.invoice_date + timedelta(days=DEFAULT_DUE_DAYS if days is None else days)

    if not inv.invoice_number:
        inv.invoice_number = await _next_invoice_number(db, inv.invoice_date)
    inv.status = SalesInvoiceStatus.POSTED
    inv.posted_at = datetime.now(timezone.utc)
    inv.posted_by_id = user_id
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.SALES_INVOICE, inv.id, "posted",
        f"Invoice {inv.invoice_number} confirmed", user_id,
    )
    await db.flush()
    return await _reload_response(db, inv.id)


async def cancel_invoice(
    db: AsyncSession, invoice_id: uuid.UUID, user_id: Optional[uuid.UUID]
) -> SalesInvoiceResponse:
    """Cancel a posted invoice that has no payments; the number is kept, never reused."""
    inv = await _load(db, invoice_id)
    _require_status(inv, SalesInvoiceStatus.POSTED, action="cancel")
    if inv.payments:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invoice has recorded payments — remove them before cancelling",
        )
    inv.status = SalesInvoiceStatus.CANCELLED
    inv.cancelled_at = datetime.now(timezone.utc)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.SALES_INVOICE, inv.id, "cancelled",
        f"Invoice {inv.invoice_number} cancelled", user_id,
    )
    await db.flush()
    return await _reload_response(db, inv.id)


def _sync_payment_state(inv: SalesInvoice) -> None:
    """Recompute amount_paid and flip POSTED <-> PAID from the payment rows."""
    inv.amount_paid = _r2(sum(float(p.amount) for p in inv.payments))
    if inv.balance <= _CENT:
        if inv.status != SalesInvoiceStatus.PAID:
            inv.status = SalesInvoiceStatus.PAID
            inv.paid_at = datetime.now(timezone.utc)
    else:
        inv.status = SalesInvoiceStatus.POSTED
        inv.paid_at = None


async def record_payment(
    db: AsyncSession, invoice_id: uuid.UUID, payload: SalesInvoicePaymentCreate, user_id: Optional[uuid.UUID]
) -> SalesInvoiceResponse:
    """Record a payment against a posted invoice; flips it to PAID once fully covered.

    Raises:
        HTTPException: 409 if the invoice isn't posted.
        HTTPException: 400 if the payment would exceed the outstanding balance.
    """
    inv = await _load(db, invoice_id)
    _require_status(inv, SalesInvoiceStatus.POSTED, action="record a payment on")
    amount = _r2(payload.amount)
    if amount > inv.balance + _CENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment of {amount:,.2f} exceeds the outstanding balance of {inv.balance:,.2f}",
        )
    inv.payments.append(SalesInvoicePayment(
        amount=amount,
        payment_date=payload.payment_date or date.today(),
        method=payload.method,
        reference=(payload.reference or "").strip() or None,
        notes=(payload.notes or "").strip() or None,
        recorded_by_id=user_id,
    ))
    _sync_payment_state(inv)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.SALES_INVOICE, inv.id, "payment_recorded",
        f"Payment of {amount:,.2f} {inv.currency} recorded ({payload.method.replace('_', ' ')})", user_id,
    )
    await db.flush()
    return await _reload_response(db, inv.id)


async def delete_payment(
    db: AsyncSession, invoice_id: uuid.UUID, payment_id: uuid.UUID, user_id: Optional[uuid.UUID]
) -> SalesInvoiceResponse:
    """Void a mistakenly recorded payment; reopens the invoice if it was PAID."""
    inv = await _load(db, invoice_id)
    _require_status(inv, SalesInvoiceStatus.POSTED, SalesInvoiceStatus.PAID, action="remove a payment from")
    payment = next((p for p in inv.payments if p.id == payment_id), None)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    amount = _r2(payment.amount)
    inv.payments.remove(payment)
    _sync_payment_state(inv)
    await db.flush()
    activity_service.log_activity(
        db, ActivityEntityType.SALES_INVOICE, inv.id, "payment_removed",
        f"Payment of {amount:,.2f} {inv.currency} removed", user_id,
    )
    await db.flush()
    return await _reload_response(db, inv.id)


async def get_kpis(db: AsyncSession) -> SalesInvoiceKPIs:
    """Headline numbers for the base currency (SAR); other currencies are only counted."""
    S = SalesInvoiceStatus
    today = date.today()
    live = SalesInvoice.status.in_([S.POSTED, S.PAID])
    overdue = and_(SalesInvoice.status == S.POSTED,
                   SalesInvoice.due_date.isnot(None), SalesInvoice.due_date < today)
    in_base = SalesInvoice.currency == BASE_CURRENCY
    balance = SalesInvoice.total - SalesInvoice.amount_paid

    row = (await db.execute(select(
        func.coalesce(func.sum(SalesInvoice.total).filter(live, in_base), 0),
        func.coalesce(func.sum(SalesInvoice.amount_paid).filter(live, in_base), 0),
        func.coalesce(func.sum(balance).filter(SalesInvoice.status == S.POSTED, in_base), 0),
        func.count().filter(overdue, in_base),
        func.coalesce(func.sum(balance).filter(overdue, in_base), 0),
        func.count().filter(live, in_base),
        func.count().filter(live, SalesInvoice.currency != BASE_CURRENCY),
    ))).one()

    return SalesInvoiceKPIs(
        currency=BASE_CURRENCY,
        total_invoiced=_r2(row[0]),
        total_received=_r2(row[1]),
        total_outstanding=_r2(row[2]),
        overdue_count=int(row[3]),
        overdue_amount=_r2(row[4]),
        invoice_count=int(row[5]),
        other_currency_invoices=int(row[6]),
    )


async def email_invoice(db: AsyncSession, invoice_id: uuid.UUID, user_id: Optional[uuid.UUID]) -> SalesInvoiceResponse:
    """Email the invoice PDF to the customer's address.

    Only posted/paid invoices qualify — a draft isn't a real tax invoice yet,
    so it must be confirmed first. Unlike a status transition (e.g. sending a
    quotation), delivery failure here is surfaced as an error rather than
    silently marked as sent, since there's no "sent" state to fall back on.

    Raises:
        HTTPException: 409 if the invoice is still a draft.
        HTTPException: 400 if there's no (valid) customer email address.
        HTTPException: 502 if the email provider rejects or fails to send it.
    """
    inv = await _load(db, invoice_id)
    _require_status(inv, SalesInvoiceStatus.POSTED, SalesInvoiceStatus.PAID, action="email")
    if not inv.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invoice has no customer email address — edit the draft to add one before confirming, or add it now.",
        )
    if not _EMAIL_RE.match(inv.email.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{inv.email}' is not a valid email address")

    pdf_buf = build_invoice_pdf(inv)
    try:
        await send_email_with_pdf(
            to_addr=inv.email,
            subject=f"Invoice {inv.invoice_number} — {settings.SELLER_NAME.split(' ')[0]}",
            body=(
                f"Dear {inv.contact_person or inv.customer_name},\n\n"
                f"Please find attached invoice {inv.invoice_number} for "
                f"{inv.total:,.2f} {inv.currency}, due {inv.due_date or 'on receipt'}.\n\n"
                f"Best regards,\n{settings.SELLER_NAME}"
            ),
            pdf_bytes=pdf_buf.getvalue(),
            pdf_filename=f"{inv.invoice_number.replace('/', '-')}.pdf",
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Email delivery failed: {exc}")

    activity_service.log_activity(
        db, ActivityEntityType.SALES_INVOICE, inv.id, "emailed",
        f"Invoice emailed to {inv.email}", user_id,
    )
    await db.flush()
    return await _reload_response(db, inv.id)


async def generate_pdf(db: AsyncSession, invoice_id: uuid.UUID) -> StreamingResponse:
    """Stream the invoice as a downloadable PDF (see sales_invoice_pdf.build_invoice_pdf)."""
    inv = await _load(db, invoice_id)
    buf = build_invoice_pdf(inv)
    name = (inv.invoice_number or f"DRAFT-{str(inv.id)[:8]}").replace("/", "-")
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'},
    )


def get_seller_profile() -> SellerProfile:
    """Seller block + bank accounts from settings, for the read-only part of the form."""
    st = settings
    return SellerProfile(
        name=st.SELLER_NAME, building=st.SELLER_BUILDING, street=st.SELLER_STREET,
        district=st.SELLER_DISTRICT, city=st.SELLER_CITY, country=st.SELLER_COUNTRY,
        postal_code=st.SELLER_POSTAL_CODE, vat_number=st.SELLER_VAT_NUMBER, cr_no=st.SELLER_CR_NO,
        bank_accounts=[BankAccountInfo(**a) for a in st.COMPANY_BANK_ACCOUNTS],
    )
