# =============================================================================
# app/schemas/sales_quotation.py
# -----------------------------------------------------------------------------
# Pydantic request/response schemas for the Sales Quotation endpoints.
# Includes validation for email addresses and customer name, as well as
# server-side price computation fields (net_price, total) that are accepted
# from the client but always overwritten by the service layer.
# =============================================================================

from __future__ import annotations

import re
import uuid
from datetime import date as _Date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Internal email regex ──────────────────────────────────────────────────────
# Used both here and in the service layer to validate the quotation email
# before attempting SMTP delivery.
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# ── Item schemas ──────────────────────────────────────────────────────────────

class SalesQuotationItemCreate(BaseModel):
    """Request body for a single quotation line item.

    ``net_price`` and ``total`` are accepted from the client for convenience
    but are always recomputed server-side to prevent tampering.
    """

    line_no: int = 1
    catalog_no: Optional[str] = None
    item_name: str = Field(min_length=1)
    description: Optional[str] = None
    qty: float = Field(gt=0)
    unit: str = "EA"
    unit_price: float = Field(ge=0)
    discount: float = Field(default=0, ge=0, le=100)
    # These fields are accepted from the client but always recomputed server-side
    net_price: float = Field(default=0, ge=0)
    total: float = Field(default=0, ge=0)


class SalesQuotationItemResponse(SalesQuotationItemCreate):
    """Response schema for a single quotation line item."""

    id: uuid.UUID
    quotation_id: uuid.UUID
    # Override: DB rows created before item_name became required may be NULL
    item_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ── Quotation create / update schemas ─────────────────────────────────────────

class SalesQuotationCreate(BaseModel):
    """Request body for creating a new SalesQuotation."""

    date: Optional[_Date] = None
    currency: str = "SAR"
    validity: Optional[str] = None
    delivery_time: Optional[str] = None
    delivery_location: Optional[str] = None
    payment_terms: Optional[str] = None
    customer_name: str = Field(min_length=1)
    department: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    cc: Optional[str] = None
    your_ref: Optional[str] = None
    subject: Optional[str] = None
    remarks: Optional[str] = None
    terms: Optional[str] = None
    items: List[SalesQuotationItemCreate] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        """Validate the optional customer email address format.

        Args:
            v: Raw email string or None.

        Returns:
            Stripped email string, or None if empty.

        Raises:
            ValueError: If the string is present but not a valid email address.
        """
        if v and not _EMAIL_RE.match(v.strip()):
            raise ValueError("Invalid email address")
        return v.strip() if v else v

    @field_validator("customer_name")
    @classmethod
    def validate_customer_name(cls, v: str) -> str:
        """Ensure customer_name is non-empty after stripping whitespace.

        Args:
            v: Raw customer name string.

        Returns:
            Stripped customer name.

        Raises:
            ValueError: If the name is blank or whitespace-only.
        """
        if not v or not v.strip():
            raise ValueError("Customer name is required")
        return v.strip()


class SalesQuotationUpdate(BaseModel):
    """Request body for updating an existing DRAFT SalesQuotation.

    Identical fields to ``SalesQuotationCreate``; kept as a separate class
    to allow independent evolution of create vs. update contracts.
    """

    date: Optional[_Date] = None
    currency: str = "SAR"
    validity: Optional[str] = None
    delivery_time: Optional[str] = None
    delivery_location: Optional[str] = None
    payment_terms: Optional[str] = None
    customer_name: str = Field(min_length=1)
    department: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    cc: Optional[str] = None
    your_ref: Optional[str] = None
    subject: Optional[str] = None
    remarks: Optional[str] = None
    terms: Optional[str] = None
    items: List[SalesQuotationItemCreate] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        """Validate optional customer email address format.

        Args:
            v: Raw email string or None.

        Returns:
            Stripped email string, or None if empty.

        Raises:
            ValueError: If the string is present but not a valid email address.
        """
        if v and not _EMAIL_RE.match(v.strip()):
            raise ValueError("Invalid email address")
        return v.strip() if v else v


# ── Response schemas ──────────────────────────────────────────────────────────

class SalesQuotationResponse(BaseModel):
    """Full response schema for a SalesQuotation including all line items."""

    id: uuid.UUID
    quote_number: str
    date: Optional[_Date]
    currency: str
    validity: Optional[str]
    delivery_time: Optional[str]
    delivery_location: Optional[str]
    payment_terms: Optional[str]
    customer_name: Optional[str]
    department: Optional[str]
    contact_person: Optional[str]
    phone: Optional[str]
    fax: Optional[str] = None
    email: Optional[str]
    cc: Optional[str] = None
    your_ref: Optional[str] = None
    subject: Optional[str]
    subtotal: float
    vat: float
    total: float
    remarks: Optional[str]
    terms: Optional[str]
    status: str
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    updated_by: Optional[uuid.UUID] = None
    items: List[SalesQuotationItemResponse] = []
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SalesQuotationStatusUpdate(BaseModel):
    """Request body for PATCH /quotations/{id}/status."""

    status: str


class SalesQuotationListResponse(BaseModel):
    """Paginated list response wrapping multiple SalesQuotation records."""

    items: List[SalesQuotationResponse]
    total: int
