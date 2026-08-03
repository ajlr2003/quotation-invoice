from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Task ──────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    description: Optional[str] = None
    status: str = "todo"          # todo | in_progress | done
    priority: str = "medium"      # low | medium | high
    assignee: Optional[str] = None
    due_date: Optional[date] = None


class TaskStatusUpdate(BaseModel):
    status: str


class TaskResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: Optional[str]
    status: str
    priority: str
    assignee: Optional[str]
    due_date: Optional[date]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Milestone ─────────────────────────────────────────────────────────────────

class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1)
    due_date: Optional[date] = None


class MilestoneResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    due_date: Optional[date]
    completed: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Time log ──────────────────────────────────────────────────────────────────

class TimeLogCreate(BaseModel):
    date: date
    hours: float = Field(gt=0)
    description: Optional[str] = None
    logged_by: Optional[str] = None


class TimeLogResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    date: date
    hours: float
    description: Optional[str]
    logged_by: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Project ───────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    client: Optional[str] = None
    description: Optional[str] = None
    status: str = "planning"
    budget: float = Field(default=0, ge=0)
    billable: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    progress: int = Field(default=0, ge=0, le=100)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    client: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = None
    budget_spent: Optional[float] = None
    billable: Optional[bool] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    client: Optional[str]
    description: Optional[str]
    status: str
    budget: float
    budget_spent: float
    billable: bool = True
    start_date: Optional[date]
    end_date: Optional[date]
    progress: int
    total_hours: float = 0
    tasks: List[TaskResponse] = []
    milestones: List[MilestoneResponse] = []
    time_logs: List[TimeLogResponse] = []
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    items: List[ProjectResponse]
    total: int


class ProjectKPIs(BaseModel):
    total_projects: int
    active_projects: int
    total_hours: float
    budget_utilization_pct: float
    total_team_members: int
