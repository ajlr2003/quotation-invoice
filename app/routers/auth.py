"""
app/routers/auth.py

POST   /api/v1/auth/register        — create account, returns tokens
POST   /api/v1/auth/login           — email+password, returns tokens
POST   /api/v1/auth/refresh         — new access token from refresh token
GET    /api/v1/auth/me              — current user profile
PATCH  /api/v1/auth/me              — update profile
POST   /api/v1/auth/change-password — change password
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_current_user_id
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services import auth_service

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.register_user(db, payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.login_user(db, payload)


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Get new access token using refresh token",
)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await auth_service.refresh_access_token(db, payload)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(current_user=Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update current user profile",
)
async def update_me(
    payload: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await auth_service.update_profile(db, user_id, payload)


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
    summary="Change current user password",
)
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await auth_service.change_password(db, user_id, payload)
