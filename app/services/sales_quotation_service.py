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

_VALID_TRANSITIONS = {
    SalesQuotationStatus.DRAFT:     {SalesQuotationStatus.SENT},
    SalesQuotationStatus.SENT:      {SalesQuotationStatus.ACCEPTED, SalesQuotationStatus.REJECTED},
    SalesQuotationStatus.ACCEPTED:  {SalesQuotationStatus.CONVERTED},
    SalesQuotationStatus.REJECTED:  set(),
    SalesQuotationStatus.CONVERTED: set(),
}


async def _next_quote_number(db: AsyncSession) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"SQ-{year}-"
    count_result = await db.execute(
        select(func.count()).select_from(SalesQuotation).where(
            SalesQuotation.quote_number.like(f"{prefix}%")
        )
    )
    n = (count_result.scalar_one() or 0) + 1
    return f"{prefix}{n:04d}"


def _valid_items(items_data: list) -> list:
    """Keep only items with a non-empty name, positive qty, and positive unit_price."""
    return [
        i for i in items_data
        if (i.item_name or "").strip()
        and float(i.qty) > 0
        and float(i.unit_price) > 0
    ]


def _calc_totals(items_data: list) -> tuple[float, float, float]:
    subtotal = sum(float(i.total) for i in items_data)
    vat = round(subtotal * 0.15, 2)
    total = round(subtotal + vat, 2)
    return subtotal, vat, total


async def _load(db: AsyncSession, quote_id) -> SalesQuotation:
    result = await db.execute(
        select(SalesQuotation)
        .where(SalesQuotation.id == quote_id)
        .options(selectinload(SalesQuotation.items))
    )
    q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales quotation not found")
    return q


async def create_quotation(db: AsyncSession, payload: SalesQuotationCreate) -> SalesQuotationResponse:
    valid = _valid_items(payload.items)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quotation must have at least one valid item (non-empty name, qty > 0, unit_price > 0)",
        )

    quote_number = await _next_quote_number(db)
    subtotal, vat, total = _calc_totals(valid)

    customer_name = (payload.customer_name or "").strip() or None

    q = SalesQuotation(
        quote_number=quote_number,
        date=payload.date or date.today(),
        currency=payload.currency,
        validity=payload.validity,
        delivery_time=(payload.delivery_time or "").strip() or None,
        delivery_location=(payload.delivery_location or "").strip() or None,
        payment_terms=(payload.payment_terms or "").strip() or None,
        customer_name=customer_name,
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
        status=SalesQuotationStatus(payload.status) if payload.status in ("draft", "sent") else SalesQuotationStatus.DRAFT,
        sent_at=datetime.now(timezone.utc) if payload.status == "sent" else None,
    )
    db.add(q)
    await db.flush()

    for idx, item_data in enumerate(valid, start=1):
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
            net_price=item_data.net_price,
            total=item_data.total,
        ))

    await db.flush()
    return await _to_response(db, q.id)


async def get_conversion_rate(db: AsyncSession) -> float:
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(SalesQuotation.status == SalesQuotationStatus.CONVERTED).label("converted"),
        )
    )
    row = result.one()
    if not row.total:
        return 0.0
    return round((row.converted / row.total) * 100, 1)


async def get_active_quotes_count(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(SalesQuotation).where(
            SalesQuotation.status.in_([SalesQuotationStatus.DRAFT, SalesQuotationStatus.SENT])
        )
    )
    return result.scalar_one()


async def list_quotations(db: AsyncSession, status_filter: Optional[str] = None) -> SalesQuotationListResponse:
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
            pass
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return SalesQuotationListResponse(
        items=[SalesQuotationResponse.model_validate(r) for r in rows],
        total=len(rows),
    )


async def get_quotation(db: AsyncSession, quote_id) -> SalesQuotationResponse:
    q = await _load(db, quote_id)
    return SalesQuotationResponse.model_validate(q)


async def update_quotation(db: AsyncSession, quote_id, payload: SalesQuotationUpdate) -> SalesQuotationResponse:
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

    for old_item in list(q.items):
        await db.delete(old_item)
    await db.flush()

    for idx, item_data in enumerate(valid, start=1):
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
            net_price=item_data.net_price,
            total=item_data.total,
        ))

    await db.flush()
    return await _to_response(db, q.id)


