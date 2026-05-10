# =============================================================================
# app/main.py
# -----------------------------------------------------------------------------
# FastAPI application factory for the Quotation-Invoice API. Configures
# middleware (CORS, trailing-slash normalisation), registers all routers under
# the /api/v1 prefix, and wires up the ASGI lifespan (DB init + optional
# dev-mode seed data on startup, connection-pool disposal on shutdown).
# =============================================================================

from __future__ import annotations

import logging
import os

# ── Logging must be configured before any other local imports ─────────────────
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db, close_db, AsyncSessionLocal

# ── Register all ORM models in Base.metadata before init_db() ────────────────
# The noqa comment suppresses the "imported but unused" warning; the import is
# intentional — it populates Base.metadata as a side-effect.
import app.models  # noqa: F401

# ── Import all routers ────────────────────────────────────────────────────────
from app.routers import (
    auth, users, clients, quotations, invoices, suppliers, rfqs,
    purchase_orders, grn, purchase_invoices, sales_quotations, sales_orders,
    dashboard,
)

logger = logging.getLogger(__name__)

# ── API prefix constant ───────────────────────────────────────────────────────
# All versioned routes are mounted under this prefix.
API_PREFIX = "/api/v1"


# =============================================================================
# ASGI middleware
# =============================================================================

