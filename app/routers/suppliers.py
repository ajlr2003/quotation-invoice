"""
app/routers/suppliers.py

POST   /api/v1/suppliers               — create supplier
GET    /api/v1/suppliers               — list suppliers (paginated + search)
GET    /api/v1/suppliers/{id}          — get supplier by ID
PATCH  /api/v1/suppliers/{id}          — partial update
DELETE /api/v1/suppliers/{id}          — soft delete (deactivate)

All endpoints require a valid JWT (authenticated users only).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.supplier import (
    SupplierCreateRequest,
    SupplierUpdateRequest,
    SupplierResponse,
    SupplierListResponse,
)
from app.services import supplier_service

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /suppliers  — Create
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new supplier",
)
async def create_supplier(
    payload: SupplierCreateRequest,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),   # JWT guard
):
    """Register a new supplier/vendor in the system."""
    return await supplier_service.create_supplier(db, payload)


# ---------------------------------------------------------------------------
# GET /suppliers  — List (paginated)
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=SupplierListResponse,
    summary="List suppliers",
)
async def list_suppliers(
    page: int           = Query(default=1, ge=1, description="Page number"),
    page_size: int      = Query(default=20, ge=1, le=100, description="Items per page"),
    search: Optional[str]       = Query(default=None, description="Search by name, email, or contact"),
    is_active: Optional[bool]   = Query(default=None, description="Filter by active status"),
    is_preferred: Optional[bool]= Query(default=None, description="Filter preferred suppliers"),
    country: Optional[str]      = Query(default=None, description="Filter by country"),
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Return a paginated list of suppliers.
    Supports search and filtering by status, preference, and country.
    """
    return await supplier_service.list_suppliers(
        db=db,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        is_preferred=is_preferred,
        country=country,
    )


# ---------------------------------------------------------------------------
# GET /suppliers/{supplier_id}  — Get by ID
# ---------------------------------------------------------------------------

@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Get supplier by ID",
)
async def get_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Fetch a single supplier by their UUID."""
    return await supplier_service.get_supplier(db, supplier_id)


# ---------------------------------------------------------------------------
# PATCH /suppliers/{supplier_id}  — Partial update
# ---------------------------------------------------------------------------

@router.patch(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Update supplier details",
)
async def update_supplier(
    supplier_id: uuid.UUID,
    payload: SupplierUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Partially update a supplier record.
    Only the fields included in the request body are updated.
    """
    return await supplier_service.update_supplier(db, supplier_id, payload)


# ---------------------------------------------------------------------------
# DELETE /suppliers/{supplier_id}  — Soft delete
# ---------------------------------------------------------------------------

@router.delete(
    "/{supplier_id}",
    status_code=status.HTTP_200_OK,
    summary="Deactivate a supplier",
)
async def delete_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Soft-delete a supplier by setting is_active = False.
    Suppliers with pending quotes cannot be deactivated.
    """
    return await supplier_service.delete_supplier(db, supplier_id)
