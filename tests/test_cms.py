PROJECT = {
    "title": "My Cool App",
    "summary": "A summary",
    "description": "# Hi\n<script>alert(1)</script>",
    "tags": "Python, API",
    "status": "published",
    "featured": "on",
    "thumbnail": "portfolio/projects/abc",
    "screenshots": ["portfolio/projects/s1", "portfolio/projects/s2"],
    "live_url": "javascript:alert(1)",
    "embed_url": "https://stackblitz.com/edit/x?embed=1",
    "video_url": "https://youtu.be/dQw4w9WgXcQ",
}


def test_dashboard_and_screens(admin):
    for path in ["/admin", "/admin/projects", "/admin/projects/new", "/admin/posts", "/admin/posts/new",
                 "/admin/messages", "/admin/profile"]:
        assert admin.get(path).status_code == 200, path


def test_upload_signature(admin):
    r = admin.post("/admin/api/upload-signature", json={"kind": "projects"})
    assert r.status_code == 200
    body = r.json()
    assert body["cloud_name"] == "demo" and body["signature"] and body["folder"].endswith("/projects")
    assert "api_secret" not in body
    assert admin.post("/admin/api/upload-signature", json={"kind": "../etc"}).status_code == 400


def test_project_lifecycle(admin, db):
    r = admin.post("/admin/projects/new", data=PROJECT)
    assert r.status_code == 303
    p = db.projects.docs[0]
    assert p["slug"] == "my-cool-app"
    assert p["tags"] == ["python", "api"]
    assert p["live_url"] == ""  # non-http URL stripped

    html = admin.get("/projects/my-cool-app").text
    assert "<script>alert(1)</script>" not in html
    assert "f_auto" in html and "q_auto" in html
    assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in html
    assert 'property="og:title" content="My Cool App' in html
    assert admin.get("/projects?tag=python").status_code == 200

    admin.post("/admin/projects/new", data={"title": "My Cool App"})
    assert db.projects.docs[1]["slug"] == "my-cool-app-2"
    assert admin.get("/projects/my-cool-app-2").status_code == 404  # draft

    pid = p["_id"]
    assert admin.post(f"/admin/projects/{pid}", data={**PROJECT, "title": "Renamed", "slug": ""}).status_code == 303
    assert db.projects.docs[0]["title"] == "Renamed"
    assert admin.post(f"/admin/projects/{pid}/delete").status_code == 303
    assert len(db.projects.docs) == 1


def test_post_lifecycle(admin, db):
    r = admin.post("/admin/posts/new", data={
        "title": "Hello World", "content": "word " * 500, "kind": "vlog",
        "video_url": "https://vimeo.com/123456789", "tags": "intro", "status": "published",
    })
    assert r.status_code == 303
    post = db.posts.docs[0]
    assert post["reading_time"] == 3 and post["published_at"]

    assert "player.vimeo.com/video/123456789" in admin.get("/blog/hello-world").text
    assert admin.get("/blog?kind=vlog").status_code == 200
    assert "/blog/hello-world" in admin.get("/sitemap.xml").text


def test_profile_drives_home_page(admin):
    r = admin.post("/admin/profile", data={
        "name": "Test Person", "headline": "Dev", "bio": "bio", "tech_stack": "Go, Rust",
        "social_github": "https://github.com/x", "available_for_work": "on",
    })
    assert r.status_code == 303
    home = admin.get("/").text
    assert "Test Person" in home and "Rust" in home


def test_message_inbox(admin, client, db):
    client.post("/contact", data={"name": "Bob", "email": "bob@example.com", "body": "Hello there!"})
    mid = db.messages.docs[0]["_id"]
    admin.post(f"/admin/messages/{mid}/toggle-read")
    assert db.messages.docs[0]["read"] is True
    admin.post(f"/admin/messages/{mid}/delete")
    assert not db.messages.docs
