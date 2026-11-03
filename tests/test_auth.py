import re

from tests.conftest import ADMIN, PASSWORD


def register(client, email=ADMIN):
    return client.post("/admin/register", data={"email": email, "password": PASSWORD, "confirm": PASSWORD})


def test_admin_pages_require_login(client):
    assert client.get("/admin").headers["location"] == "/admin/login"
    assert client.post("/admin/api/upload-signature", json={"kind": "projects"}).status_code == 401


def test_registration_only_for_admin_email_and_only_once(client):
    assert register(client, "someone@else.com").status_code == 403
    assert register(client).status_code == 303
    assert register(client).status_code == 403


def test_login(client):
    register(client)
    assert client.post("/admin/login", data={"email": ADMIN, "password": "wrong"}).status_code == 401
    r = client.post("/admin/login", data={"email": ADMIN, "password": PASSWORD})
    assert r.status_code == 303
    assert "admin_session" in r.cookies


def test_login_rate_limited(client):
    codes = [client.post("/admin/login", data={"email": "x@y.z", "password": "p"}).status_code for _ in range(11)]
    assert codes[-1] == 429


def test_otp_password_reset(client, outbox):
    register(client)
    client.post("/admin/forgot", data={"email": ADMIN})
    code = next(m["otp"] for m in outbox if "otp" in m)
    assert re.fullmatch(r"\d{6}", code)

    wrong = "000000" if code != "000000" else "111111"
    new = {"password": "NewPassw0rd!", "confirm": "NewPassw0rd!"}
    assert client.post("/admin/reset", data={"code": wrong, **new}).status_code == 400
    assert client.post("/admin/reset", data={"code": code, **new}).status_code == 303
    # Code is single-use.
    assert client.post("/admin/reset", data={"code": code, **new}).status_code == 400

    assert client.post("/admin/login", data={"email": ADMIN, "password": PASSWORD}).status_code == 401
    assert client.post("/admin/login", data={"email": ADMIN, "password": "NewPassw0rd!"}).status_code == 303


def test_forgot_does_not_reveal_unknown_emails(client, outbox):
    r = client.post("/admin/forgot", data={"email": "nobody@example.com"})
    assert r.status_code == 303
    assert not outbox


def test_password_change_invalidates_old_session(admin, outbox):
    assert admin.get("/admin").status_code == 200
    admin.post("/admin/forgot", data={"email": ADMIN})
    code = next(m["otp"] for m in outbox if "otp" in m)
    old_cookie = admin.cookies["admin_session"]
    admin.post("/admin/reset", data={"code": code, "password": "NewPassw0rd!", "confirm": "NewPassw0rd!"})
    admin.cookies.clear()
    admin.cookies.set("admin_session", old_cookie)
    assert admin.get("/admin").status_code == 303
