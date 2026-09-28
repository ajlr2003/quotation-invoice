"""
Shared pytest fixtures for the accounting test suite.

Strategy:
- Register a fresh test user at session start, get a JWT token.
- Expose a `client` fixture (httpx) and an `auth_headers` fixture.
- All tests hit the live server on localhost:8000 (must be running).
"""

import asyncio
import uuid
import pytest
import httpx

BASE = "http://localhost:8000/api/v1"

TEST_EMAIL    = f"test_{uuid.uuid4().hex[:8]}@kytos-test.com"
TEST_PASSWORD = "TestPass123!"
TEST_NAME     = "Test User"


async def _promote_to_admin(email: str) -> None:
    """Self-registration always creates a VIEWER (see auth_service.register_user —
    a deliberate security choice, role escalation requires an existing ADMIN).
    The accounting suite needs write access, so promote the freshly registered
    test user directly in the DB rather than via the API (which would need an
    ADMIN token we don't have yet — chicken-and-egg)."""
    from sqlalchemy import update
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.models.enums import UserRole

    async with AsyncSessionLocal() as db:
        await db.execute(update(User).where(User.email == email.lower()).values(role=UserRole.ADMIN))
        await db.commit()


@pytest.fixture(scope="session")
def token():
    """Register a test user, promote it to admin, and return a valid access token."""
    with httpx.Client(base_url=BASE) as c:
        r = c.post("/auth/register", json={
            "email":     TEST_EMAIL,
            "password":  TEST_PASSWORD,
            "full_name": TEST_NAME,
        })
        assert r.status_code == 201, f"Register failed: {r.text}"
        asyncio.run(_promote_to_admin(TEST_EMAIL))
        return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE, timeout=15) as c:
        yield c
