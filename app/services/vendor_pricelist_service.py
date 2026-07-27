# =============================================================================
# app/services/vendor_pricelist_service.py
# -----------------------------------------------------------------------------
# CRUD for Vendor Pricelists (per-supplier product pricing).
# =============================================================================

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_item import StockItem
from app.models.supplier import Supplier
from app.models.vendor_pricelist import VendorPricelist
from app.schemas.vendor_pricelist import (
    VendorPricelistCreate,
    VendorPricelistListResponse,
    VendorPricelistResponse,
    VendorPricelistUpdate,
)


async def _to_response(db: AsyncSession, row: VendorPricelist) -> VendorPricelistResponse:
    supplier_name = (await db.execute(
        select(Supplier.company_name).where(Supplier.id == row.supplier_id)
    )).scalar_one_or_none()

    product_name = None
    if row.stock_item_id:
        item = (await db.execute(
            select(StockItem.description, StockItem.part_number).where(StockItem.id == row.stock_item_id)
        )).first()
        if item:
            product_name = item.description or item.part_number

    data = VendorPricelistResponse.model_validate(row)
    data.supplier_name = supplier_name
    data.product_name = product_name
    return data


async def list_pricelists(
    db: AsyncSession, supplier_id: Optional[uuid.UUID] = None
) -> VendorPricelistListResponse:
    query = select(VendorPricelist).order_by(VendorPricelist.created_at.desc())
    if supplier_id:
        query = query.where(VendorPricelist.supplier_id == supplier_id)
    rows = (await db.execute(query)).scalars().all()
    items = [await _to_response(db, r) for r in rows]
    return VendorPricelistListResponse(items=items, total=len(items))


async def get_pricelist(db: AsyncSession, pricelist_id: uuid.UUID) -> VendorPricelistResponse:
    row = (await db.execute(
        select(VendorPricelist).where(VendorPricelist.id == pricelist_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor pricelist entry not found.")
    return await _to_response(db, row)


async def _validate_refs(db: AsyncSession, payload: VendorPricelistCreate) -> None:
    supplier = (await db.execute(
        select(Supplier.id).where(Supplier.id == payload.supplier_id)
    )).scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Supplier not found.")
    if payload.stock_item_id:
        item = (await db.execute(
            select(StockItem.id).where(StockItem.id == payload.stock_item_id)
        )).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Product not found.")


async def create_pricelist(db: AsyncSession, payload: VendorPricelistCreate) -> VendorPricelistResponse:
    await _validate_refs(db, payload)
    row = VendorPricelist(**payload.model_dump())
    db.add(row)
    await db.flush()
    await db.refresh(row)
    await db.commit()
    return await _to_response(db, row)


async def update_pricelist(
    db: AsyncSession, pricelist_id: uuid.UUID, payload: VendorPricelistUpdate
) -> VendorPricelistResponse:
    row = (await db.execute(
        select(VendorPricelist).where(VendorPricelist.id == pricelist_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor pricelist entry not found.")
    await _validate_refs(db, payload)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    await db.commit()
    return await _to_response(db, row)


async def delete_pricelist(db: AsyncSession, pricelist_id: uuid.UUID) -> None:
    row = (await db.execute(
        select(VendorPricelist).where(VendorPricelist.id == pricelist_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor pricelist entry not found.")
    await db.delete(row)
    await db.commit()
