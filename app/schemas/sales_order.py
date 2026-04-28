import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class SalesOrderItemResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    line_no: int
    catalog_no: Optional[str] = None
    item_name: Optional[str] = None
    description: Optional[str] = None
    qty: float
    unit: str
    unit_price: float
    discount: float
    net_price: float
    total: float
    model_config = ConfigDict(from_attributes=True)


class SalesOrderCreate(BaseModel):
    quotation_id: uuid.UUID


class SalesOrderResponse(BaseModel):
    id: uuid.UUID
    order_number: str
    quotation_id: Optional[uuid.UUID] = None
    customer_name: Optional[str] = None
    department: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    subject: Optional[str] = None
    currency: str
    payment_terms: Optional[str] = None
    delivery_location: Optional[str] = None
    subtotal: float
    vat: float
    total: float
    remarks: Optional[str] = None
    status: str
    items: List[SalesOrderItemResponse] = []
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SalesOrderListResponse(BaseModel):
    items: List[SalesOrderResponse]
    total: int
