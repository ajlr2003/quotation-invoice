# =============================================================================
# app/services/sales_quotation_service.py
# -----------------------------------------------------------------------------
# Business logic for the Sales Quotation lifecycle: create, list, get, update,
# status transitions, email delivery, PDF generation, and conversion to a
# SalesOrder. All database writes use SQLAlchemy async sessions; PDF rendering
# is handled by ReportLab and email delivery is offloaded to a thread executor
# so neither operation blocks the asyncio event loop.
# =============================================================================

from __future__ import annotations

import asyncio
import smtplib
from datetime import date, datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from typing import Optional

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.enums import SalesOrderStatus, SalesQuotationStatus
from app.models.sales_order import SalesOrder
from app.models.sales_order_item import SalesOrderItem
from app.models.sales_quotation import SalesQuotation
from app.models.sales_quotation_item import SalesQuotationItem
from app.schemas.sales_order import SalesOrderResponse
from app.schemas.sales_quotation import (
    SalesQuotationCreate,
    SalesQuotationListResponse,
    SalesQuotationResponse,
    SalesQuotationUpdate,
)

# ── State-machine: allowed transitions between quotation statuses ─────────────
# Sending (DRAFT → SENT) is handled separately by `send_quotation` to ensure
# the email is actually delivered before the status is persisted.
_VALID_TRANSITIONS: dict[SalesQuotationStatus, set[SalesQuotationStatus]] = {
    SalesQuotationStatus.DRAFT:     {SalesQuotationStatus.SENT},
    SalesQuotationStatus.SENT:      {SalesQuotationStatus.ACCEPTED, SalesQuotationStatus.REJECTED},
    SalesQuotationStatus.ACCEPTED:  {SalesQuotationStatus.CONVERTED},
    SalesQuotationStatus.REJECTED:  set(),
    SalesQuotationStatus.CONVERTED: set(),
}


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _next_quote_number(db: AsyncSession) -> str:
    """Generate the next sequential Sales Quotation number for the current year.

    Format: ``SQ-{YYYY}-{NNNN}`` (e.g. ``SQ-2026-0042``).

    Args:
        db: Active async database session.

    Returns:
        A unique quote number string.
    """
    year = datetime.now(timezone.utc).year
    prefix = f"SQ-{year}-"
    count_result = await db.execute(
        select(func.count()).select_from(SalesQuotation).where(
            SalesQuotation.quote_number.like(f"{prefix}%")
        )
    )
    n = (count_result.scalar_one() or 0) + 1
    return f"{prefix}{n:04d}"


def _compute_item(item_data) -> tuple[float, float]:
    """Recompute net_price and total for a single item, ignoring client values.

    Args:
        item_data: A ``SalesQuotationItemCreate`` (or similar) object with
            ``qty``, ``unit_price``, and ``discount`` attributes.

    Returns:
        A ``(net_price, total)`` tuple rounded to 2 decimal places.
    """
    qty = float(item_data.qty)
    up = float(item_data.unit_price)
    disc = min(100.0, max(0.0, float(item_data.discount or 0)))
    net_price = round(up * (1 - disc / 100), 2)
    total = round(qty * net_price, 2)
    return net_price, total


def _valid_items(items_data: list) -> list:
    """Filter out invalid line items before persisting.

    A valid item must have a non-empty name, positive qty, and non-negative
    unit_price.  Invalid items are silently discarded.

    Args:
        items_data: List of ``SalesQuotationItemCreate`` objects.

    Returns:
        A filtered list containing only valid items.
    """
    return [
        i for i in items_data
        if (i.item_name or "").strip()
        and float(i.qty) > 0
        and float(i.unit_price) >= 0
    ]


def _calc_totals(items_data: list) -> tuple[float, float, float]:
    """Calculate subtotal, VAT (15%), and grand total from a list of items.

    Args:
        items_data: List of valid item objects (must pass through
            ``_valid_items`` first).

    Returns:
        A ``(subtotal, vat, total)`` tuple, all rounded to 2 decimal places.
    """
    subtotal = round(sum(_compute_item(i)[1] for i in items_data), 2)
    vat = round(subtotal * 0.15, 2)      # Saudi VAT rate: 15%
    total = round(subtotal + vat, 2)
    return subtotal, vat, total


async def _load(db: AsyncSession, quote_id) -> SalesQuotation:
    """Fetch a SalesQuotation by ID, eagerly loading its items.

    Args:
        db:       Active async database session.
        quote_id: UUID of the quotation to load.

    Returns:
        The ``SalesQuotation`` ORM instance with ``items`` loaded.

    Raises:
        HTTPException: 404 if no quotation with the given ID exists.
    """
    result = await db.execute(
        select(SalesQuotation)
        .where(SalesQuotation.id == quote_id)
        .options(selectinload(SalesQuotation.items))
    )
    q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales quotation not found",
        )
    return q


# ── Public service functions ──────────────────────────────────────────────────

