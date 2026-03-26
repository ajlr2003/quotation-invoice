"""
app/schemas/supplier.py
Pydantic request/response schemas for Supplier CRUD.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Shared base (fields common to create & update)
# ---------------------------------------------------------------------------

class SupplierBase(BaseModel):
    company_name: str              = Field(min_length=2, max_length=255)
    contact_name: Optional[str]    = Field(default=None, max_length=255)
    email: EmailStr
    phone: Optional[str]           = Field(default=None, max_length=50)

    # Address
    address_line1: Optional[str]   = Field(default=None, max_length=255)
    address_line2: Optional[str]   = Field(default=None, max_length=255)
    city: Optional[str]            = Field(default=None, max_length=100)
    state: Optional[str]           = Field(default=None, max_length=100)
    postal_code: Optional[str]     = Field(default=None, max_length=20)
    country: Optional[str]         = Field(default=None, max_length=100)

    # Finance
    tax_id: Optional[str]          = Field(default=None, max_length=100)
    payment_terms_days: int        = Field(default=30, ge=0, le=365)
    currency: str                  = Field(default="USD", min_length=3, max_length=3)
    bank_details: Optional[str]    = None

    # Evaluation
    rating: Optional[float]        = Field(default=None, ge=0.0, le=5.0)
    is_preferred: bool             = False
    notes: Optional[str]           = None

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()


# ---------------------------------------------------------------------------
# Create request
# ---------------------------------------------------------------------------

class SupplierCreateRequest(SupplierBase):
    """All fields for creating a new supplier."""
    pass


# ---------------------------------------------------------------------------
# Update request — every field optional (PATCH semantics)
# ---------------------------------------------------------------------------

class SupplierUpdateRequest(BaseModel):
    company_name: Optional[str]    = Field(default=None, min_length=2, max_length=255)
    contact_name: Optional[str]    = Field(default=None, max_length=255)
    email: Optional[EmailStr]      = None
    phone: Optional[str]           = Field(default=None, max_length=50)

    address_line1: Optional[str]   = Field(default=None, max_length=255)
    address_line2: Optional[str]   = Field(default=None, max_length=255)
    city: Optional[str]            = Field(default=None, max_length=100)
    state: Optional[str]           = Field(default=None, max_length=100)
    postal_code: Optional[str]     = Field(default=None, max_length=20)
    country: Optional[str]         = Field(default=None, max_length=100)

    tax_id: Optional[str]          = Field(default=None, max_length=100)
    payment_terms_days: Optional[int] = Field(default=None, ge=0, le=365)
    currency: Optional[str]        = Field(default=None, min_length=3, max_length=3)
    bank_details: Optional[str]    = None

    rating: Optional[float]        = Field(default=None, ge=0.0, le=5.0)
    is_preferred: Optional[bool]   = None
    is_active: Optional[bool]      = None
    notes: Optional[str]           = None

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class SupplierResponse(BaseModel):
    id: uuid.UUID
    company_name: str
    contact_name: Optional[str]
    email: str
    phone: Optional[str]

    address_line1: Optional[str]
    address_line2: Optional[str]
    city: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]
    country: Optional[str]

    tax_id: Optional[str]
    payment_terms_days: int
    currency: str
    bank_details: Optional[str]

    rating: Optional[float]
    is_preferred: bool
    is_active: bool
    notes: Optional[str]

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Paginated list response
# ---------------------------------------------------------------------------

class SupplierListResponse(BaseModel):
    items: list[SupplierResponse]
    total: int
    page: int
    page_size: int
    pages: int
