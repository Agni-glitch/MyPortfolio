import os
import sys
from pathlib import Path

import pytest

# Test settings. Real env vars take priority over .env in pydantic-settings,
# so these win locally too and no real service is ever contacted.
os.environ.update({
    "MONGO_URI": "mongodb://localhost:27017/unused",
    "JWT_SECRET_KEY": "test-secret-key-for-ci-only-0123456789abcdef",
    "ADMIN_EMAIL": "admin@example.com",
    "CLOUDINARY_URL": "cloudinary://123:secret@demo",
    "SMTP_PASSWORD": "",
    "SITE_URL": "http://testserver",
    "ENVIRONMENT": "development",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import routes.admin  # noqa: E402
import routes.auth  # noqa: E402
import routes.public  # noqa: E402
from api.index import app  # noqa: E402
from core.db import get_db  # noqa: E402
from core.limiter import limiter  # noqa: E402
from tests.fakes import FakeDB  # noqa: E402

ADMIN = "admin@example.com"
PASSWORD = "Passw0rd!!x"


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []

    async def fake_send(to, subject, text, html=None, reply_to=None):
        sent.append({"to": to, "subject": subject, "text": text})
        return True

    async def fake_otp(to, code, ttl):
        sent.append({"to": to, "otp": code})
        return True

    async def fake_delete(public_id):
        pass

    monkeypatch.setattr(routes.public, "send_email", fake_send)
    monkeypatch.setattr(routes.auth, "send_otp_email", fake_otp)
    monkeypatch.setattr(routes.admin, "delete_asset", fake_delete)

    async def fake_ping():
        return True

    monkeypatch.setattr(routes.public, "ping", fake_ping)
    return sent


@pytest.fixture
def client(db, outbox):
    async def _db():
        return db

    app.dependency_overrides[get_db] = _db
    limiter.reset()
    with TestClient(app, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin(client):
    """A client logged in as the admin."""
    client.post("/admin/register", data={"email": ADMIN, "password": PASSWORD, "confirm": PASSWORD})
    r = client.post("/admin/login", data={"email": ADMIN, "password": PASSWORD})
    assert "admin_session" in client.cookies, r.status_code  # TestClient keeps response cookies
    return client
