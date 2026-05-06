# =============================================================================
# app/services/sales_order_service.py
# -----------------------------------------------------------------------------
# Business logic for SalesOrder CRUD and status transitions. Orders are
# created by converting an accepted SalesQuotation; their lifecycle follows a
# strict linear state machine: confirmed → shipped → delivered (or cancelled).
# Revenue and top-product statistics are also surfaced from this module for
# the dashboard.
# =============================================================================

from __future__ import annotations

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

# ── State machine: only one valid "next" state per current state ──────────────
# CANCELLED is a terminal state reachable outside this map (direct assignment).
_ALLOWED_TRANSITIONS: dict[SalesOrderStatus, SalesOrderStatus] = {
    SalesOrderStatus.CONFIRMED: SalesOrderStatus.SHIPPED,
    SalesOrderStatus.SHIPPED:   SalesOrderStatus.DELIVERED,
}


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _next_order_number(db: AsyncSession) -> str:
    """Generate the next sequential SalesOrder number for the current year.

    Format: ``SO-{YYYY}-{NNNN}`` (e.g. ``SO-2026-0007``).

    Args:
        db: Active async database session.

    Returns:
        A unique order number string.
    """
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
    """Fetch a SalesQuotation by ID with items eagerly loaded.

    Args:
        db:            Active async database session.
        quotation_id:  UUID of the quotation.

    Returns:
        The ``SalesQuotation`` ORM instance.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(
        select(SalesQuotation)
        .where(SalesQuotation.id == quotation_id)
        .options(selectinload(SalesQuotation.items))
    )
    q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales quotation not found",
        )
    return q


async def _load_order(db: AsyncSession, order_id) -> SalesOrder:
    """Fetch a SalesOrder by ID with items eagerly loaded.

    Args:
        db:       Active async database session.
        order_id: UUID of the order.

    Returns:
        The ``SalesOrder`` ORM instance.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(
        select(SalesOrder)
        .where(SalesOrder.id == order_id)
        .options(selectinload(SalesOrder.items))
    )
    o = result.scalar_one_or_none()
    if o is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found",
        )
    return o


# ── Public service functions ──────────────────────────────────────────────────

async def create_from_quotation(
    db: AsyncSession,
    payload: SalesOrderCreate,
) -> SalesOrderResponse:
    """Create a SalesOrder by converting an accepted SalesQuotation.

    Copies all header fields and line items from the quotation.  Sets the
    quotation's status to CONVERTED so it cannot be converted again.

    Args:
        db:      Active async database session.
        payload: Create request containing the source ``quotation_id``.

    Returns:
        The newly created ``SalesOrder`` as a ``SalesOrderResponse``.

    Raises:
        HTTPException: 404 if the quotation does not exist.
        HTTPException: 409 if the quotation is not in ACCEPTED status.
    """
    q = await _load_quotation(db, payload.quotation_id)

    if q.status != SalesQuotationStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only accepted quotations can be converted to orders. "
                f"Current status: '{q.status.value}'"
            ),
        )

    order_number = await _next_order_number(db)

    # ── Create order (snapshot all fields from quotation) ─────────────────────
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

    # ── Copy line items ───────────────────────────────────────────────────────
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

    # ── Mark source quotation as converted ────────────────────────────────────
    q.status = SalesQuotationStatus.CONVERTED
    await db.flush()

    result = await db.execute(
        select(SalesOrder)
        .where(SalesOrder.id == o.id)
        .options(selectinload(SalesOrder.items))
    )
    return SalesOrderResponse.model_validate(result.scalar_one())


async def list_orders(db: AsyncSession) -> SalesOrderListResponse:
    """Return all SalesOrders ordered by creation date descending.

    Args:
        db: Active async database session.

    Returns:
        A ``SalesOrderListResponse`` containing all orders and their total count.
    """
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
    """Fetch a single SalesOrder by UUID.

    Args:
        db:       Active async database session.
        order_id: UUID of the order to retrieve.

    Returns:
        The order as a ``SalesOrderResponse``.

    Raises:
        HTTPException: 404 if not found.
    """
    o = await _load_order(db, order_id)
    return SalesOrderResponse.model_validate(o)


async def get_total_revenue(db: AsyncSession) -> float:
    """Sum ``total`` across all DELIVERED SalesOrders.

    Only DELIVERED orders contribute to revenue — confirmed or shipped orders
    are still in transit and not yet recognised as income.

    Args:
        db: Active async database session.

    Returns:
        Total revenue as a float (0.0 if no delivered orders exist).
    """
    result = await db.execute(
        select(func.coalesce(func.sum(SalesOrder.total), 0))
        .where(SalesOrder.status == SalesOrderStatus.DELIVERED)
    )
    return float(result.scalar_one())


async def update_order_status(
    db: AsyncSession,
    order_id,
    new_status_str: str,
    user_id=None,
) -> SalesOrderResponse:
    """Advance a SalesOrder to the next step in its fulfillment workflow.

    The transition map enforces: ``confirmed → shipped → delivered``.
    No other transitions (including backwards or skipping steps) are allowed.

    Args:
        db:             Active async database session.
        order_id:       UUID of the order to update.
        new_status_str: Target status string value.
        user_id:        UUID of the acting user (stored in ``updated_by``).

    Returns:
        Updated order as a ``SalesOrderResponse``.

    Raises:
        HTTPException: 400 if the status string is not a valid enum value.
        HTTPException: 400 if the current status is terminal or the target
            status is not the allowed next step.
    """
    try:
        new_status = SalesOrderStatus(new_status_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status '{new_status_str}'. "
                "Allowed values: confirmed, shipped, delivered."
            ),
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
            detail=(
                f"Cannot transition from '{o.status.value}' to '{new_status.value}'. "
                f"Expected: '{allowed_next.value}'."
            ),
        )

    now = datetime.now(timezone.utc)
    o.status = new_status
    o.updated_by = user_id
    # Record timestamp for each fulfillment milestone
    if new_status == SalesOrderStatus.SHIPPED:
        o.shipped_at = now
    elif new_status == SalesOrderStatus.DELIVERED:
        o.delivered_at = now

    await db.commit()
    await db.refresh(o)
    result = await db.execute(
        select(SalesOrder)
        .where(SalesOrder.id == o.id)
        .options(selectinload(SalesOrder.items))
    )
    return SalesOrderResponse.model_validate(result.scalar_one())


async def get_top_products(db: AsyncSession, limit: int = 3) -> list[dict]:
    """Return the top N products by total revenue across all SalesOrders.

    Groups by item name and sums the ``total`` column across all order items,
    returning results ordered by revenue descending.

    Args:
        db:    Active async database session.
        limit: Maximum number of products to return (default 3).

    Returns:
        A list of ``{"name": str, "revenue": float}`` dicts.
    """
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
