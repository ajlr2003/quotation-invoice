"""
Shared pytest fixtures for the accounting test suite.

Strategy:
- Register a fresh test user at session start, get a JWT token.
- Expose a `client` fixture (httpx) and an `auth_headers` fixture.
- All tests hit the live server on localhost:8000 (must be running).
"""

import uuid
import pytest
import httpx

BASE = "http://localhost:8000/api/v1"

TEST_EMAIL    = f"test_{uuid.uuid4().hex[:8]}@kytos-test.com"
TEST_PASSWORD = "TestPass123!"
TEST_NAME     = "Test User"


@pytest.fixture(scope="session")
def token():
    """Register a test user and return a valid access token."""
    with httpx.Client(base_url=BASE) as c:
        r = c.post("/auth/register", json={
            "email":     TEST_EMAIL,
            "password":  TEST_PASSWORD,
            "full_name": TEST_NAME,
        })
        assert r.status_code == 201, f"Register failed: {r.text}"
        return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE, timeout=15) as c:
        yield c
