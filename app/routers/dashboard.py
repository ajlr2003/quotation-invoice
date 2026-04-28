from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.enums import SalesQuotationStatus
from app.models.sales_order import SalesOrder
from app.models.sales_quotation import SalesQuotation

router = APIRouter()

_ACTIVE_STATUSES = (
    SalesQuotationStatus.DRAFT,
    SalesQuotationStatus.SENT,
    SalesQuotationStatus.ACCEPTED,
)


@router.get("/sales", summary="Sales dashboard KPIs")
async def sales_kpis(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    revenue_result = await db.execute(
        select(func.coalesce(func.sum(SalesOrder.total), 0))
    )
    total_revenue = float(revenue_result.scalar_one())

    quotes_result = await db.execute(
        select(func.count()).select_from(SalesQuotation).where(
            SalesQuotation.status.in_(_ACTIVE_STATUSES)
        )
    )
    active_quotes = int(quotes_result.scalar_one())

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

    conversion_rate = round(converted_quotes / total_quotes * 100, 1) if total_quotes > 0 else 0.0

    return {
        "total_revenue": total_revenue,
        "active_quotes": active_quotes,
        "conversion_rate": conversion_rate,
    }