async def create_quotation(
    db: AsyncSession, payload: SalesQuotationCreate
) -> SalesQuotationResponse:
    """Create a new SalesQuotation in DRAFT status.

    Validates and filters items, computes server-side totals, generates a
    sequential quote number, and persists the quotation + items.

    Args:
        db:      Active async database session.
        payload: Validated create request from the router.

    Returns:
        The newly created quotation as a ``SalesQuotationResponse``.

    Raises:
        HTTPException: 400 if no valid line items remain after filtering.
    """
    valid = _valid_items(payload.items)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Quotation must have at least one valid item "
                "(non-empty name, qty > 0, unit_price ≥ 0)"
            ),
        )

    quote_number = await _next_quote_number(db)
    subtotal, vat, total = _calc_totals(valid)

    q = SalesQuotation(
        quote_number=quote_number,
        date=payload.date or date.today(),
        currency=payload.currency,
        validity=payload.validity,
        delivery_time=(payload.delivery_time or "").strip() or None,
        delivery_location=(payload.delivery_location or "").strip() or None,
        payment_terms=(payload.payment_terms or "").strip() or None,
        customer_name=payload.customer_name.strip(),
        department=(payload.department or "").strip() or None,
        contact_person=(payload.contact_person or "").strip() or None,
        phone=(payload.phone or "").strip() or None,
        email=(payload.email or "").strip() or None,
        subject=(payload.subject or "").strip() or "Sales Quotation",
        subtotal=subtotal,
        vat=vat,
        total=total,
        remarks=(payload.remarks or "").strip() or None,
        terms=(payload.terms or "").strip() or None,
        status=SalesQuotationStatus.DRAFT,
    )
    db.add(q)
    await db.flush()  # get q.id before adding items

    for idx, item_data in enumerate(valid, start=1):
        net_price, item_total = _compute_item(item_data)
        db.add(SalesQuotationItem(
            quotation_id=q.id,
            line_no=idx,
            catalog_no=(item_data.catalog_no or "").strip() or None,
            item_name=item_data.item_name.strip(),
            description=(item_data.description or "").strip() or None,
            qty=item_data.qty,
            unit=item_data.unit,
            unit_price=item_data.unit_price,
            discount=item_data.discount,
            net_price=net_price,
            total=item_total,
        ))

    await db.flush()
    return await _to_response(db, q.id)


async def get_conversion_rate(db: AsyncSession) -> float:
    """Calculate the percentage of quotations that were converted to orders.

    Args:
        db: Active async database session.

    Returns:
        Conversion rate as a percentage (0.0 – 100.0), rounded to 1 decimal.
        Returns 0.0 if no quotations exist yet.
    """
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(
                SalesQuotation.status == SalesQuotationStatus.CONVERTED
            ).label("converted"),
        )
    )
    row = result.one()
    if not row.total:
        return 0.0
    return round((row.converted / row.total) * 100, 1)


async def get_active_quotes_count(db: AsyncSession) -> int:
    """Count quotations currently in DRAFT or SENT status.

    Args:
        db: Active async database session.

    Returns:
        Integer count of active (in-progress) quotations.
    """
    result = await db.execute(
        select(func.count()).select_from(SalesQuotation).where(
            SalesQuotation.status.in_([SalesQuotationStatus.DRAFT, SalesQuotationStatus.SENT])
        )
    )
    return result.scalar_one()


async def list_quotations(
    db: AsyncSession,
    status_filter: Optional[str] = None,
) -> SalesQuotationListResponse:
    """Return all SalesQuotations, optionally filtered by status.

    Args:
        db:            Active async database session.
        status_filter: Optional string value of a ``SalesQuotationStatus``
                       member.  Invalid values are silently ignored.

    Returns:
        A ``SalesQuotationListResponse`` containing matching quotations and
        their total count.
    """
    stmt = (
        select(SalesQuotation)
        .options(selectinload(SalesQuotation.items))
        .order_by(SalesQuotation.created_at.desc())
    )
    if status_filter:
        try:
            st = SalesQuotationStatus(status_filter)
            stmt = stmt.where(SalesQuotation.status == st)
        except ValueError:
            pass   # unknown status value — return unfiltered results
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return SalesQuotationListResponse(
        items=[SalesQuotationResponse.model_validate(r) for r in rows],
        total=len(rows),
    )


async def get_quotation(db: AsyncSession, quote_id) -> SalesQuotationResponse:
    """Fetch a single SalesQuotation by UUID.

    Args:
        db:       Active async database session.
        quote_id: UUID of the target quotation.

    Returns:
        The quotation as a ``SalesQuotationResponse``.

    Raises:
        HTTPException: 404 if not found.
    """
    q = await _load(db, quote_id)
    return SalesQuotationResponse.model_validate(q)