class _StripTrailingSlash:
    """ASGI middleware that removes trailing slashes from request paths.

    Normalises paths before routing so that ``/login`` and ``/login/`` resolve
    to the same route without issuing a 307 redirect.  The root path ``/`` is
    never modified.
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        """Strip trailing slash from ``scope["path"]`` for HTTP requests.

        Args:
            scope:   ASGI connection scope dictionary.
            receive: ASGI receive callable.
            send:    ASGI send callable.
        """
        if scope["type"] == "http":
            path: str = scope.get("path", "")
            if path != "/" and path.endswith("/"):
                scope["path"] = path.rstrip("/")
        await self.app(scope, receive, send)


# =============================================================================
# Lifespan — startup / shutdown
# =============================================================================

async def _seed_test_user() -> None:
    """Create a default test account when DEBUG=True and no users exist yet.

    Seeds ``test@example.com / test123`` with MANAGER role so developers can
    immediately authenticate against a fresh database.  No-ops in production
    (``DEBUG=False``).
    """
    if not settings.DEBUG:
        return
    from sqlalchemy import select
    from app.models.user import User
    from app.utils.security import hash_password

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(User).where(User.email == "test@example.com"))
        if existing.scalar_one_or_none():
            return
        from app.models.enums import UserRole
        user = User(
            email="test@example.com",
            full_name="Test User",
            hashed_password=hash_password("test123"),
            role=UserRole.MANAGER,
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        logger.info("Seeded test user: test@example.com / test123")


async def _seed_suppliers() -> None:
    """Populate a set of sample suppliers when DEBUG=True.

    Only inserts suppliers whose email addresses are not already present,
    making the operation safe to run on every restart.  No-ops in production.
    """
    if not settings.DEBUG:
        return
    from sqlalchemy import select, func
    from app.models.supplier import Supplier

    # Sample supplier data used only in development / local testing
    _SUPPLIERS = [
        dict(company_name="TechSupply Co.",        email="john@techsupply.com",
             contact_name="John Doe",              phone="123456789",
             country="Saudi Arabia", currency="USD", payment_terms_days=30, is_preferred=True),
        dict(company_name="Gulf Office Supplies",  email="sales@gulfoffice.sa",
             contact_name="Ahmad Al-Rashid",       phone="+966-11-4001234",
             country="Saudi Arabia", currency="SAR", payment_terms_days=14),
        dict(company_name="AlMansoori Trading",    email="info@almansoori.ae",
             contact_name="Fatima Al-Mansoori",    phone="+971-4-3456789",
             country="UAE",          currency="AED", payment_terms_days=30),
        dict(company_name="GreenTech Industries",  email="procurement@greentech.com",
             contact_name="Sara Ahmed",            phone="+966-12-6001111",
             country="Saudi Arabia", currency="USD", payment_terms_days=45, is_preferred=True),
        dict(company_name="FastLog Logistics",     email="ops@fastlog.com",
             contact_name="Khalid Nasser",         phone="+971-50-9988776",
             country="UAE",          currency="USD", payment_terms_days=7),
        dict(company_name="Arabian Print House",   email="quotes@arabprint.sa",
             contact_name="Nora Saleh",            phone="+966-13-8877001",
             country="Saudi Arabia", currency="SAR", payment_terms_days=15),
        dict(company_name="Delta Electronics",     email="supply@deltaelec.com",
             contact_name="James Miller",          phone="+1-800-3339900",
             country="USA",          currency="USD", payment_terms_days=30),
        dict(company_name="Horizon Packaging",     email="orders@horizonpack.com",
             contact_name="Liu Wei",               phone="+86-21-5558800",
             country="China",        currency="USD", payment_terms_days=60),
    ]

    async with AsyncSessionLocal() as session:
        count = (await session.execute(select(func.count()).select_from(Supplier))).scalar_one()
        if count >= len(_SUPPLIERS):
            return
        existing_emails = {
            r[0] for r in (await session.execute(select(Supplier.email))).all()
        }
        for data in _SUPPLIERS:
            if data["email"] not in existing_emails:
                session.add(Supplier(is_active=True, **data))
        await session.commit()
        logger.info("Seeded suppliers")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """ASGI lifespan context manager — runs startup then yields, then shutdown.

    Startup:
        1. Create all ORM tables (dev convenience; use Alembic in production).
        2. Seed test user and sample suppliers in DEBUG mode.

    Shutdown:
        Dispose the SQLAlchemy connection pool cleanly.
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    print(f"🚀  Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    await _seed_test_user()
    await _seed_suppliers()
    yield
    # ── Shutdown ──────────────────────────────────────────────────────────────
    print("🛑  Shutting down — closing DB pool")
    await close_db()


# =============================================================================
# Application factory
# =============================================================================

def create_application() -> FastAPI:
    """Construct and configure the FastAPI application instance.

    Docs endpoints (``/docs``, ``/redoc``, ``/openapi.json``) are exposed only
    when ``DEBUG=True`` or ``ENVIRONMENT != production``.

    Returns:
        A fully configured ``FastAPI`` application ready to be served by
        Uvicorn or any other ASGI server.
    """
    _expose_docs = settings.DEBUG or settings.ENVIRONMENT != "production"
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        redirect_slashes=True,
        description=(
            "REST API for Quotation-to-Invoice Workflow Automation. "
            "Handles quotation creation, approval, and conversion to invoices."
        ),
        docs_url="/docs"            if _expose_docs else None,
        redoc_url="/redoc"          if _expose_docs else None,
        openapi_url="/openapi.json" if _expose_docs else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Trailing-slash normalisation ──────────────────────────────────────────
    app.add_middleware(_StripTrailingSlash)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(auth.router,               prefix=f"{API_PREFIX}/auth",             tags=["Authentication"])
    app.include_router(users.router,              prefix=f"{API_PREFIX}/users",            tags=["Users"])
    app.include_router(clients.router,            prefix=f"{API_PREFIX}/clients",          tags=["Clients"])
    app.include_router(suppliers.router,          prefix=f"{API_PREFIX}/suppliers",        tags=["Suppliers"])
    app.include_router(rfqs.router,               prefix=f"{API_PREFIX}/rfqs",             tags=["RFQs"])
    app.include_router(quotations.router,         prefix=f"{API_PREFIX}/quotations",       tags=["Quotations"])
    app.include_router(purchase_orders.router,    prefix=f"{API_PREFIX}/purchase-orders",  tags=["Purchase Orders"])
    app.include_router(grn.router,                prefix=f"{API_PREFIX}/grn",              tags=["GRN"])
    app.include_router(invoices.router,           prefix=f"{API_PREFIX}/invoices",         tags=["Invoices"])
    app.include_router(purchase_invoices.router,  prefix=f"{API_PREFIX}/purchase-invoices", tags=["Purchase Invoices"])
    app.include_router(sales_quotations.router,   prefix=f"{API_PREFIX}/sales/quotations",  tags=["Sales Quotations"])
    app.include_router(sales_orders.router,       prefix=f"{API_PREFIX}/sales/orders",      tags=["Sales Orders"])
    app.include_router(dashboard.router,          prefix=f"{API_PREFIX}/dashboard",         tags=["Dashboard"])

    # ── Health-check endpoints ────────────────────────────────────────────────

    @app.get("/", tags=["Health"], summary="Root health check")
    async def root() -> dict:
        """Return application identity and health status."""
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "healthy",
            "docs": "/docs",
        }

    @app.get("/health", tags=["Health"], summary="Liveness probe")
    async def health() -> JSONResponse:
        """Minimal liveness probe used by container orchestrators."""
        return JSONResponse({"status": "ok"})

    return app


# ── ASGI application instance ─────────────────────────────────────────────────
app = create_application()


# ── Dev entrypoint ────────────────────────────────────────────────────────────
# Run with: `python -m app.main`  or  `uvicorn app.main:app --reload`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
