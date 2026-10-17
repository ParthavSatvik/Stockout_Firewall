import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).parent / "test_stockout.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

# Must happen before any `app.*` module is imported anywhere in the test session,
# since app.database builds its engine from settings at import time.
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["LOCAL_JWT_SECRET"] = "test-only-secret-at-least-32-bytes-long"
os.environ["DEMO_MODE"] = "true"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.seed import seed_data  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _seeded_database():
    seed_data.run()
    yield


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


def login(client: TestClient, email: str, password: str = "demo1234") -> str:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def future(hours: float = 24) -> str:
    """A ready-by time that is always in the future (ready-by must not be in the past)."""
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
