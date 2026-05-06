# =============================================================================
# app/routers/sales_quotations.py
# -----------------------------------------------------------------------------
# FastAPI router for the outbound Sales Quotation endpoints. All routes are
# mounted under /api/v1/sales/quotations by the application factory. Write
# operations (create, update, send, status transitions) require ADMIN, MANAGER,
# or SALES roles; read operations require any authenticated user.
#
# Routes:
#   POST   /                        — create a new quotation
#   GET    /                        — list all quotations (optional ?status=)
#   GET    /stats/conversion-rate   — % of quotations converted
#   GET    /stats/active            — count of draft + sent quotations
#   GET    /{id}                    — get single quotation
#   PUT    /{id}                    — full update (draft only)
#   PATCH  /{id}/status             — transition status
#   PUT    /{id}/send               — generate PDF + email, then mark sent
#   PUT    /{id}/accept             — mark accepted by client
#   PUT    /{id}/reject             — mark rejected by client
#   POST   /{id}/convert            — convert accepted quotation to sales order
#   GET    /{id}/pdf                — download quotation as PDF
# =============================================================================

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.sales_order import SalesOrderResponse
from app.schemas.sales_quotation import (
    SalesQuotationCreate,
    SalesQuotationListResponse,
    SalesQuotationResponse,
    SalesQuotationStatusUpdate,
    SalesQuotationUpdate,
)
from app.services import sales_quotation_service

# ── Role guard for mutating operations ───────────────────────────────────────
_sales_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.SALES)


# ── Local response models (small enough to live here) ────────────────────────

class ActiveQuotesResponse(BaseModel):
    """Response body for the active-quotes count endpoint."""
    active_quotes: int


class ConversionRateResponse(BaseModel):
    """Response body for the conversion-rate statistics endpoint."""
    conversion_rate: float


router = APIRouter()


