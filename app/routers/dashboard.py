# =============================================================================
# app/routers/dashboard.py
# -----------------------------------------------------------------------------
# Aggregated KPI endpoint for the sales dashboard. Returns a single JSON
# payload containing total revenue, active quote count, conversion rate, and
# top-5 products — all computed with individual SQL aggregation queries.
# =============================================================================

from __future__ import annotations

import calendar
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.enums import SalesQuotationStatus
from app.models.sales_order import SalesOrder
from app.models.sales_order_item import SalesOrderItem
from app.models.sales_quotation import SalesQuotation

router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────────────────
# Quotation statuses considered "active" (in-flight, not terminal)
_ACTIVE_STATUSES = (
    SalesQuotationStatus.DRAFT,
    SalesQuotationStatus.SENT,
    SalesQuotationStatus.ACCEPTED,
)


@router.get("/sales", summary="Sales dashboard KPIs")
async def sales_kpis(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> dict:
    """Return aggregated KPIs for the sales dashboard.

    Executes four separate aggregation queries and returns the results in a
    single JSON object to minimise round-trips from the frontend.

    Args:
        db:           Injected async database session.

    Returns:
        A dict with keys:
        - ``total_revenue``     : Sum of all SalesOrder totals (all statuses).
        - ``active_quotes``     : Count of draft/sent/accepted quotations.
        - ``conversion_rate``   : Percentage of quotations converted to orders.
        - ``orders_this_month`` : Count of SalesOrders created since the 1st of this month.
        - ``orders_change_pct`` : % change in order count vs. the same period last month
                                  (``None`` if last month had zero orders — undefined ratio).
        - ``top_products``      : Up to 5 products ranked by total revenue, each with
                                   its revenue and the number of order lines it appeared on.
    """
    # ── Total revenue (all orders, regardless of status) ─────────────────────
    revenue_result = await db.execute(
        select(func.coalesce(func.sum(SalesOrder.total), 0))
    )
    total_revenue = float(revenue_result.scalar_one())

    # ── Active quotations (draft + sent + accepted) ───────────────────────────
    quotes_result = await db.execute(
        select(func.count()).select_from(SalesQuotation).where(
            SalesQuotation.status.in_(_ACTIVE_STATUSES)
        )
    )
    active_quotes = int(quotes_result.scalar_one())

    # ── Conversion rate ───────────────────────────────────────────────────────
    total_result = await db.execute(
        select(func.count()).select_from(SalesQuotation)
    )
    total_quotes = int(total_result.scalar_one())

    converted_result = await db.execute(
        select(func.count()).select_from(SalesQuotation).where(
            SalesQuotation.status == SalesQuotationStatus.CONVERTED
        )
    )
    converted_quotes = int(converted_result.scalar_one())

    # Avoid division by zero when no quotations exist yet
    conversion_rate = (
        round(converted_quotes / total_quotes * 100, 1) if total_quotes > 0 else 0.0
    )

    # ── Top 5 products by revenue (with order-line count for the "Orders by
    #    Product" breakdown — there's no product-category taxonomy in the
    #    schema, so per-product is the only real grouping available) ─────────
    top_products_result = await db.execute(
        select(
            SalesOrderItem.item_name,
            func.sum(SalesOrderItem.total).label("revenue"),
            func.count().label("order_count"),
        )
        .where(SalesOrderItem.item_name.isnot(None))
        .group_by(SalesOrderItem.item_name)
        .order_by(func.sum(SalesOrderItem.total).desc())
        .limit(5)
    )
    top_products = [
        {
            "name": row.item_name,
            "revenue": float(row.revenue),
            "order_count": int(row.order_count),
        }
        for row in top_products_result.all()
    ]

    # ── Orders this month vs. same period last month ─────────────────────────
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 1:
        prev_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_month_start = month_start.replace(month=month_start.month - 1)

    this_month_result = await db.execute(
        select(func.count()).select_from(SalesOrder).where(
            SalesOrder.created_at >= month_start
        )
    )
    orders_this_month = int(this_month_result.scalar_one())

    prev_month_result = await db.execute(
        select(func.count()).select_from(SalesOrder).where(
            SalesOrder.created_at >= prev_month_start,
            SalesOrder.created_at < month_start,
        )
    )
    orders_prev_month = int(prev_month_result.scalar_one())

    orders_change_pct = (
        round((orders_this_month - orders_prev_month) / orders_prev_month * 100, 1)
        if orders_prev_month > 0
        else None
    )

    return {
        "total_revenue": total_revenue,
        "active_quotes": active_quotes,
        "conversion_rate": conversion_rate,
        "orders_this_month": orders_this_month,
        "orders_change_pct": orders_change_pct,
        "top_products": top_products,
    }


def _trailing_months(n: int) -> list[tuple[int, int]]:
    """Return the last `n` (year, month) pairs ending with the current month."""
    now = datetime.now(timezone.utc)
    months = []
    y, m = now.year, now.month
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


@router.get("/revenue-trend", summary="Monthly revenue trend (last 6 months) + order data completeness")
async def revenue_trend(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> dict:
    """
    Real monthly revenue series computed from SalesOrder rows (no synthetic
    data). Used by the Intelligence page to derive a simple linear-trend
    forecast rather than showing a hardcoded prediction.

    Returns:
        - ``months``: last 6 months, each ``{label, total, order_count}``.
        - ``total_orders`` / ``data_completeness_pct``: share of SalesOrders
          with a positive total, used as an honest "data health" signal
          (there's no real ML model to score, so we score data quality instead).
    """
    months_out = []
    for (y, m) in _trailing_months(6):
        result = await db.execute(
            select(
                func.coalesce(func.sum(SalesOrder.total), 0),
                func.count(),
            ).where(
                extract("year", SalesOrder.created_at) == y,
                extract("month", SalesOrder.created_at) == m,
            )
        )
        total, count = result.one()
        months_out.append({
            "label": calendar.month_abbr[m],
            "total": float(total),
            "order_count": int(count),
        })

    total_orders = int((await db.execute(select(func.count()).select_from(SalesOrder))).scalar_one())
    valid_orders = int((await db.execute(
        select(func.count()).select_from(SalesOrder).where(SalesOrder.total > 0)
    )).scalar_one())
    data_completeness_pct = round(valid_orders / total_orders * 100, 1) if total_orders > 0 else None

    return {
        "months": months_out,
        "total_orders": total_orders,
        "data_completeness_pct": data_completeness_pct,
    }
