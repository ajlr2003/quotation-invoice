# =============================================================================
# app/database.py
# -----------------------------------------------------------------------------
# Async SQLAlchemy engine, session factory, and declarative base used by every
# ORM model in the application. Also exposes a FastAPI dependency (`get_db`)
# that provides a per-request transactional session, and lifecycle helpers
# (`init_db`, `close_db`) called from the application lifespan.
# =============================================================================

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ── Async engine ─────────────────────────────────────────────────────────────
# `echo=DEBUG` logs all SQL statements to stdout in debug mode.
# `future=True` enables SQLAlchemy 2.0-style behaviour.

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,        # log SQL statements in debug mode
    future=True,
)

# ── Session factory ───────────────────────────────────────────────────────────
# `expire_on_commit=False` keeps attribute values accessible after a commit
# without triggering a new SELECT, which is important in async contexts.

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,     # keep attributes accessible after commit
    autoflush=False,
    autocommit=False,
)

# ── Declarative base ──────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Declarative base class inherited by all ORM models.

    All table definitions (models) must inherit from this class so that
    ``Base.metadata`` is populated before ``init_db()`` calls ``create_all``.
    """
    pass


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for use in FastAPI route handlers.

    The session is committed automatically on success, or rolled back if an
    exception propagates.  Always closed in the ``finally`` block.

    Yields:
        An ``AsyncSession`` bound to the connection pool.

    Raises:
        Any exception raised inside the route handler — rollback is performed
        before re-raising.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Lifecycle helpers ─────────────────────────────────────────────────────────


async def init_db() -> None:
    """Create all ORM tables via ``Base.metadata.create_all``.

    Intended as a development convenience.  In production, database schema
    changes should be managed exclusively through Alembic migrations.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the SQLAlchemy connection pool on application shutdown.

    Called from the FastAPI ``lifespan`` context manager to cleanly release
    all database connections before the process exits.
    """
    await engine.dispose()
