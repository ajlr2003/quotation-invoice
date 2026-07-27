from __future__ import annotations

import uuid
from datetime import date as _Date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


EXPENSE_CATEGORIES = ["Hotel", "Food", "Fuel", "Car Rental", "Travel", "Meals", "Supplies", "Software", "Other"]
EXPENSE_STATUSES   = ["submitted", "approved", "rejected", "reimbursed"]


class ExpenseCreate(BaseModel):
    title: str = Field(min_length=1)
    category: str
    amount: float = Field(gt=0)
    currency: str = "SAR"
    expense_date: Optional[_Date] = None
    submitted_by_name: Optional[str] = None
    project_name: Optional[str] = None
    notes: Optional[str] = None


class ExpenseStatusUpdate(BaseModel):
    status: str
    rejection_reason: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    amount: float
    currency: str
    expense_date: Optional[_Date]
    submitted_by_id: Optional[uuid.UUID]
    submitted_by_name: Optional[str]
    project_name: Optional[str]
    notes: Optional[str]
    status: str
    rejection_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ExpenseListResponse(BaseModel):
    items: List[ExpenseResponse]
    total: int


class ExpenseKPIs(BaseModel):
    total_submitted: int
    pending_count: int
    pending_amount: float
    approved_amount: float
    reimbursed_amount: float
    rejected_count: int
    category_breakdown: List[dict]   # [{category, total}]
