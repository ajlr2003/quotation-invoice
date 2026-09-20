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
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"
    # SendGrid HTTP API — preferred when SENDGRID_API_KEY is set.
    # Requires only Single Sender Verification (no domain ownership needed).
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = ""
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

    # ── Seller block + bank accounts printed on customer (tax) invoices ───────
    # Mirrors the legal invoice layout, so each value is bilingual free text
    # exactly as it should print (English first, then Arabic). Override any of
    # them from .env; COMPANY_BANK_ACCOUNTS is a JSON list, one entry per
    # currency (the invoice prints the account matching its currency).
    SELLER_NAME: str = "Abdulkarim H. Al Sinan & Partner For Trading Company شركة عبدالكريم حسين السنان وشريكه للتجارة"
    SELLER_BUILDING: str = "Building Number 4084 رقم المبنى ; Unit 1 وحدة ; Additional Number 8189 الرقم الإضافي"
    SELLER_STREET: str = "Makkah Street شارع مكة"
    SELLER_DISTRICT: str = "Al Dana الدانة"
    SELLER_CITY: str = "Jubail الجبيل المنطقة الشرقية Eastern Province"
    SELLER_COUNTRY: str = "Saudi Arabia"
    SELLER_POSTAL_CODE: str = "35514"
    SELLER_VAT_NUMBER: str = "300506284400003"
    SELLER_CR_NO: str = "2055001448"
    COMPANY_BANK_ACCOUNTS: list = [
        {
            "currency": "USD",
            "account_name": "Abdulkarim H. Al Sinan & Partner For Trading Company شركة عبدالكريم حسين السنان وشريكه للتجارة",
            "account_no": "3232820640440",
            "swift": "RIBLSARIXXX",
            "bank": "Riyad Bank - USD",
            "branch": "Main Branch, Jubail, Kingdom of Saudi Arabia الفرع الرئيسي ، الجبيل ، المملكة العربية السعودية",
            "iban": "SA7520000003232820640440",
        },
    ]

    # ── AI Copilot (Anthropic Claude) ────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""                  # sk-ant-... — leave empty to disable AI Copilot
    ANTHROPIC_MODEL: str = "claude-opus-4-8"     # e.g. claude-sonnet-5 for lower cost

    # ── Payment gateways ─────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""          # sk_test_... or sk_live_...
    STRIPE_WEBHOOK_SECRET: str = ""      # whsec_... from `stripe listen` or dashboard
    STRIPE_PUBLISHABLE_KEY: str = ""     # pk_test_... exposed to frontend
    PAYPAL_CLIENT_ID: str = ""           # sandbox or live client ID
    PAYPAL_CLIENT_SECRET: str = ""       # sandbox or live client secret
    PAYPAL_MODE: str = "sandbox"         # "sandbox" or "live"
    # Base URL of THIS backend (used to build Stripe success/cancel redirect URLs)
    APP_BASE_URL: str = "http://localhost:8000"
    # Base URL of the frontend (used to build post-payment redirect pages)
    FRONTEND_BASE_URL: str = "http://localhost:5173"

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

    @field_validator("COMPANY_BANK_ACCOUNTS", mode="before")
    @classmethod
    def parse_bank_accounts(cls, v: str | list) -> list:
        """Accept the bank-account list as a JSON string (env var) or a list."""
        return json.loads(v) if isinstance(v, str) else v

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

    # extra="ignore": stale keys left in a deployed .env (e.g. the retired
    # ODOO_* settings) must not stop the app from booting.
    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


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
