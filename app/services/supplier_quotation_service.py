"""
app/services/supplier_quotation_service.py
Business logic for SupplierQuotation (supplier bids on RFQs).

Rules enforced:
- The supplier must already be linked to the RFQ (in rfq_suppliers).
- Each supplier may submit at most one quotation per RFQ.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.rfq import RFQ, rfq_suppliers
from app.models.supplier import Supplier
from app.models.supplier_quotation import SupplierQuotation
from app.schemas.supplier_quotation import (
    QuotationCreate,
    QuotationListResponse,
    QuotationResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_rfq_or_404(db: AsyncSession, rfq_id: uuid.UUID) -> RFQ:
    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} not found.",
        )
    return rfq


async def _get_supplier_or_404(db: AsyncSession, supplier_id: uuid.UUID) -> Supplier:
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id} not found.",
        )
    return supplier


async def _assert_supplier_on_rfq(
    db: AsyncSession, rfq_id: uuid.UUID, supplier_id: uuid.UUID
) -> None:
    """Raise 422 if the supplier is not linked to the given RFQ."""
    result = await db.execute(
        select(rfq_suppliers).where(
            rfq_suppliers.c.rfq_id == rfq_id,
            rfq_suppliers.c.supplier_id == supplier_id,
        )
    )
    if not result.first():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Supplier is not assigned to this RFQ.",
        )


async def _load_quotation(
    db: AsyncSession, quotation_id: uuid.UUID
) -> SupplierQuotation:
    result = await db.execute(
        select(SupplierQuotation)
        .where(SupplierQuotation.id == quotation_id)
        .options(selectinload(SupplierQuotation.supplier))
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Submit a quotation
# ---------------------------------------------------------------------------

async def submit_quotation(
    db: AsyncSession,
    payload: QuotationCreate,
) -> QuotationResponse:
    # Verify RFQ and supplier exist
    await _get_rfq_or_404(db, payload.rfq_id)
    await _get_supplier_or_404(db, payload.supplier_id)

    # Supplier must be linked to the RFQ
    await _assert_supplier_on_rfq(db, payload.rfq_id, payload.supplier_id)

    quotation = SupplierQuotation(
        rfq_id=payload.rfq_id,
        supplier_id=payload.supplier_id,
        unit_price=payload.unit_price,
        notes=payload.notes,
    )
    db.add(quotation)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A quotation from this supplier for this RFQ already exists.",
        )

    quotation_full = await _load_quotation(db, quotation.id)
    return QuotationResponse.model_validate(quotation_full)


# ---------------------------------------------------------------------------
# List quotations for an RFQ
# ---------------------------------------------------------------------------

async def list_quotations_for_rfq(
    db: AsyncSession,
    rfq_id: uuid.UUID,
) -> QuotationListResponse:
    await _get_rfq_or_404(db, rfq_id)

    result = await db.execute(
        select(SupplierQuotation)
        .where(SupplierQuotation.rfq_id == rfq_id)
        .options(selectinload(SupplierQuotation.supplier))
        .order_by(SupplierQuotation.created_at.asc())
    )
    quotations = result.scalars().all()

    return QuotationListResponse(
        items=[QuotationResponse.model_validate(q) for q in quotations],
        total=len(quotations),
    )
