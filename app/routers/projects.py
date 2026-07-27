from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.project import (
    MilestoneCreate,
    MilestoneResponse,
    ProjectCreate,
    ProjectKPIs,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
    TaskCreate,
    TaskResponse,
    TaskStatusUpdate,
    TimeLogCreate,
    TimeLogResponse,
)
from app.services import project_service

router = APIRouter()

_project_admin_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER)


def _404(msg: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis", response_model=ProjectKPIs)
async def kpis(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await project_service.get_kpis(db)


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("", response_model=ProjectListResponse)
async def list_projects(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await project_service.list_projects(db)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_project_admin_roles),
):
    return await project_service.create_project(db, payload)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(_project_admin_roles),
):
    try:
        return await project_service.update_project(db, project_id, payload)
    except ValueError as e:
        _404(str(e))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(_project_admin_roles),
):
    try:
        await project_service.delete_project(db, project_id)
    except ValueError as e:
        _404(str(e))


# ── Tasks ─────────────────────────────────────────────────────────────────────

@router.post("/{project_id}/tasks", response_model=ProjectResponse, status_code=201)
async def add_task(
    project_id: uuid.UUID,
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return await project_service.create_task(db, project_id, payload)
    except ValueError as e:
        _404(str(e))


@router.patch("/tasks/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: uuid.UUID,
    payload: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return await project_service.update_task_status(db, task_id, payload.status)
    except ValueError as e:
        _404(str(e))


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        await project_service.delete_task(db, task_id)
    except ValueError as e:
        _404(str(e))


# ── Milestones ────────────────────────────────────────────────────────────────

@router.post("/{project_id}/milestones", response_model=ProjectResponse, status_code=201)
async def add_milestone(
    project_id: uuid.UUID,
    payload: MilestoneCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return await project_service.create_milestone(db, project_id, payload)
    except ValueError as e:
        _404(str(e))


@router.post("/milestones/{milestone_id}/toggle", response_model=MilestoneResponse)
async def toggle_milestone(
    milestone_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return await project_service.toggle_milestone(db, milestone_id)
    except ValueError as e:
        _404(str(e))


# ── Time logs ─────────────────────────────────────────────────────────────────

@router.post("/{project_id}/time-logs", response_model=ProjectResponse, status_code=201)
async def log_time(
    project_id: uuid.UUID,
    payload: TimeLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.logged_by:
        payload.logged_by = current_user.full_name or current_user.email
    try:
        return await project_service.log_time(db, project_id, payload)
    except ValueError as e:
        _404(str(e))
