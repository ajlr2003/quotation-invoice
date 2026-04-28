import uuid
from datetime import date as _Date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SalesQuotationItemCreate(BaseModel):
    line_no: int = 1
    catalog_no: Optional[str] = None
    item_name: Optional[str] = None
    description: Optional[str] = None
    qty: float = Field(default=0, ge=0)
    unit: str = "EA"
    unit_price: float = Field(default=0, ge=0)
    discount: float = Field(default=0, ge=0, le=100)
    net_price: float = Field(default=0, ge=0)
    total: float = Field(default=0, ge=0)


class SalesQuotationItemResponse(SalesQuotationItemCreate):
    id: uuid.UUID
    quotation_id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)


class SalesQuotationCreate(BaseModel):
    date: Optional[_Date] = None
    currency: str = "SAR"
    validity: Optional[str] = None
    delivery_time: Optional[str] = None
    delivery_location: Optional[str] = None
    payment_terms: Optional[str] = None
    customer_name: Optional[str] = None
    department: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    subject: Optional[str] = None
    remarks: Optional[str] = None
    terms: Optional[str] = None
    status: str = "draft"
    items: List[SalesQuotationItemCreate] = []


class SalesQuotationUpdate(SalesQuotationCreate):
    pass


class SalesQuotationResponse(BaseModel):
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
    email: Optional[str]
    subject: Optional[str]
    subtotal: float
    vat: float
    total: float
    remarks: Optional[str]
    terms: Optional[str]
    status: str
    sent_at: Optional[datetime] = None
    items: List[SalesQuotationItemResponse] = []
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SalesQuotationStatusUpdate(BaseModel):
    status: str


class SalesQuotationListResponse(BaseModel):
    items: List[SalesQuotationResponse]
    total: int
