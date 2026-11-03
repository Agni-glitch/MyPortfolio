import pytest


@pytest.mark.parametrize("path", ["/", "/projects", "/blog", "/contact", "/robots.txt", "/sitemap.xml", "/healthz"])
def test_public_pages_render_on_empty_db(client, path):
    assert client.get(path).status_code == 200


def test_unknown_slug_is_404(client):
    assert client.get("/projects/nope").status_code == 404
    assert client.get("/blog/nope").status_code == 404


def test_contact_saves_and_notifies(client, db, outbox):
    r = client.post("/contact", data={"name": "Bob", "email": "bob@example.com", "subject": "Hi", "body": "Hello there!"})
    assert r.status_code == 303
    assert len(db.messages.docs) == 1
    assert outbox and outbox[0]["to"] == "admin@example.com"


def test_contact_validation(client, db):
    assert client.post("/contact", data={"name": "", "email": "bad", "body": "x"}).status_code == 422
    assert not db.messages.docs


def test_contact_honeypot_drops_spam(client, db):
    r = client.post("/contact", data={"name": "Bot", "email": "b@example.com", "body": "spam spam", "website": "x"})
    assert r.status_code == 303
    assert not db.messages.docs


def test_contact_rate_limited(client):
    data = {"name": "Bob", "email": "bob@example.com", "body": "Hello there!"}
    codes = [client.post("/contact", data=data).status_code for _ in range(6)]
    assert codes[-1] == 429