# ── Create ────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=SalesQuotationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a sales quotation",
)
async def create_quotation(
    payload: SalesQuotationCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_sales_roles),
) -> SalesQuotationResponse:
    """Create a new SalesQuotation in DRAFT status.

    Requires ADMIN, MANAGER, or SALES role.

    Args:
        payload:      Validated quotation create request.
        db:           Injected async database session.
        current_user: Authenticated user with a permitted role.

    Returns:
        The newly created quotation.
    """
    return await sales_quotation_service.create_quotation(db, payload)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=SalesQuotationListResponse,
    summary="List all sales quotations",
)
async def list_quotations(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> SalesQuotationListResponse:
    """Return all SalesQuotations, optionally filtered by status.

    Args:
        status_filter: Optional status string to filter results.
        db:            Injected async database session.

    Returns:
        Paginated list of quotations.
    """
    return await sales_quotation_service.list_quotations(db, status_filter)


# ── Statistics ────────────────────────────────────────────────────────────────

@router.get(
    "/stats/conversion-rate",
    response_model=ConversionRateResponse,
    summary="Conversion rate: converted quotations / total quotations * 100",
)
async def get_conversion_rate(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> ConversionRateResponse:
    """Return the percentage of quotations that were converted to orders.

    Args:
        db: Injected async database session.

    Returns:
        Conversion rate as a percentage value.
    """
    rate = await sales_quotation_service.get_conversion_rate(db)
    return ConversionRateResponse(conversion_rate=rate)


@router.get(
    "/stats/active",
    response_model=ActiveQuotesResponse,
    summary="Count of active (draft + sent) quotations",
)
async def get_active_quotes(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> ActiveQuotesResponse:
    """Return the number of quotations currently in DRAFT or SENT status.

    Args:
        db: Injected async database session.

    Returns:
        Count of active quotations.
    """
    count = await sales_quotation_service.get_active_quotes_count(db)
    return ActiveQuotesResponse(active_quotes=count)


# ── Single quotation ──────────────────────────────────────────────────────────

@router.get(
    "/{quote_id}",
    response_model=SalesQuotationResponse,
    summary="Get a single sales quotation",
)
async def get_quotation(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> SalesQuotationResponse:
    """Fetch a SalesQuotation by UUID with all line items.

    Args:
        quote_id: UUID path parameter identifying the quotation.
        db:       Injected async database session.

    Returns:
        The requested quotation.

    Raises:
        HTTPException: 404 if not found.
    """
    return await sales_quotation_service.get_quotation(db, quote_id)


# ── Update ────────────────────────────────────────────────────────────────────

@router.put(
    "/{quote_id}",
    response_model=SalesQuotationResponse,
    summary="Update a sales quotation (draft only)",
)
async def update_quotation(
    quote_id: uuid.UUID,
    payload: SalesQuotationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_sales_roles),
) -> SalesQuotationResponse:
    """Replace all fields and items on a DRAFT quotation.

    Only DRAFT quotations may be edited.  Requires ADMIN, MANAGER, or SALES role.

    Args:
        quote_id: UUID of the quotation to update.
        payload:  Validated update request body.
        db:       Injected async database session.

    Returns:
        The updated quotation.
    """
    return await sales_quotation_service.update_quotation(db, quote_id, payload)


# ── Status transitions ────────────────────────────────────────────────────────

@router.patch(
    "/{quote_id}/status",
    response_model=SalesQuotationResponse,
    summary="Transition quotation status (sent → accepted / rejected, etc.)",
)
async def update_status(
    quote_id: uuid.UUID,
    payload: SalesQuotationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SalesQuotationResponse:
    """Advance a quotation to a new status via the state machine.

    Note: use ``PUT /{id}/send`` to transition to SENT — that route also
    triggers email delivery.

    Args:
        quote_id: UUID of the quotation.
        payload:  Contains the target ``status`` string.
        db:       Injected async database session.

    Returns:
        The updated quotation.
    """
    return await sales_quotation_service.update_status(
        db, quote_id, payload.status, user_id=current_user.id
    )


@router.put(
    "/{quote_id}/send",
    response_model=SalesQuotationResponse,
    summary="Generate PDF and email quotation to client, then mark as sent",
)
async def send_quotation(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SalesQuotationResponse:
    """Render a PDF, email it to the client, then persist status=SENT.

    The status is only updated if the email is delivered successfully.

    Args:
        quote_id:     UUID of the quotation to send.
        db:           Injected async database session.
        current_user: Authenticated user (ID stored in ``updated_by``).

    Returns:
        The updated quotation with status=SENT and ``sent_at`` populated.
    """
    return await sales_quotation_service.send_quotation(
        db, quote_id, user_id=current_user.id
    )


@router.put(
    "/{quote_id}/accept",
    response_model=SalesQuotationResponse,
    summary="Mark quotation as accepted by client",
)
async def accept_quotation(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SalesQuotationResponse:
    """Transition a SENT quotation to ACCEPTED status.

    Args:
        quote_id:     UUID of the quotation.
        db:           Injected async database session.
        current_user: Authenticated user (ID stored in ``updated_by``).

    Returns:
        The updated quotation.
    """
    return await sales_quotation_service.update_status(
        db, quote_id, "accepted", user_id=current_user.id
    )


@router.put(
    "/{quote_id}/reject",
    response_model=SalesQuotationResponse,
    summary="Mark quotation as rejected by client",
)
async def reject_quotation(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SalesQuotationResponse:
    """Transition a SENT quotation to REJECTED status.

    Args:
        quote_id:     UUID of the quotation.
        db:           Injected async database session.
        current_user: Authenticated user (ID stored in ``updated_by``).

    Returns:
        The updated quotation.
    """
    return await sales_quotation_service.update_status(
        db, quote_id, "rejected", user_id=current_user.id
    )


# ── Convert to order ──────────────────────────────────────────────────────────

@router.post(
    "/{quote_id}/convert",
    response_model=SalesOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Convert an accepted quotation into a sales order",
)
async def convert_to_order(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SalesOrderResponse:
    """Convert an ACCEPTED SalesQuotation into a confirmed SalesOrder.

    Args:
        quote_id:     UUID of the accepted quotation.
        db:           Injected async database session.
        current_user: Authenticated user (ID stored in order ``updated_by``).

    Returns:
        The newly created SalesOrder.
    """
    return await sales_quotation_service.convert_to_order(
        db, quote_id, user_id=current_user.id
    )


# ── PDF download ──────────────────────────────────────────────────────────────

@router.get(
    "/{quote_id}/pdf",
    summary="Download quotation as PDF",
)
async def download_pdf(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Render and stream a SalesQuotation as a downloadable PDF file.

    Args:
        quote_id: UUID of the quotation to render.
        db:       Injected async database session.

    Returns:
        A ``StreamingResponse`` with ``Content-Type: application/pdf``.
    """
    return await sales_quotation_service.generate_pdf(db, quote_id)
