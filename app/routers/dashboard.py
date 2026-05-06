# =============================================================================
# app/routers/dashboard.py
# -----------------------------------------------------------------------------
# Aggregated KPI endpoint for the sales dashboard. Returns a single JSON
# payload containing total revenue, active quote count, conversion rate, and
# top-5 products — all computed with individual SQL aggregation queries.
# =============================================================================

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
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
        - ``total_revenue``  : Sum of all SalesOrder totals (all statuses).
        - ``active_quotes``  : Count of draft/sent/accepted quotations.
        - ``conversion_rate``: Percentage of quotations converted to orders.
        - ``top_products``   : Up to 5 products ranked by total revenue.
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

    # ── Top 5 products by revenue ─────────────────────────────────────────────
    top_products_result = await db.execute(
        select(
            SalesOrderItem.item_name,
            func.sum(SalesOrderItem.total).label("revenue"),
        )
        .where(SalesOrderItem.item_name.isnot(None))
        .group_by(SalesOrderItem.item_name)
        .order_by(func.sum(SalesOrderItem.total).desc())
        .limit(5)
    )
    top_products = [
        {"name": row.item_name, "revenue": float(row.revenue)}
        for row in top_products_result.all()
    ]

    return {
        "total_revenue": total_revenue,
        "active_quotes": active_quotes,
        "conversion_rate": conversion_rate,
        "top_products": top_products,
    }
