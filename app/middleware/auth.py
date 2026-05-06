# =============================================================================
# app/middleware/auth.py
# -----------------------------------------------------------------------------
# FastAPI dependency functions for JWT-based authentication and role-based
# access control (RBAC). These are injected into route handlers via
# ``Depends()`` rather than running as traditional ASGI middleware.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.security import decode_token

# ── OAuth2 scheme ─────────────────────────────────────────────────────────────
# Points to the login endpoint so Swagger UI can auto-fill the token field.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> uuid.UUID:
    """Validate a Bearer JWT and return the encoded user UUID.

    This is a lightweight dependency that does **not** hit the database —
    use it when only the user's ID is needed (e.g. audit stamps).

    Args:
        token: Raw JWT string extracted from the ``Authorization`` header.

    Returns:
        The UUID of the authenticated user.

    Raises:
        HTTPException: 401 if the token is missing, expired, or has an
            invalid signature.  401 if the ``sub`` claim is not a valid UUID.
    """
    user_id_str = decode_token(token)
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Validate a Bearer JWT and return the full User ORM object.

    Performs a database lookup to confirm the user still exists and is active.
    Use this dependency whenever route logic needs user attributes beyond the ID.

    Args:
        token: Raw JWT string extracted from the ``Authorization`` header.
        db:    Async database session (injected by FastAPI).

    Returns:
        The authenticated ``User`` ORM instance.

    Raises:
        HTTPException: 401 if the token is invalid or the user no longer exists.
        HTTPException: 403 if the user account has been deactivated.
    """
    from sqlalchemy import select
    from app.models.user import User

    user_id = await get_current_user_id(token)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )
    return user


def require_roles(*roles):
    """Return a FastAPI dependency that enforces role-based access control.

    Factory function — call it with the set of permitted ``UserRole`` values
    and use the result as a ``Depends()`` argument in a route.

    Example::

        _admin_only = require_roles(UserRole.ADMIN)

        @router.delete("/{id}", dependencies=[Depends(_admin_only)])
        async def delete_item(...): ...

    Args:
        *roles: One or more ``UserRole`` enum values that are allowed access.

    Returns:
        An async dependency function that resolves to the authenticated user or
        raises HTTP 403 if the user's role is not in ``roles``.

    Raises:
        HTTPException: 403 if the current user's role is not permitted.
    """
    async def _check_role(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in roles]}",
            )
        return current_user
    return _check_role