async def update_quotation(
    db: AsyncSession,
    quote_id,
    payload: SalesQuotationUpdate,
) -> SalesQuotationResponse:
    """Replace items and update fields on an existing DRAFT quotation.

    All existing items are deleted and replaced with the items from the
    payload.  Only DRAFT quotations may be edited.

    Args:
        db:       Active async database session.
        quote_id: UUID of the quotation to update.
        payload:  Validated update request.

    Returns:
        The updated quotation as a ``SalesQuotationResponse``.

    Raises:
        HTTPException: 409 if the quotation is not in DRAFT status.
        HTTPException: 400 if no valid items remain after filtering.
    """
    q = await _load(db, quote_id)

    if q.status not in (SalesQuotationStatus.DRAFT,):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot edit a quotation with status '{q.status.value}'",
        )

    valid = _valid_items(payload.items)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quotation must have at least one valid item (non-empty name, qty > 0, unit_price > 0)",
        )

    subtotal, vat, total = _calc_totals(valid)

    # ── Update header fields ──────────────────────────────────────────────────
    q.date = payload.date or q.date
    q.currency = payload.currency
    q.validity = payload.validity
    q.delivery_time = (payload.delivery_time or "").strip() or None
    q.delivery_location = (payload.delivery_location or "").strip() or None
    q.payment_terms = (payload.payment_terms or "").strip() or None
    q.customer_name = (payload.customer_name or "").strip() or None
    q.department = (payload.department or "").strip() or None
    q.contact_person = (payload.contact_person or "").strip() or None
    q.phone = (payload.phone or "").strip() or None
    q.email = (payload.email or "").strip() or None
    q.subject = (payload.subject or "").strip() or "Sales Quotation"
    q.subtotal = subtotal
    q.vat = vat
    q.total = total
    q.remarks = (payload.remarks or "").strip() or None
    q.terms = (payload.terms or "").strip() or None
    if payload.status in ("draft", "sent"):
        q.status = SalesQuotationStatus(payload.status)

    # ── Replace items (delete all, then re-insert) ────────────────────────────
    for old_item in list(q.items):
        await db.delete(old_item)
    await db.flush()

    for idx, item_data in enumerate(valid, start=1):
        net_price, item_total = _compute_item(item_data)
        db.add(SalesQuotationItem(
            quotation_id=q.id,
            line_no=idx,
            catalog_no=(item_data.catalog_no or "").strip() or None,
            item_name=item_data.item_name.strip(),
            description=(item_data.description or "").strip() or None,
            qty=item_data.qty,
            unit=item_data.unit,
            unit_price=item_data.unit_price,
            discount=item_data.discount,
            net_price=net_price,
            total=item_total,
        ))

    await db.flush()
    return await _to_response(db, q.id)


async def update_status(
    db: AsyncSession,
    quote_id,
    new_status_str: str,
    user_id=None,
) -> SalesQuotationResponse:
    """Transition a quotation to a new status via the state machine.

    Sending (DRAFT → SENT) is intentionally blocked here; callers must use
    ``send_quotation`` instead to guarantee email delivery before the state
    is persisted.

    Args:
        db:             Active async database session.
        quote_id:       UUID of the quotation.
        new_status_str: Target status value string.
        user_id:        UUID of the acting user (stored in ``updated_by``).

    Returns:
        Updated quotation as a ``SalesQuotationResponse``.

    Raises:
        HTTPException: 400 if the status string is not a valid enum value.
        HTTPException: 409 if the target status is SENT (use ``send_quotation``).
        HTTPException: 409 if the transition is not allowed from the current status.
    """
    q = await _load(db, quote_id)
    try:
        new_status = SalesQuotationStatus(new_status_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {new_status_str}",
        )

    # Sending must go through send_quotation() to guarantee email delivery
    if new_status == SalesQuotationStatus.SENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Use PUT /quotations/{id}/send to send a quotation — "
                "this ensures the email is actually delivered."
            ),
        )

    allowed = _VALID_TRANSITIONS.get(q.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from '{q.status.value}' to '{new_status.value}'",
        )

    now = datetime.now(timezone.utc)
    q.status = new_status
    q.updated_by = user_id
    if new_status == SalesQuotationStatus.ACCEPTED:
        q.accepted_at = now
    await db.flush()
    return await _to_response(db, q.id)


async def send_quotation(
    db: AsyncSession,
    quote_id,
    user_id=None,
) -> SalesQuotationResponse:
    """Generate a PDF, email it to the client, then mark the quotation as SENT.

    Email is sent synchronously in a thread executor to avoid blocking the
    event loop.  The status is only persisted if the email succeeds — if the
    SMTP call raises, the status remains DRAFT and the exception is surfaced
    as an HTTP 502/503.

    Args:
        db:       Active async database session.
        quote_id: UUID of the quotation to send.
        user_id:  UUID of the acting user (stored in ``updated_by``).

    Returns:
        Updated quotation (status=SENT) as a ``SalesQuotationResponse``.

    Raises:
        HTTPException: 409 if the quotation is not in a sendable state.
        HTTPException: 400 if the quotation has no valid client email address.
        HTTPException: 502 on SMTP authentication failure or other SMTP error.
        HTTPException: 503 if SMTP is not configured.
    """
    q = await _load(db, quote_id)

    allowed = _VALID_TRANSITIONS.get(q.status, set())
    if SalesQuotationStatus.SENT not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot send a quotation with status '{q.status.value}'",
        )
    if not q.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Quotation has no client email address. "
                "Edit the quotation and add one before sending."
            ),
        )
    from app.schemas.sales_quotation import _EMAIL_RE
    if not _EMAIL_RE.match(q.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Client email '{q.email}' is not a valid email address.",
        )

    pdf_buf = _build_pdf(q)

    # ── Offload blocking SMTP call to thread executor ─────────────────────────
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _smtp_send, q, pdf_buf)
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Email failed: SMTP authentication error. Check SMTP_USER and SMTP_PASS in .env.",
        )
    except smtplib.SMTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Email failed: {exc}",
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Email failed: {exc}",
        )

    # Only persist SENT status after successful email delivery
    q.status = SalesQuotationStatus.SENT
    q.sent_at = datetime.now(timezone.utc)
    q.updated_by = user_id
    await db.flush()
    return await _to_response(db, q.id)


