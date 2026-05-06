# =============================================================================
# app/utils/security.py
# -----------------------------------------------------------------------------
# Password hashing (bcrypt via passlib) and JWT creation/validation helpers.
# All JWT operations use the application's SECRET_KEY and ALGORITHM from
# app/config.py.  Both access tokens and refresh tokens are signed JWTs
# differing only in their expiry duration.
# =============================================================================

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

logger = logging.getLogger(__name__)

# ── Password hashing context ──────────────────────────────────────────────────
# Uses bcrypt with automatic hash-upgrade on verify (deprecated="auto").
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt.

    Args:
        plain: The raw password string provided by the user.

    Returns:
        A bcrypt hash string suitable for storage in the database.
    """
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash.

    Args:
        plain:  The raw password string to check.
        hashed: The bcrypt hash retrieved from the database.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _build_token(subject: Any, expires_delta: timedelta) -> str:
    """Build and sign a JWT with the given subject and expiry.

    Args:
        subject:       Value to encode as the ``sub`` claim (typically a user ID).
        expires_delta: How long until the token expires.

    Returns:
        A signed JWT string.
    """
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: Any) -> str:
    """Create a short-lived access token for API authentication.

    Expiry is controlled by ``ACCESS_TOKEN_EXPIRE_MINUTES`` in settings.

    Args:
        subject: The value to encode as ``sub`` (usually a user UUID string).

    Returns:
        A signed JWT access token string.
    """
    return _build_token(
        subject,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(subject: Any) -> str:
    """Create a long-lived refresh token used to obtain new access tokens.

    Expiry is controlled by ``REFRESH_TOKEN_EXPIRE_DAYS`` in settings.

    Args:
        subject: The value to encode as ``sub`` (usually a user UUID string).

    Returns:
        A signed JWT refresh token string.
    """
    return _build_token(
        subject,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> Optional[str]:
    """Decode and validate a JWT, returning the subject claim.

    Args:
        token: The raw JWT string to decode.

    Returns:
        The ``sub`` claim value (user ID string) if the token is valid and
        not expired, or ``None`` if validation fails for any reason.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        logger.debug("Token decoded OK — sub=%s exp=%s", payload.get("sub"), payload.get("exp"))
        return payload.get("sub")
    except JWTError as e:
        logger.warning("Token rejected — %s: %s", type(e).__name__, e)
        return None
