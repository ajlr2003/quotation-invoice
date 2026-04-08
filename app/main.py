import logging

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s — %(message)s")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db, close_db, AsyncSessionLocal

# ---------------------------------------------------------------------------
# Import ALL ORM models so Base.metadata is fully populated before
# init_db() calls create_all().  The models/__init__.py comment requires this.
# ---------------------------------------------------------------------------
import app.models  # noqa: F401  — registers every model in Base.metadata

# ---------------------------------------------------------------------------
# Import routers (stubs — each will be expanded in subsequent tasks)
# ---------------------------------------------------------------------------
from app.routers import auth, users, clients, quotations, invoices, suppliers, rfqs, purchase_orders

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — runs startup/shutdown logic around the app
# ---------------------------------------------------------------------------

async def _seed_test_user() -> None:
    """Create a test user (test@example.com / test123) when DEBUG=True and the DB is empty."""
    if not settings.DEBUG:
        return
    from sqlalchemy import select
    from app.models.user import User
    from app.utils.security import hash_password

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(User).where(User.email == "test@example.com"))
        if existing.scalar_one_or_none():
            return
        user = User(
            email="test@example.com",
            full_name="Test User",
            hashed_password=hash_password("test123"),
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        logger.info("Seeded test user: test@example.com / test123")


async def _seed_suppliers() -> None:
    """Seed sample suppliers when DEBUG=True."""
    if not settings.DEBUG:
        return
    from sqlalchemy import select, func
    from app.models.supplier import Supplier

    _SUPPLIERS = [
        dict(company_name="TechSupply Co.",        email="john@techsupply.com",      contact_name="John Doe",        phone="123456789",    country="Saudi Arabia", currency="USD", payment_terms_days=30, is_preferred=True),
        dict(company_name="Gulf Office Supplies",  email="sales@gulfoffice.sa",      contact_name="Ahmad Al-Rashid", phone="+966-11-4001234", country="Saudi Arabia", currency="SAR", payment_terms_days=14),
        dict(company_name="AlMansoori Trading",    email="info@almansoori.ae",       contact_name="Fatima Al-Mansoori", phone="+971-4-3456789", country="UAE",          currency="AED", payment_terms_days=30),
        dict(company_name="GreenTech Industries",  email="procurement@greentech.com", contact_name="Sara Ahmed",      phone="+966-12-6001111", country="Saudi Arabia", currency="USD", payment_terms_days=45, is_preferred=True),
        dict(company_name="FastLog Logistics",     email="ops@fastlog.com",          contact_name="Khalid Nasser",   phone="+971-50-9988776", country="UAE",          currency="USD", payment_terms_days=7),
        dict(company_name="Arabian Print House",   email="quotes@arabprint.sa",      contact_name="Nora Saleh",      phone="+966-13-8877001", country="Saudi Arabia", currency="SAR", payment_terms_days=15),
        dict(company_name="Delta Electronics",     email="supply@deltaelec.com",     contact_name="James Miller",    phone="+1-800-3339900",  country="USA",          currency="USD", payment_terms_days=30),
        dict(company_name="Horizon Packaging",     email="orders@horizonpack.com",   contact_name="Liu Wei",         phone="+86-21-5558800",  country="China",        currency="USD", payment_terms_days=60),
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
    # ── Startup ──────────────────────────────────────────────────────────
    print(f"🚀  Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    await _seed_test_user()
    await _seed_suppliers()
    yield
    # ── Shutdown ─────────────────────────────────────────────────────────
    print("🛑  Shutting down — closing DB pool")
    await close_db()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "REST API for Quotation-to-Invoice Workflow Automation. "
            "Handles quotation creation, approval, and conversion to invoices."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ──────────────────────────────────────────────────────────
    API_PREFIX = "/api/v1"

    app.include_router(auth.router,        prefix=f"{API_PREFIX}/auth",       tags=["Authentication"])
    app.include_router(users.router,       prefix=f"{API_PREFIX}/users",      tags=["Users"])
    app.include_router(clients.router,     prefix=f"{API_PREFIX}/clients",    tags=["Clients"])
    app.include_router(suppliers.router,   prefix=f"{API_PREFIX}/suppliers",  tags=["Suppliers"])
    app.include_router(rfqs.router,        prefix=f"{API_PREFIX}/rfqs",       tags=["RFQs"])
    app.include_router(quotations.router,       prefix=f"{API_PREFIX}/quotations",      tags=["Quotations"])
    app.include_router(purchase_orders.router,  prefix=f"{API_PREFIX}/purchase-orders", tags=["Purchase Orders"])
    app.include_router(invoices.router,    prefix=f"{API_PREFIX}/invoices",   tags=["Invoices"])

    # ── Root health-check ─────────────────────────────────────────────────
    @app.get("/", tags=["Health"], summary="Root health check")
    async def root():
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "healthy",
            "docs": "/docs",
        }

    @app.get("/health", tags=["Health"], summary="Liveness probe")
    async def health():
        return JSONResponse({"status": "ok"})

    return app


app = create_application()


# ---------------------------------------------------------------------------
# Dev entrypoint: `python -m app.main` or `uvicorn app.main:app --reload`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