async def convert_to_order(
    db: AsyncSession,
    quote_id,
    user_id=None,
) -> SalesOrderResponse:
    """Convert an ACCEPTED SalesQuotation into a SalesOrder.

    Copies all header fields and line items from the quotation to a new
    SalesOrder (status=CONFIRMED), then marks the quotation as CONVERTED.

    Args:
        db:       Active async database session.
        quote_id: UUID of the accepted quotation to convert.
        user_id:  UUID of the acting user.

    Returns:
        The newly created ``SalesOrder`` as a ``SalesOrderResponse``.

    Raises:
        HTTPException: 409 if the quotation is not in ACCEPTED status.
    """
    q = await _load(db, quote_id)

    if q.status != SalesQuotationStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only accepted quotations can be converted to orders "
                f"(current status: '{q.status.value}')"
            ),
        )

    # ── Generate order number ─────────────────────────────────────────────────
    year = datetime.now(timezone.utc).year
    prefix = f"SO-{year}-"
    count_result = await db.execute(
        select(func.count()).select_from(SalesOrder).where(
            SalesOrder.order_number.like(f"{prefix}%")
        )
    )
    n = (count_result.scalar_one() or 0) + 1
    order_number = f"{prefix}{n:04d}"

    # ── Create order header (snapshot from quotation) ─────────────────────────
    order = SalesOrder(
        order_number=order_number,
        quotation_id=q.id,
        customer_name=q.customer_name,
        department=q.department,
        contact_person=q.contact_person,
        phone=q.phone,
        email=q.email,
        subject=q.subject,
        currency=q.currency,
        payment_terms=q.payment_terms,
        delivery_location=q.delivery_location,
        subtotal=q.subtotal,
        vat=q.vat,
        total=q.total,
        remarks=q.remarks,
        status=SalesOrderStatus.CONFIRMED,
    )
    db.add(order)
    await db.flush()

    # ── Copy line items from quotation ────────────────────────────────────────
    for item in q.items:
        db.add(SalesOrderItem(
            order_id=order.id,
            line_no=item.line_no,
            catalog_no=item.catalog_no,
            item_name=item.item_name,
            description=item.description,
            qty=item.qty,
            unit=item.unit,
            unit_price=item.unit_price,
            discount=item.discount,
            net_price=item.net_price,
            total=item.total,
        ))

    # ── Mark quotation as converted ───────────────────────────────────────────
    now = datetime.now(timezone.utc)
    q.status = SalesQuotationStatus.CONVERTED
    q.converted_at = now
    q.updated_by = user_id
    await db.flush()

    result = await db.execute(
        select(SalesOrder)
        .where(SalesOrder.id == order.id)
        .options(selectinload(SalesOrder.items))
    )
    return SalesOrderResponse.model_validate(result.scalar_one())


# ── SMTP helper (blocking — must run in a thread executor) ────────────────────

