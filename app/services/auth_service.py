"""
app/services/auth_service.py
All authentication business logic — registration, login, token refresh,
profile updates, password changes.
"""
import logging
import uuid
from datetime import timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.enums import UserRole
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    UserUpdateRequest,
    ChangePasswordRequest,
    TokenResponse,
    AccessTokenResponse,
    UserResponse,
)
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.config import settings
from fastapi import HTTPException, status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def _get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


def _make_token_response(user_id: uuid.UUID) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user_id)),
        refresh_token=create_refresh_token(str(user_id)),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

async def register_user(db: AsyncSession, payload: RegisterRequest) -> TokenResponse:
    # Duplicate email check
    existing = await _get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        phone=payload.phone,
        department=payload.department,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.flush()   # get the UUID without committing yet

    return _make_token_response(user.id)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

async def login_user(db: AsyncSession, payload: LoginRequest) -> TokenResponse:
    logger.debug("Login attempt for email=%s", payload.email)
    try:
        user = await _get_user_by_email(db, payload.email)
    except Exception:
        logger.exception("DB error during user lookup for email=%s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable. Check database connection.",
        )

    # Use same error for wrong email AND wrong password (prevents user enumeration)
    if not user:
        logger.debug("Login failed — no user found for email=%s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, user.hashed_password):
        logger.debug("Login failed — incorrect password for email=%s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    logger.debug("Login successful for user_id=%s", user.id)
    return _make_token_response(user.id)


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------

async def refresh_access_token(
    db: AsyncSession, payload: RefreshRequest
) -> AccessTokenResponse:
    user_id_str = decode_token(payload.refresh_token)
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token.")

    user = await _get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    return AccessTokenResponse(
        access_token=create_access_token(str(user.id)),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# Get current user profile
# ---------------------------------------------------------------------------

async def get_current_user(db: AsyncSession, user_id: uuid.UUID) -> UserResponse:
    user = await _get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# Update profile
# ---------------------------------------------------------------------------

async def update_profile(
    db: AsyncSession, user_id: uuid.UUID, payload: UserUpdateRequest
) -> UserResponse:
    user = await _get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    update_data = payload.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.flush()
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

async def change_password(
    db: AsyncSession, user_id: uuid.UUID, payload: ChangePasswordRequest
) -> dict:
    user = await _get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current password.",
        )

    user.hashed_password = hash_password(payload.new_password)
    await db.flush()
    return {"message": "Password updated successfully."}
