"""
app/routers/quotations.py

Supplier quotation endpoints:
  POST  /api/v1/quotations/   — supplier submits a quotation for an RFQ
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.supplier_quotation import QuotationCreate, QuotationResponse
from app.services import supplier_quotation_service

router = APIRouter()

@router.post(
    "",
    response_model=QuotationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a supplier quotation for an RFQ",
)
async def submit_quotation(
    payload: QuotationCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Submit a supplier's price offer for an RFQ.

    **Rules:**
    - The supplier must already be linked to the RFQ.
    - Each supplier can submit at most **one** quotation per RFQ.
    """
    return await supplier_quotation_service.submit_quotation(db, payload)