def _smtp_send(q: SalesQuotation, pdf_buf: BytesIO) -> None:
    """Build and send the quotation email with a PDF attachment (blocking).

    Supports both STARTTLS (port != 465) and implicit SSL (port 465).
    This function must **not** be called directly from an async context;
    always wrap it with ``loop.run_in_executor``.

    Args:
        q:       The ``SalesQuotation`` ORM object (provides recipient address,
                 quote number, totals, etc.).
        pdf_buf: In-memory buffer containing the rendered PDF bytes.

    Raises:
        RuntimeError: If SMTP credentials are not configured in settings.
        smtplib.SMTPAuthenticationError: On login failure.
        smtplib.SMTPException: On any other SMTP-level error.
    """
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    user = settings.SMTP_USER
    pw   = settings.SMTP_PASS

    if not (host and user and pw):
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER, and SMTP_PASS in .env"
        )

    # ── Build display values ──────────────────────────────────────────────────
    client_name   = q.customer_name or q.contact_person or "Valued Client"
    contact_name  = q.contact_person or client_name
    currency      = q.currency or "SAR"
    total_fmt     = f"{currency} {float(q.total or 0):,.2f}"
    validity_line = f"This quotation is valid for {q.validity} days." if q.validity else ""
    subject_line  = q.subject or "Sales Quotation"

    # ── Build multipart MIME message ──────────────────────────────────────────
    msg = MIMEMultipart("alternative")
    msg["From"]    = f"Kytos Smart Management <{user}>"
    msg["To"]      = q.email
    msg["Subject"] = f"Quotation {q.quote_number} — {subject_line}"

    plain = (
        f"Dear {contact_name},\n\n"
        f"Thank you for your interest. Please find attached quotation "
        f"{q.quote_number} prepared for {client_name}.\n\n"
        f"  Quote No : {q.quote_number}\n"
        f"  Total    : {total_fmt}\n"
        f"  Subject  : {subject_line}\n"
        + (f"  Valid for: {q.validity} days\n" if q.validity else "")
        + f"\nTo accept or discuss this quotation, simply reply to this email "
        f"or contact us directly.\n\n"
        f"Best regards,\n"
        f"Kytos Smart Management\n"
    )
    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
        <tr><td style="background:#7c3aed;padding:28px 36px;">
          <span style="color:#ffffff;font-size:22px;font-weight:700;letter-spacing:.5px;">KYTOS</span>
          <span style="color:#c4b5fd;font-size:13px;margin-left:10px;">Smart Management</span>
        </td></tr>
        <tr><td style="padding:32px 36px;">
          <p style="margin:0 0 8px;color:#374151;font-size:15px;">Dear <strong>{contact_name}</strong>,</p>
          <p style="margin:0 0 20px;color:#6b7280;font-size:14px;line-height:1.6;">
            Thank you for your interest. Please find attached quotation
            <strong>{q.quote_number}</strong> prepared for <strong>{client_name}</strong>.
          </p>
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border-radius:6px;padding:16px 20px;margin-bottom:24px;">
            <tr><td style="padding:4px 0;color:#6b7280;font-size:13px;">Quote No</td>
                <td style="padding:4px 0;color:#111827;font-size:13px;font-weight:600;text-align:right;">{q.quote_number}</td></tr>
            <tr><td style="padding:4px 0;color:#6b7280;font-size:13px;">Subject</td>
                <td style="padding:4px 0;color:#111827;font-size:13px;text-align:right;">{subject_line}</td></tr>
            <tr><td style="padding:8px 0 4px;color:#111827;font-size:15px;font-weight:700;border-top:1px solid #e5e7eb;">Total</td>
                <td style="padding:8px 0 4px;color:#7c3aed;font-size:18px;font-weight:700;text-align:right;border-top:1px solid #e5e7eb;">{total_fmt}</td></tr>
          </table>
          {f'<p style="margin:0 0 20px;color:#6b7280;font-size:13px;">{validity_line}</p>' if validity_line else ''}
          <p style="margin:0 0 24px;color:#6b7280;font-size:14px;line-height:1.6;">
            To accept or discuss this quotation, simply reply to this email or contact us directly.
          </p>
          <p style="margin:0;color:#9ca3af;font-size:12px;">
            Best regards,<br><strong style="color:#374151;">Kytos Smart Management</strong>
          </p>
        </td></tr>
        <tr><td style="background:#f9fafb;padding:16px 36px;border-top:1px solid #e5e7eb;">
          <p style="margin:0;color:#9ca3af;font-size:11px;text-align:center;">
            This email was sent automatically. Please do not share this quotation outside your organisation.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    # ── Attach the PDF ────────────────────────────────────────────────────────
    pdf_buf.seek(0)
    attachment = MIMEApplication(pdf_buf.read(), _subtype="pdf")
    attachment.add_header(
        "Content-Disposition", "attachment", filename=f"{q.quote_number}.pdf"
    )
    msg.attach(attachment)

    # ── Deliver — choose SSL/TLS vs STARTTLS based on port ────────────────────
    if port == 465:
        # Implicit SSL/TLS (no STARTTLS upgrade needed)
        with smtplib.SMTP_SSL(host, port, timeout=15) as server:
            server.login(user, pw)
            server.send_message(msg)
    else:
        # STARTTLS upgrade (port 587 default)
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, pw)
            server.send_message(msg)


