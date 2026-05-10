# =============================================================================
# app/config.py
# -----------------------------------------------------------------------------
# Pydantic-settings configuration for the entire application. All tuneable
# parameters (database URL, JWT secrets, SMTP, company identity, pagination)
# are declared here and loaded from environment variables / a .env file.
# A cached `get_settings()` factory is provided for use as a FastAPI
# dependency or direct import via the module-level `settings` singleton.
# =============================================================================

from __future__ import annotations

import json
from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-wide configuration loaded from environment variables or .env.

    All fields use UPPER_SNAKE_CASE to match the environment variable names.
    Sensitive fields (SECRET_KEY, SMTP_PASS) must be provided at runtime and
    are never given insecure defaults.
    """

    # ── Application identity ─────────────────────────────────────────────────
    APP_NAME: str = "Quotation-Invoice API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str                        # asyncpg DSN — must be set in .env
    DATABASE_POOL_SIZE: int = 10             # SQLAlchemy connection pool size
    DATABASE_MAX_OVERFLOW: int = 20          # extra connections beyond pool_size

    # ── JWT authentication ───────────────────────────────────────────────────
    SECRET_KEY: str                          # HMAC secret — must be set in .env
    ALGORITHM: str = "HS256"                 # JWT signing algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480   # 8 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7       # 1 week

    # ── CORS ─────────────────────────────────────────────────────────────────
    # JSON array string accepted when set via environment variable
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Email delivery ────────────────────────────────────────────────────────
    # Resend (HTTP API) is preferred — works on Render free tier.
    # SMTP is used as fallback when RESEND_API_KEY is not set.
    RESEND_API_KEY: str = ""
    # "From" address used when sending via Resend. Must be a domain verified on
    # resend.com/domains. Defaults to Resend's shared onboarding sender which
    # works on all accounts without domain setup (testing / free tier).
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587                     # 587 = STARTTLS, 465 = SSL/TLS
    SMTP_USER: str = ""
    SMTP_PASS: str = ""

    # ── Company identity (used in PDF letterhead) ─────────────────────────────
    COMPANY_NAME: str = "Kytos Arabia"
    COMPANY_ADDRESS: str = "P.O. BOX 374, AL JUBAIL (Support Industries III) - 31961"
    COMPANY_WEBSITE: str = "www.sinanakh.com"
    COMPANY_PHONE: str = ""
    COMPANY_FAX: str = ""
    COMPANY_CONTACT_NAME: str = ""
    COMPANY_DIRECT_LINE: str = ""
    # Absolute path to logo JPG/PNG; if empty, a text-only fallback is rendered
    COMPANY_LOGO_PATH: str = ""

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── Pagination defaults ───────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    @field_validator("SMTP_PORT", mode="before")
    @classmethod
    def parse_smtp_port(cls, v: str | int) -> int:
        """Coerce SMTP_PORT to int, falling back to 587 when empty or missing."""
        if isinstance(v, int):
            return v
        if not str(v).strip():
            return 587
        return int(v)

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list) -> list:
        """Parse ALLOWED_ORIGINS from a JSON string when provided via env var.

        Args:
            v: Either a JSON-encoded string (e.g. '["http://localhost:3000"]')
               or an already-parsed list.

        Returns:
            A list of allowed origin strings.
        """
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = {"env_file": ".env", "case_sensitive": True}


@lru_cache()
def get_settings() -> Settings:
    """Return the cached Settings singleton.

    Uses ``functools.lru_cache`` so the .env file is only read once per
    process.  Can also be used as a FastAPI dependency via ``Depends``.

    Returns:
        The application Settings instance.
    """
    return Settings()


# Module-level singleton — used throughout the application via `from app.config import settings`
settings = get_settings()
