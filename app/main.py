from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db, close_db

# ---------------------------------------------------------------------------
# Import routers (stubs — each will be expanded in subsequent tasks)
# ---------------------------------------------------------------------------
from app.routers import auth, users, clients, quotations, invoices, suppliers, rfqs


# ---------------------------------------------------------------------------
# Lifespan — runs startup/shutdown logic around the app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    print(f"🚀  Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
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
    app.include_router(quotations.router,  prefix=f"{API_PREFIX}/quotations", tags=["Quotations"])
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
