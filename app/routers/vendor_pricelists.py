# =============================================================================
# app/routers/vendor_pricelists.py
# -----------------------------------------------------------------------------
# GET    /api/v1/vendor-pricelists            — list (optionally by supplier)
# POST   /api/v1/vendor-pricelists            — create
# GET    /api/v1/vendor-pricelists/{id}       — get one
# PUT    /api/v1/vendor-pricelists/{id}       — update
# DELETE /api/v1/vendor-pricelists/{id}       — delete
# =============================================================================

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.vendor_pricelist import (
    VendorPricelistCreate,
    VendorPricelistListResponse,
    VendorPricelistResponse,
    VendorPricelistUpdate,
)
from app.services import vendor_pricelist_service

router = APIRouter()

_purchase_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.PURCHASER)


@router.get("", response_model=VendorPricelistListResponse, summary="List vendor pricelists")
async def list_vendor_pricelists(
    supplier_id: Optional[uuid.UUID] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await vendor_pricelist_service.list_pricelists(db, supplier_id=supplier_id)


@router.post("", response_model=VendorPricelistResponse, status_code=status.HTTP_201_CREATED, summary="Create a vendor pricelist entry")
async def create_vendor_pricelist(
    payload: VendorPricelistCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(_purchase_roles),
):
    return await vendor_pricelist_service.create_pricelist(db, payload)


@router.get("/{pricelist_id}", response_model=VendorPricelistResponse, summary="Get a vendor pricelist entry")
async def get_vendor_pricelist(
    pricelist_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return await vendor_pricelist_service.get_pricelist(db, pricelist_id)


@router.put("/{pricelist_id}", response_model=VendorPricelistResponse, summary="Update a vendor pricelist entry")
async def update_vendor_pricelist(
    pricelist_id: uuid.UUID,
    payload: VendorPricelistUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(_purchase_roles),
):
    return await vendor_pricelist_service.update_pricelist(db, pricelist_id, payload)


@router.delete("/{pricelist_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a vendor pricelist entry")
async def delete_vendor_pricelist(
    pricelist_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(_purchase_roles),
):
    await vendor_pricelist_service.delete_pricelist(db, pricelist_id)
