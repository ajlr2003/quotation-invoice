from __future__ import annotations

import uuid
from typing import List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.project_task import ProjectTask
from app.models.project_milestone import ProjectMilestone
from app.models.time_log import TimeLog
from app.schemas.project import (
    MilestoneCreate,
    ProjectCreate,
    ProjectKPIs,
    ProjectResponse,
    ProjectUpdate,
    TaskCreate,
    TimeLogCreate,
)


# ── helpers ───────────────────────────────────────────────────────────────────

async def _load(db: AsyncSession, project_id: uuid.UUID) -> Project:
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.tasks),
            selectinload(Project.milestones),
            selectinload(Project.time_logs),
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise ValueError(f"Project {project_id} not found")
    return p


def _to_response(p: Project) -> ProjectResponse:
    total_hours = sum(float(tl.hours) for tl in p.time_logs)
    return ProjectResponse(
        id=p.id,
        name=p.name,
        client=p.client,
        description=p.description,
        status=p.status,
        budget=float(p.budget),
        budget_spent=float(p.budget_spent),
        billable=p.billable,
        start_date=p.start_date,
        end_date=p.end_date,
        progress=p.progress,
        total_hours=total_hours,
        tasks=[t for t in p.tasks],
        milestones=[m for m in p.milestones],
        time_logs=sorted(p.time_logs, key=lambda tl: tl.date, reverse=True),
        created_at=p.created_at,
    )


# ── Projects ──────────────────────────────────────────────────────────────────

async def list_projects(db: AsyncSession) -> dict:
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.tasks),
            selectinload(Project.milestones),
            selectinload(Project.time_logs),
        )
        .order_by(Project.created_at.desc())
    )
    projects = list(result.scalars().all())
    return {"items": [_to_response(p) for p in projects], "total": len(projects)}


async def create_project(db: AsyncSession, payload: ProjectCreate) -> ProjectResponse:
    p = Project(
        name=payload.name,
        client=payload.client,
        description=payload.description,
        status=payload.status,
        budget=payload.budget,
        budget_spent=0,
        billable=payload.billable,
        start_date=payload.start_date,
        end_date=payload.end_date,
        progress=payload.progress,
    )
    db.add(p)
    await db.flush()
    await db.refresh(p)
    # reload with relationships
    p = await _load(db, p.id)
    await db.commit()
    return _to_response(p)


async def update_project(
    db: AsyncSession, project_id: uuid.UUID, payload: ProjectUpdate
) -> ProjectResponse:
    p = await _load(db, project_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(p, field, value)
    await db.commit()
    p = await _load(db, project_id)
    return _to_response(p)


async def delete_project(db: AsyncSession, project_id: uuid.UUID) -> None:
    p = await _load(db, project_id)
    await db.delete(p)
    await db.commit()


# ── Tasks ─────────────────────────────────────────────────────────────────────

async def create_task(
    db: AsyncSession, project_id: uuid.UUID, payload: TaskCreate
) -> ProjectResponse:
    await _load(db, project_id)  # validate project exists
    task = ProjectTask(
        project_id=project_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        priority=payload.priority,
        assignee=payload.assignee,
        due_date=payload.due_date,
    )
    db.add(task)
    await db.commit()
    return _to_response(await _load(db, project_id))


async def update_task_status(
    db: AsyncSession, task_id: uuid.UUID, status: str
) -> ProjectTask:
    result = await db.execute(select(ProjectTask).where(ProjectTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise ValueError(f"Task {task_id} not found")
    task.status = status

    # Auto-update project progress based on task completion ratio
    all_tasks_result = await db.execute(
        select(ProjectTask).where(ProjectTask.project_id == task.project_id)
    )
    all_tasks = list(all_tasks_result.scalars().all())
    if all_tasks:
        done = sum(1 for t in all_tasks if t.status == "done")
        pct = int((done / len(all_tasks)) * 100)
        proj_result = await db.execute(
            select(Project).where(Project.id == task.project_id)
        )
        proj = proj_result.scalar_one_or_none()
        if proj:
            proj.progress = pct

    await db.commit()
    return task


async def delete_task(db: AsyncSession, task_id: uuid.UUID) -> None:
    result = await db.execute(select(ProjectTask).where(ProjectTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise ValueError(f"Task {task_id} not found")
    await db.delete(task)
    await db.commit()


# ── Milestones ────────────────────────────────────────────────────────────────

async def create_milestone(
    db: AsyncSession, project_id: uuid.UUID, payload: MilestoneCreate
) -> ProjectResponse:
    await _load(db, project_id)
    ms = ProjectMilestone(
        project_id=project_id,
        title=payload.title,
        due_date=payload.due_date,
        completed=False,
    )
    db.add(ms)
    await db.commit()
    return _to_response(await _load(db, project_id))


async def toggle_milestone(
    db: AsyncSession, milestone_id: uuid.UUID
) -> ProjectMilestone:
    result = await db.execute(
        select(ProjectMilestone).where(ProjectMilestone.id == milestone_id)
    )
    ms = result.scalar_one_or_none()
    if not ms:
        raise ValueError(f"Milestone {milestone_id} not found")
    ms.completed = not ms.completed
    await db.commit()
    return ms


# ── Time logs ─────────────────────────────────────────────────────────────────

async def log_time(
    db: AsyncSession, project_id: uuid.UUID, payload: TimeLogCreate
) -> ProjectResponse:
    await _load(db, project_id)
    tl = TimeLog(
        project_id=project_id,
        date=payload.date,
        hours=payload.hours,
        description=payload.description,
        logged_by=payload.logged_by,
    )
    db.add(tl)

    # Update budget_spent by adding hours × some rate (or just track hours)
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    proj = proj_result.scalar_one_or_none()
    if proj:
        all_logs = await db.execute(
            select(func.sum(TimeLog.hours)).where(TimeLog.project_id == project_id)
        )
        current = float(all_logs.scalar() or 0)
        # No hourly rate configured — just commit the log
    await db.commit()
    return _to_response(await _load(db, project_id))


# ── KPIs ──────────────────────────────────────────────────────────────────────

async def get_kpis(db: AsyncSession) -> ProjectKPIs:
    total = (await db.execute(select(func.count()).select_from(Project))).scalar_one()
    active = (
        await db.execute(
            select(func.count()).select_from(Project).where(Project.status == "active")
        )
    ).scalar_one()

    hours_row = await db.execute(select(func.sum(TimeLog.hours)))
    total_hours = float(hours_row.scalar() or 0)

    budget_row = await db.execute(select(func.sum(Project.budget), func.sum(Project.budget_spent)))
    b_total, b_spent = budget_row.one()
    b_total = float(b_total or 0)
    b_spent = float(b_spent or 0)
    util_pct = round((b_spent / b_total * 100), 1) if b_total else 0

    # Count distinct assignees as a proxy for team size
    assignees_row = await db.execute(
        select(func.count(func.distinct(ProjectTask.assignee))).where(
            ProjectTask.assignee.isnot(None)
        )
    )
    team = assignees_row.scalar_one() or 0

    return ProjectKPIs(
        total_projects=total,
        active_projects=active,
        total_hours=total_hours,
        budget_utilization_pct=util_pct,
        total_team_members=team,
    )