async def update_status(db: AsyncSession, quote_id, new_status_str: str) -> SalesQuotationResponse:
    q = await _load(db, quote_id)
    try:
        new_status = SalesQuotationStatus(new_status_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status: {new_status_str}")

    allowed = _VALID_TRANSITIONS.get(q.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from '{q.status.value}' to '{new_status.value}'",
        )

    q.status = new_status
    if new_status == SalesQuotationStatus.SENT:
        q.sent_at = datetime.now(timezone.utc)

    await db.flush()
    return await _to_response(db, q.id)


async def send_quotation(db: AsyncSession, quote_id) -> SalesQuotationResponse:
    """Generate PDF, email it to the client, then mark status = sent."""
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
            detail="Quotation has no client email address. Please add one before sending.",
        )

    pdf_buf = _build_pdf(q)

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

    q.status = SalesQuotationStatus.SENT
    q.sent_at = datetime.now(timezone.utc)
    await db.flush()
    return await _to_response(db, q.id)


async def convert_to_order(db: AsyncSession, quote_id) -> SalesOrderResponse:
    q = await _load(db, quote_id)

    if q.status != SalesQuotationStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only accepted quotations can be converted to orders (current status: '{q.status.value}')",
        )

    year = datetime.now(timezone.utc).year
    prefix = f"SO-{year}-"
    count_result = await db.execute(
        select(func.count()).select_from(SalesOrder).where(SalesOrder.order_number.like(f"{prefix}%"))
    )
    n = (count_result.scalar_one() or 0) + 1
    order_number = f"{prefix}{n:04d}"

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

    q.status = SalesQuotationStatus.CONVERTED
    await db.flush()

    result = await db.execute(
        select(SalesOrder)
        .where(SalesOrder.id == order.id)
        .options(selectinload(SalesOrder.items))
    )
    return SalesOrderResponse.model_validate(result.scalar_one())


def _smtp_send(q: SalesQuotation, pdf_buf: BytesIO) -> None:
    """Blocking SMTP call — run in a thread via run_in_executor."""
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    user = settings.SMTP_USER
    pw   = settings.SMTP_PASS

    if not (host and user and pw):
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER, and SMTP_PASS in .env"
        )

    client_name = q.customer_name or q.contact_person or "Valued Client"

    msg = MIMEMultipart()
    msg["From"]    = user
    msg["To"]      = q.email
    msg["Subject"] = f"Quotation {q.quote_number}"

    body = (
        f"Dear {client_name},\n\n"
        f"Please find attached quotation {q.quote_number}.\n\n"
        f"Let us know if you have any questions.\n\n"
        f"Best regards"
    )
    msg.attach(MIMEText(body, "plain"))

    pdf_buf.seek(0)
    attachment = MIMEApplication(pdf_buf.read(), _subtype="pdf")
    attachment.add_header(
        "Content-Disposition", "attachment", filename=f"{q.quote_number}.pdf"
    )
    msg.attach(attachment)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as server:
            server.login(user, pw)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, pw)
            server.send_message(msg)