async def generate_pdf(db: AsyncSession, quote_id) -> StreamingResponse:
    """Render a SalesQuotation as a PDF and return it as a streaming download.

    Args:
        db:       Active async database session.
        quote_id: UUID of the quotation to render.

    Returns:
        A ``StreamingResponse`` with ``Content-Type: application/pdf`` and
        a ``Content-Disposition`` header suggesting a filename.
    """
    q = await _load(db, quote_id)
    buf = _build_pdf(q)
    filename = f"{q.quote_number}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_pdf(q: SalesQuotation) -> BytesIO:  # noqa: C901
    """Render a SalesQuotation to a PDF using ReportLab and return a BytesIO buffer.

    Layout sections:
    1. Header row: logo | company name | quote number
    2. Company address block + quote info grid
    3. "Submitted To" / "From" section tables
    4. Items table with gradient header (green → yellow)
    5. Totals summary (subtotal, VAT 15%, grand total)
    6. Remarks and Terms & Conditions (if set)

    Args:
        q: The ``SalesQuotation`` ORM instance with items eagerly loaded.

    Returns:
        A ``BytesIO`` buffer containing the rendered PDF, seeked to position 0.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image, Flowable,
    )
    from app.config import settings

    # ── Page geometry ─────────────────────────────────────────────────────────
    PAGE_W = A4[0]
    L_MARGIN = R_MARGIN = 15 * mm
    USABLE_W = PAGE_W - L_MARGIN - R_MARGIN   # ≈ 165 mm

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=L_MARGIN, rightMargin=R_MARGIN,
        topMargin=14 * mm, bottomMargin=14 * mm,
    )

    styles = getSampleStyleSheet()

    # ── Colour palette ────────────────────────────────────────────────────────
    PURPLE = colors.HexColor("#7c3aed")
    DKGRAY = colors.HexColor("#374151")
    MGRAY  = colors.HexColor("#6b7280")
    LGRAY  = colors.HexColor("#f3f4f6")
    BORDER = colors.HexColor("#9ca3af")
    YELLOW = colors.HexColor("#fef9c3")
    WHITE  = colors.white

    def S(**kw):
        return ParagraphStyle("_", parent=styles["Normal"], **kw)

    def P(text, style):
        return Paragraph(str(text) if text not in (None, "") else "—", style)

    def _v(v):
        return str(v).strip() if v else "—"

    # ── Text styles ───────────────────────────────────────────────────────────
    logo_s  = S(fontSize=15, fontName="Helvetica-Bold", textColor=PURPLE)
    tag_s   = S(fontSize=7,  textColor=MGRAY)
    qnum_s  = S(fontSize=10, fontName="Helvetica-Bold", textColor=DKGRAY, alignment=2)
    cname_s = S(fontSize=11, fontName="Helvetica-Bold", textColor=DKGRAY, alignment=1)
    addr_s  = S(fontSize=7,  textColor=DKGRAY, leading=11)
    lbl_s   = S(fontSize=7,  fontName="Helvetica-Bold", textColor=DKGRAY)
    val_s   = S(fontSize=7,  textColor=DKGRAY, leading=10)
    sec_s   = S(fontSize=7,  fontName="Helvetica-Bold", textColor=DKGRAY)
    th_s    = S(fontSize=7,  fontName="Helvetica-Bold", textColor=WHITE)
    td_s    = S(fontSize=7,  textColor=DKGRAY, leading=10)
    small_s = S(fontSize=7,  textColor=MGRAY,  leading=10)
    note_s  = S(fontSize=8,  fontName="Helvetica-Bold", textColor=DKGRAY)

    currency = q.currency or "SAR"
    fmt = lambda n: f"{float(n or 0):,.2f}"

    story = []

    # Reusable cell-padding style commands shared by multiple tables
    ROW_PAD = [
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]

    # ── Section 1: Header row ─────────────────────────────────────────────────
    import os as _os
    _logo_path = settings.COMPANY_LOGO_PATH.strip()
    if _logo_path and _os.path.isfile(_logo_path):
        _logo_img = Image(_logo_path)
        _logo_img._restrictSize(40 * mm, 15 * mm)
        logo_cell = _logo_img
    else:
        # Text-only fallback when no logo file is configured
        logo_cell = [P("KYTOS", logo_s), P("Smart Management", tag_s)]

    W1, W2, W3 = USABLE_W * 0.32, USABLE_W * 0.36, USABLE_W * 0.32
    hdr_data = [[
        logo_cell,
        P(settings.COMPANY_NAME, cname_s),
        P(f"QUOTE : {q.quote_number}", qnum_s),
    ]]
    hdr_tbl = Table(hdr_data, colWidths=[W1, W2, W3])
    hdr_tbl.setStyle(TableStyle(ROW_PAD + [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX",    (0, 0), (-1, -1), 0.5, BORDER),
    ]))
    story.append(hdr_tbl)

    # ── Section 2: Company address + quote info grid ──────────────────────────
    s = settings
    addr_raw = s.COMPANY_ADDRESS or ""
    parts = [p.strip() for p in addr_raw.split(",", 1)]
    addr_lines = []
    if parts:
        addr_lines.append(f"{s.COMPANY_NAME} ; {parts[0]}")
    if len(parts) > 1:
        addr_lines.append(parts[1])
    if s.COMPANY_WEBSITE:
        addr_lines.append(f"Website: {s.COMPANY_WEBSITE}")
    if s.COMPANY_PHONE:
        addr_lines.append(f"Phone: {s.COMPANY_PHONE}")
    if s.COMPANY_FAX:
        addr_lines.append(f"Fax: {s.COMPANY_FAX}")
    if s.COMPANY_CONTACT_NAME:
        addr_lines.append(f"Prepared by: {s.COMPANY_CONTACT_NAME}")
    if s.COMPANY_DIRECT_LINE:
        addr_lines.append(f"Direct Line: {s.COMPANY_DIRECT_LINE}")

    LEFT_W = USABLE_W * 0.55
    addr_cell_rows = [[P(line, addr_s)] for line in addr_lines]
    addr_inner = Table(addr_cell_rows, colWidths=[LEFT_W - 4 * mm])
    addr_inner.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))

    RIGHT_W  = USABLE_W - LEFT_W
    INFO_LBL = 35 * mm
    INFO_VAL = RIGHT_W - INFO_LBL

    info_rows = [
        ("Al Sinan Ref No#", _v(q.quote_number)),
        ("Date",             _v(q.date)),
        ("Currency",         _v(q.currency)),
        ("Delivery Time",    _v(q.delivery_time)),
        ("Delivery Point",   _v(q.delivery_location)),
        ("Payment Terms",    _v(q.payment_terms)),
        ("Quote Validity",   _v(q.validity)),
    ]
    info_cells = [[P(lbl, lbl_s), P(val, val_s)] for lbl, val in info_rows]
    info_inner = Table(info_cells, colWidths=[INFO_LBL, INFO_VAL])
    info_inner.setStyle(TableStyle(ROW_PAD + [
        ("GRID",       (0, 0), (-1, -1), 0.4, BORDER),
        ("BACKGROUND", (0, 0), (0,  -1), LGRAY),
        ("BACKGROUND", (1, 3), (1,   3), YELLOW),  # highlight Delivery Time row
    ]))

    t1 = Table([[addr_inner, info_inner]], colWidths=[LEFT_W, RIGHT_W])
    t1.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("BOX",           (0, 0), (-1, -1), 0.5, BORDER),
        ("LINEBEFORE",    (1, 0), (1,  -1), 0.5, BORDER),
    ]))
    story.append(t1)
    story.append(Spacer(1, 4 * mm))

    # ── Section 3: Submitted To / From section ────────────────────────────────

    def make_section(heading, rows, lbl_w, val_w):
        """Build a two-column sub-table with a spanning header row.

        Args:
            heading: Header text spanning both columns.
            rows:    List of ``(label, value)`` tuples for data rows.
            lbl_w:   Width of the label column.
            val_w:   Width of the value column.

        Returns:
            A ReportLab ``Table`` flowable.
        """
        cells = [[P(heading, sec_s), ""]]          # header spans both columns
        for lbl, val in rows:
            cells.append([P(lbl, lbl_s), P(val or "—", val_s)])
        tbl = Table(cells, colWidths=[lbl_w, val_w])
        tbl.setStyle(TableStyle(ROW_PAD + [
            ("SPAN",       (0, 0), (1,  0)),        # merge header row
            ("BACKGROUND", (0, 0), (1,  0), LGRAY), # grey header background
            ("BACKGROUND", (0, 1), (0, -1), LGRAY), # grey label column
            ("GRID",       (0, 0), (-1, -1), 0.4, BORDER),
        ]))
        return tbl

    TO_W   = USABLE_W * 0.55
    FROM_W = USABLE_W - TO_W
    TO_LBL, TO_VAL  = 26 * mm, TO_W   - 26 * mm
    FR_LBL, FR_VAL  = 24 * mm, FROM_W - 24 * mm

    to_rows = [
        ("To Company", q.customer_name),
        ("Department",  q.department),
        ("Attention",   q.contact_person),
        ("Tel No.",     q.phone),
        ("Fax",         q.fax),
        ("E-mail",      q.email),
        ("CC",          q.cc),
        ("Your Ref.",   q.your_ref),
        ("Subject",     q.subject),
    ]
    from_rows = [
        ("From",       s.COMPANY_NAME),
        ("Department", "Sales"),
        ("Tel",        s.COMPANY_PHONE or None),
        ("Fax",        s.COMPANY_FAX   or None),
        ("Email",      s.SMTP_USER     or None),
        ("CC",         None),
    ]

    to_sec   = make_section("Submitted To:", to_rows, TO_LBL, TO_VAL)
    from_sec = make_section("From:",         from_rows, FR_LBL, FR_VAL)

    t2 = Table([[to_sec, from_sec]], colWidths=[TO_W, FROM_W])
    t2.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("BOX",           (0, 0), (-1, -1), 0.5, BORDER),
        ("LINEBEFORE",    (1, 0), (1,  -1), 0.5, BORDER),
    ]))
    story.append(t2)
    story.append(Spacer(1, 4 * mm))

    # ── Section 4: Items table with gradient header ───────────────────────────
    COLS = [
        ("LN",               8 * mm, "CENTER"),
        ("Cat No.",         22 * mm, "LEFT"),
        ("Item Description", 47 * mm, "LEFT"),
        ("QTY",             10 * mm, "CENTER"),
        ("UM",              10 * mm, "CENTER"),
        ("Unit Price",      22 * mm, "RIGHT"),
        ("Discount\n(%)",   16 * mm, "CENTER"),
        ("Unit Net\nPrice", 20 * mm, "RIGHT"),
        ("Total\nAmount",     None,  "RIGHT"),
    ]
    # Compute last column width to fill remaining space
    fixed_w = sum(c[1] for c in COLS if c[1] is not None)
    COLS[-1] = (COLS[-1][0], USABLE_W - fixed_w, COLS[-1][2])
    col_ws = [c[1] for c in COLS]

    # ── Custom flowable: green → yellow gradient header ───────────────────────
    GRN  = colors.HexColor("#2F7936")
    YLW  = colors.HexColor("#FDFD02")
    DTXT = colors.HexColor("#1a2e05")

    class _GradientHeader(Flowable):
        """ReportLab Flowable that draws a left-to-right colour gradient header row.

        Args:
            labels:  Column header strings (``\\n`` for line breaks).
            widths:  Column widths in ReportLab units.
            row_h:   Height of the header row.
        """

        def __init__(self, labels, widths, row_h=14 * mm):
            super().__init__()
            self.labels = labels
            self.widths = widths
            self.height = row_h
            self.width  = sum(widths)

        def draw(self):
            cv = self.canv
            W, H = self.width, self.height
            STEPS = 80
            sw = W / STEPS
            r1, g1, b1 = GRN.red, GRN.green, GRN.blue
            r2, g2, b2 = YLW.red, YLW.green, YLW.blue
            # Draw gradient by painting narrow strips from GRN to YLW
            for i in range(STEPS):
                t = i / max(STEPS - 1, 1)
                cv.setFillColorRGB(
                    r1 + t * (r2 - r1),
                    g1 + t * (g2 - g1),
                    b1 + t * (b2 - b1),
                )
                cv.rect(i * sw, 0, sw + 0.5, H, fill=1, stroke=0)

            # Column labels and vertical separators
            x = 0
            cv.setFont("Helvetica-Bold", 7)
            cv.setFillColor(DTXT)
            for label, cw in zip(self.labels, self.widths):
                if x > 0:
                    cv.setStrokeColor(colors.HexColor("#9ca3af"))
                    cv.setLineWidth(0.3)
                    cv.line(x, 2, x, H - 2)
                lines = label.split("\n")
                line_h = 8
                y0 = (H + len(lines) * line_h) / 2 - line_h * 0.75
                cv.setFillColor(DTXT)
                for j, ln in enumerate(lines):
                    cv.drawCentredString(x + cw / 2, y0 - j * line_h, ln)
                x += cw

            # Outer border
            cv.setStrokeColor(colors.HexColor("#9ca3af"))
            cv.setLineWidth(0.3)
            cv.rect(0, 0, W, H, fill=0, stroke=1)

    # ── Data rows ─────────────────────────────────────────────────────────────
    item_rows = []
    for item in q.items:
        desc = item.item_name or ""
        if item.description:
            desc += f"\n{item.description}"
        item_rows.append([
            P(str(item.line_no),              td_s),
            P(item.catalog_no or "",          td_s),
            P(desc,                           td_s),
            P(f"{float(item.qty):g}",         td_s),
            P(item.unit or "EA",              td_s),
            P(fmt(item.unit_price),           td_s),
            P(f"{float(item.discount):.2f}%", td_s),
            P(fmt(item.net_price),            td_s),
            P(fmt(item.total),                td_s),
        ])

    items_tbl = Table(item_rows, colWidths=col_ws)
    ts_items = [
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LGRAY]),
        ("GRID",           (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN",         (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 3),
    ]
    for ci, (_, _, align) in enumerate(COLS):
        if align == "RIGHT":
            ts_items.append(("ALIGN", (ci, 0), (ci, -1), "RIGHT"))
        elif align == "CENTER":
            ts_items.append(("ALIGN", (ci, 0), (ci, -1), "CENTER"))
    items_tbl.setStyle(TableStyle(ts_items))

    # Wrap gradient header + data table in a single container to keep them
    # perfectly x-aligned (prevents sub-pixel drift between the two Tables)
    grad_hdr = _GradientHeader([c[0] for c in COLS], col_ws)
    wrapper = Table([[grad_hdr], [items_tbl]], colWidths=[USABLE_W])
    wrapper.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(wrapper)
    story.append(Spacer(1, 4 * mm))

    # ── Section 5: Totals ─────────────────────────────────────────────────────
    DKGRN    = colors.HexColor("#1E6F32")
    tot_bold = S(fontSize=9, fontName="Helvetica-Bold", textColor=DKGRN)
    sum_data = [
        [P("Subtotal",    lbl_s),   P(f"{currency}  {fmt(q.subtotal)}", val_s)],
        [P("VAT (15%)",   lbl_s),   P(f"{currency}  {fmt(q.vat)}",      val_s)],
        [P("GRAND TOTAL", tot_bold), P(f"{currency}  {fmt(q.total)}",   tot_bold)],
    ]
    sum_tbl = Table(sum_data, colWidths=[40 * mm, 40 * mm], hAlign="RIGHT")
    sum_tbl.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("BACKGROUND",    (0, 0), (0,  -1), LGRAY),
        ("ALIGN",         (1, 0), (1,  -1), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("LINEABOVE",     (0, 2), (-1,  2), 1.2, DKGRN),  # bold line above grand total
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 5 * mm))

    # ── Section 6: Remarks & Terms (optional) ────────────────────────────────
    if q.remarks:
        story.append(P("REMARKS", note_s))
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=3))
        story.append(P(q.remarks.replace("\n", "<br/>"), small_s))
        story.append(Spacer(1, 4 * mm))
    if q.terms:
        story.append(P("TERMS & CONDITIONS", note_s))
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=3))
        story.append(P(q.terms.replace("\n", "<br/>"), small_s))

    doc.build(story)
    buf.seek(0)
    return buf


async def _to_response(db: AsyncSession, quote_id) -> SalesQuotationResponse:
    """Re-fetch a quotation from the DB and return it as a response schema.

    Used internally to guarantee a fresh, fully-loaded ORM state after any
    write operation (create, update, status change).

    Args:
        db:       Active async database session.
        quote_id: UUID of the quotation to reload.

    Returns:
        The quotation as a ``SalesQuotationResponse``.
    """
    q = await _load(db, quote_id)
    return SalesQuotationResponse.model_validate(q)
