# =============================================================================
# app/routers/users.py
# -----------------------------------------------------------------------------
# Admin-only user-administration endpoints: list accounts, change a user's
# role, and activate/deactivate accounts. Self-registration (POST /register)
# lives in auth.py and always creates a VIEWER account — promotion to any
# other role happens here, and only an ADMIN may do it.
#
# GET   /api/v1/users              — list all user accounts        (ADMIN)
# PATCH /api/v1/users/{id}/role    — change a user's role           (ADMIN)
# PATCH /api/v1/users/{id}/status  — activate / deactivate a user   (ADMIN)
# =============================================================================

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    UserListResponse,
    UserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)

router = APIRouter()

_admin_only = require_roles(UserRole.ADMIN)


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.get(
    "",
    response_model=UserListResponse,
    summary="List all user accounts (admin only)",
)
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(_admin_only),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=len(users),
    )


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Change a user's role (admin only)",
)
async def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    if user_id == admin.id and payload.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role away from admin.",
        )
    user = await _get_user_or_404(db, user_id)
    user.role = payload.role
    await db.flush()
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    summary="Activate or deactivate a user account (admin only)",
)
async def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    if user_id == admin.id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )
    user = await _get_user_or_404(db, user_id)
    user.is_active = payload.is_active
    await db.flush()
    return UserResponse.model_validate(user)
