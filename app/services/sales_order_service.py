from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import SalesOrderStatus, SalesQuotationStatus
from app.models.sales_order import SalesOrder
from app.models.sales_order_item import SalesOrderItem
from app.models.sales_quotation import SalesQuotation
from app.schemas.sales_order import SalesOrderCreate, SalesOrderListResponse, SalesOrderResponse


async def _next_order_number(db: AsyncSession) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"SO-{year}-"
    count_result = await db.execute(
        select(func.count()).select_from(SalesOrder).where(
            SalesOrder.order_number.like(f"{prefix}%")
        )
    )
    n = (count_result.scalar_one() or 0) + 1
    return f"{prefix}{n:04d}"


async def _load_quotation(db: AsyncSession, quotation_id) -> SalesQuotation:
    result = await db.execute(
        select(SalesQuotation)
        .where(SalesQuotation.id == quotation_id)
        .options(selectinload(SalesQuotation.items))
    )
    q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales quotation not found")
    return q


async def _load_order(db: AsyncSession, order_id) -> SalesOrder:
    result = await db.execute(
        select(SalesOrder)
        .where(SalesOrder.id == order_id)
        .options(selectinload(SalesOrder.items))
    )
    o = result.scalar_one_or_none()
    if o is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales order not found")
    return o


async def create_from_quotation(db: AsyncSession, payload: SalesOrderCreate) -> SalesOrderResponse:
    q = await _load_quotation(db, payload.quotation_id)

    if q.status not in (SalesQuotationStatus.ACCEPTED, SalesQuotationStatus.SENT):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Quotation must be accepted or sent before converting. Current status: '{q.status.value}'",
        )

    order_number = await _next_order_number(db)

    o = SalesOrder(
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
        subtotal=float(q.subtotal),
        vat=float(q.vat),
        total=float(q.total),
        remarks=q.remarks,
        status=SalesOrderStatus.CONFIRMED,
    )
    db.add(o)
    await db.flush()

    for item in q.items:
        db.add(SalesOrderItem(
            order_id=o.id,
            line_no=item.line_no,
            catalog_no=item.catalog_no,
            item_name=item.item_name,
            description=item.description,
            qty=float(item.qty),
            unit=item.unit,
            unit_price=float(item.unit_price),
            discount=float(item.discount),
            net_price=float(item.net_price),
            total=float(item.total),
        ))

    q.status = SalesQuotationStatus.CONVERTED
    await db.flush()

    result = await db.execute(
        select(SalesOrder)
        .where(SalesOrder.id == o.id)
        .options(selectinload(SalesOrder.items))
    )
    return SalesOrderResponse.model_validate(result.scalar_one())


async def list_orders(db: AsyncSession) -> SalesOrderListResponse:
    result = await db.execute(
        select(SalesOrder)
        .options(selectinload(SalesOrder.items))
        .order_by(SalesOrder.created_at.desc())
    )
    rows = result.scalars().all()
    return SalesOrderListResponse(
        items=[SalesOrderResponse.model_validate(r) for r in rows],
        total=len(rows),
    )


async def get_order(db: AsyncSession, order_id) -> SalesOrderResponse:
    o = await _load_order(db, order_id)
    return SalesOrderResponse.model_validate(o)


_ALLOWED_TRANSITIONS: dict[SalesOrderStatus, SalesOrderStatus] = {
    SalesOrderStatus.CONFIRMED: SalesOrderStatus.SHIPPED,
    SalesOrderStatus.SHIPPED:   SalesOrderStatus.DELIVERED,
}


async def update_order_status(db: AsyncSession, order_id, new_status_str: str) -> SalesOrderResponse:
    try:
        new_status = SalesOrderStatus(new_status_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{new_status_str}'. Must be one of: confirmed, shipped, delivered.",
        )

    o = await _load_order(db, order_id)
    allowed_next = _ALLOWED_TRANSITIONS.get(o.status)

    if allowed_next is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order is already '{o.status.value}' — no further transitions allowed.",
        )
    if new_status != allowed_next:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from '{o.status.value}' to '{new_status.value}'. Expected next status: '{allowed_next.value}'.",
        )

    o.status = new_status
    await db.flush()
    return SalesOrderResponse.model_validate(o)


async def get_total_revenue(db: AsyncSession) -> float:
    result = await db.execute(
        select(func.coalesce(func.sum(SalesOrder.total), 0))
        .where(SalesOrder.status == SalesOrderStatus.DELIVERED)
    )
    return float(result.scalar_one())


_VALID_TRANSITIONS = {
    SalesOrderStatus.CONFIRMED:   SalesOrderStatus.IN_PROGRESS,
    SalesOrderStatus.IN_PROGRESS: SalesOrderStatus.DELIVERED,
}


async def update_status(db: AsyncSession, order_id, new_status: SalesOrderStatus) -> SalesOrderResponse:
    o = await _load_order(db, order_id)
    allowed = _VALID_TRANSITIONS.get(o.status)
    if allowed is None or allowed != new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from '{o.status.value}' to '{new_status.value}'",
        )
    o.status = new_status
    await db.commit()
    result = await db.execute(
        select(SalesOrder)
        .where(SalesOrder.id == o.id)
        .options(selectinload(SalesOrder.items))
    )
    return SalesOrderResponse.model_validate(result.scalar_one())


async def get_top_products(db: AsyncSession, limit: int = 3) -> list[dict]:
    result = await db.execute(
        select(
            SalesOrderItem.item_name.label("name"),
            func.coalesce(func.sum(SalesOrderItem.total), 0).label("revenue"),
        )
        .join(SalesOrder, SalesOrderItem.order_id == SalesOrder.id)
        .where(SalesOrderItem.item_name.isnot(None))
        .group_by(SalesOrderItem.item_name)
        .order_by(func.sum(SalesOrderItem.total).desc())
        .limit(limit)
    )
    return [{"name": row.name, "revenue": float(row.revenue)} for row in result.all()]