async def generate_pdf(db: AsyncSession, quote_id) -> StreamingResponse:
    q = await _load(db, quote_id)
    buf = _build_pdf(q)
    filename = f"{q.quote_number}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_pdf(q: SalesQuotation) -> BytesIO:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=18*mm, bottomMargin=18*mm,
    )

    styles = getSampleStyleSheet()
    PURPLE = colors.HexColor("#7c3aed")
    GRAY   = colors.HexColor("#6b7280")
    LGRAY  = colors.HexColor("#f3f4f6")

    h1 = ParagraphStyle("h1", parent=styles["Normal"], fontSize=22, textColor=PURPLE, fontName="Helvetica-Bold", spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", spaceAfter=4)
    normal = ParagraphStyle("normal", parent=styles["Normal"], fontSize=9, textColor=GRAY, leading=14)
    small  = ParagraphStyle("small",  parent=styles["Normal"], fontSize=8, textColor=GRAY)

    def kv(label, value):
        return Paragraph(f"<b>{label}:</b>  {value or '—'}", normal)

    currency = q.currency or "SAR"
    fmt = lambda n: f"{currency} {float(n or 0):,.2f}"

    story = []

    # ── Header ──
    header_data = [[
        Paragraph("SALES QUOTATION", h1),
        Paragraph(
            f"<b>{q.quote_number}</b><br/>"
            f"<font color='#9ca3af' size='8'>Date: {q.date or '—'}</font><br/>"
            f"<font color='#9ca3af' size='8'>Valid: {q.validity or '—'} days</font>",
            ParagraphStyle("right", parent=styles["Normal"], fontSize=10, alignment=2),
        ),
    ]]
    header_tbl = Table(header_data, colWidths=["60%", "40%"])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(header_tbl)
    story.append(HRFlowable(width="100%", thickness=1, color=PURPLE, spaceAfter=8))

    # ── Info grid ──
    info_data = [
        [kv("Payment Terms", q.payment_terms), kv("Delivery Time", q.delivery_time)],
        [kv("Delivery Location", q.delivery_location), kv("Currency", q.currency)],
    ]
    info_tbl = Table(info_data, colWidths=["50%", "50%"])
    info_tbl.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
    story.append(info_tbl)
    story.append(Spacer(1, 6*mm))

    # ── Submitted To ──
    story.append(Paragraph("SUBMITTED TO", h2))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LGRAY, spaceAfter=4))
    to_data = [
        [kv("Company", q.customer_name), kv("Department", q.department)],
        [kv("Contact", q.contact_person), kv("Phone", q.phone)],
        [kv("Email", q.email), kv("Subject", q.subject)],
    ]
    to_tbl = Table(to_data, colWidths=["50%", "50%"])
    to_tbl.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 3)]))
    story.append(to_tbl)
    story.append(Spacer(1, 6*mm))

    # ── Line Items ──
    story.append(Paragraph("LINE ITEMS", h2))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LGRAY, spaceAfter=4))

    thead = ["#", "Catalog No", "Item Name", "Description", "Qty", "Unit", "Unit Price", "Disc%", "Net Price", "Total"]
    col_w = [8*mm, 22*mm, 30*mm, 50*mm, 10*mm, 10*mm, 20*mm, 12*mm, 22*mm, 22*mm]
    th_style = ParagraphStyle("th", parent=styles["Normal"], fontSize=7, fontName="Helvetica-Bold")
    td_style = ParagraphStyle("td", parent=styles["Normal"], fontSize=7, leading=10)

    rows = [[Paragraph(h, th_style) for h in thead]]
    for item in q.items:
        rows.append([
            Paragraph(str(item.line_no), td_style),
            Paragraph(item.catalog_no or "", td_style),
            Paragraph(item.item_name or "", td_style),
            Paragraph(item.description or "", td_style),
            Paragraph(str(float(item.qty)), td_style),
            Paragraph(item.unit or "EA", td_style),
            Paragraph(f"{float(item.unit_price):,.2f}", td_style),
            Paragraph(f"{float(item.discount):.1f}%", td_style),
            Paragraph(f"{float(item.net_price):,.2f}", td_style),
            Paragraph(f"{float(item.total):,.2f}", td_style),
        ])

    items_tbl = Table(rows, colWidths=col_w, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), PURPLE),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, LGRAY]),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#e5e7eb")),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 3),
        ("RIGHTPADDING",  (0,0), (-1,-1), 3),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 5*mm))

    # ── Summary ──
    sum_data = [
        ["Subtotal",   fmt(q.subtotal)],
        ["VAT (15%)",  fmt(q.vat)],
        ["GRAND TOTAL", fmt(q.total)],
    ]
    sum_tbl = Table(sum_data, colWidths=[40*mm, 35*mm], hAlign="RIGHT")
    sum_tbl.setStyle(TableStyle([
        ("FONTNAME",  (0,0), (-1,-2), "Helvetica"),
        ("FONTNAME",  (0,2), (-1,2),  "Helvetica-Bold"),
        ("FONTSIZE",  (0,0), (-1,-2), 8),
        ("FONTSIZE",  (0,2), (-1,2),  10),
        ("TEXTCOLOR", (0,2), (-1,2),  PURPLE),
        ("ALIGN",     (1,0), (1,-1),  "RIGHT"),
        ("LINEABOVE", (0,2), (-1,2),  0.8, PURPLE),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 6*mm))

    # ── Remarks & Terms ──
    if q.remarks:
        story.append(Paragraph("REMARKS", h2))
        story.append(Paragraph(q.remarks, small))
        story.append(Spacer(1, 4*mm))
    if q.terms:
        story.append(Paragraph("TERMS & CONDITIONS", h2))
        story.append(Paragraph(q.terms.replace("\n", "<br/>"), small))

    doc.build(story)
    buf.seek(0)
    return buf


async def _to_response(db: AsyncSession, quote_id) -> SalesQuotationResponse:
    q = await _load(db, quote_id)
    return SalesQuotationResponse.model_validate(q)
