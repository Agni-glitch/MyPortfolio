from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError

from core.db import get_db
from core.deps import get_current_admin
from core.templating import templates
from models.schemas import BlogPost, Profile, Project, SocialLinks
from routes.common import get_profile, oid, unique_slug
from utils.media import delete_asset, upload_signature
from utils.text import parse_tags, reading_time, slugify

router = APIRouter(prefix="/admin", dependencies=[Depends(get_current_admin)])


def _render(request: Request, name: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, f"admin/{name}", ctx, status_code=status_code)


def _errors(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Dashboard ----------

@router.get("")
async def dashboard(request: Request, db=Depends(get_db)):
    stats = {
        "projects": await db.projects.count_documents({}),
        "projects_published": await db.projects.count_documents({"status": "published"}),
        "posts": await db.posts.count_documents({"kind": "blog"}),
        "vlogs": await db.posts.count_documents({"kind": "vlog"}),
        "drafts": await db.posts.count_documents({"status": "draft"}) + await db.projects.count_documents({"status": "draft"}),
        "messages": await db.messages.count_documents({}),
        "unread": await db.messages.count_documents({"read": False}),
    }
    recent = await db.messages.find().sort("created_at", -1).to_list(5)
    return _render(request, "dashboard.html", stats=stats, recent=recent)


# ---------- Uploads ----------

@router.post("/api/upload-signature")
async def sign_upload(request: Request):
    data = await request.json()
    kind = data.get("kind", "misc")
    if kind not in ("projects", "posts", "profile", "misc"):
        raise HTTPException(status_code=400, detail="Invalid upload kind")
    try:
        return JSONResponse(upload_signature(kind))
    except Exception:
        raise HTTPException(status_code=500, detail="Cloudinary is not configured")


# ---------- Projects ----------

@router.get("/projects")
async def projects_list(request: Request, db=Depends(get_db)):
    items = await db.projects.find().sort([("order", 1), ("created_at", -1)]).to_list(500)
    return _render(request, "projects_list.html", items=items)


@router.get("/projects/new")
async def project_new(request: Request):
    return _render(request, "project_form.html", item={}, is_new=True)


@router.get("/projects/{item_id}")
async def project_edit(request: Request, item_id: str, db=Depends(get_db)):
    item = await db.projects.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(status_code=404)
    return _render(request, "project_form.html", item=item, is_new=False)


async def _project_from_form(request: Request, db, existing: dict | None) -> tuple[dict, str | None]:
    form = await request.form()
    raw = {k: (form.get(k) or "").strip() for k in (
        "title", "slug", "summary", "description", "category", "thumbnail",
        "live_url", "repo_url", "embed_url", "video_url",
    )}
    raw["tags"] = parse_tags(form.get("tags"))
    raw["tech_stack"] = parse_tags(form.get("tech_stack"))
    raw["screenshots"] = [s for s in form.getlist("screenshots") if s]
    raw["featured"] = form.get("featured") == "on"
    raw["status"] = "published" if form.get("status") == "published" else "draft"
    try:
        raw["order"] = int(form.get("order") or 0)
    except ValueError:
        raw["order"] = 0
    exclude = existing["_id"] if existing else None
    raw["slug"] = await unique_slug(db.projects, slugify(raw["slug"] or raw["title"]), exclude)
    if existing:
        raw["created_at"] = existing.get("created_at", _now())
    try:
        return Project(**raw).model_dump(), None
    except ValidationError as e:
        return raw, _errors(e)


@router.post("/projects/new")
async def project_create(request: Request, db=Depends(get_db)):
    data, err = await _project_from_form(request, db, None)
    if err:
        return _render(request, "project_form.html", 422, item=data, is_new=True, error=err)
    result = await db.projects.insert_one(data)
    return RedirectResponse(f"/admin/projects/{result.inserted_id}?ok=saved", status_code=303)


@router.post("/projects/{item_id}")
async def project_update(request: Request, item_id: str, db=Depends(get_db)):
    existing = await db.projects.find_one({"_id": oid(item_id)})
    if not existing:
        raise HTTPException(status_code=404)
    data, err = await _project_from_form(request, db, existing)
    if err:
        return _render(request, "project_form.html", 422, item={**data, "_id": existing["_id"]}, is_new=False, error=err)
    data["updated_at"] = _now()
    await db.projects.replace_one({"_id": existing["_id"]}, data)
    return RedirectResponse(f"/admin/projects/{item_id}?ok=saved", status_code=303)


@router.post("/projects/{item_id}/delete")
async def project_delete(item_id: str, db=Depends(get_db)):
    item = await db.projects.find_one_and_delete({"_id": oid(item_id)})
    if item:
        for pid in [item.get("thumbnail"), *item.get("screenshots", [])]:
            await delete_asset(pid)
    return RedirectResponse("/admin/projects?ok=deleted", status_code=303)


# ---------- Blog / Vlogs ----------

@router.get("/posts")
async def posts_list(request: Request, db=Depends(get_db)):
    items = await db.posts.find().sort("created_at", -1).to_list(500)
    return _render(request, "posts_list.html", items=items)


@router.get("/posts/new")
async def post_new(request: Request):
    return _render(request, "post_form.html", item={"kind": request.query_params.get("kind", "blog")}, is_new=True)


@router.get("/posts/{item_id}")
async def post_edit(request: Request, item_id: str, db=Depends(get_db)):
    item = await db.posts.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(status_code=404)
    return _render(request, "post_form.html", item=item, is_new=False)


async def _post_from_form(request: Request, db, existing: dict | None) -> tuple[dict, str | None]:
    form = await request.form()
    raw = {k: (form.get(k) or "").strip() for k in ("title", "slug", "excerpt", "content", "cover_image", "video_url")}
    raw["kind"] = "vlog" if form.get("kind") == "vlog" else "blog"
    raw["tags"] = parse_tags(form.get("tags"))
    raw["status"] = "published" if form.get("status") == "published" else "draft"
    raw["reading_time"] = reading_time(raw["content"])
    exclude = existing["_id"] if existing else None
    raw["slug"] = await unique_slug(db.posts, slugify(raw["slug"] or raw["title"]), exclude)
    if existing:
        raw["created_at"] = existing.get("created_at", _now())
        raw["published_at"] = existing.get("published_at")
    # First publish stamps the date; unpublishing keeps it for re-publish.
    if raw["status"] == "published" and not raw.get("published_at"):
        raw["published_at"] = _now()
    try:
        return BlogPost(**raw).model_dump(), None
    except ValidationError as e:
        return raw, _errors(e)


@router.post("/posts/new")
async def post_create(request: Request, db=Depends(get_db)):
    data, err = await _post_from_form(request, db, None)
    if err:
        return _render(request, "post_form.html", 422, item=data, is_new=True, error=err)
    result = await db.posts.insert_one(data)
    return RedirectResponse(f"/admin/posts/{result.inserted_id}?ok=saved", status_code=303)


@router.post("/posts/{item_id}")
async def post_update(request: Request, item_id: str, db=Depends(get_db)):
    existing = await db.posts.find_one({"_id": oid(item_id)})
    if not existing:
        raise HTTPException(status_code=404)
    data, err = await _post_from_form(request, db, existing)
    if err:
        return _render(request, "post_form.html", 422, item={**data, "_id": existing["_id"]}, is_new=False, error=err)
    data["updated_at"] = _now()
    await db.posts.replace_one({"_id": existing["_id"]}, data)
    return RedirectResponse(f"/admin/posts/{item_id}?ok=saved", status_code=303)


@router.post("/posts/{item_id}/delete")
async def post_delete(item_id: str, db=Depends(get_db)):
    item = await db.posts.find_one_and_delete({"_id": oid(item_id)})
    if item:
        await delete_asset(item.get("cover_image"))
    return RedirectResponse("/admin/posts?ok=deleted", status_code=303)


# ---------- Messages ----------

@router.get("/messages")
async def messages_list(request: Request, db=Depends(get_db)):
    items = await db.messages.find().sort("created_at", -1).to_list(500)
    return _render(request, "messages.html", items=items)


@router.post("/messages/{item_id}/toggle-read")
async def message_toggle(item_id: str, db=Depends(get_db)):
    msg = await db.messages.find_one({"_id": oid(item_id)}, {"read": 1})
    if msg:
        await db.messages.update_one({"_id": msg["_id"]}, {"$set": {"read": not msg.get("read", False)}})
    return RedirectResponse("/admin/messages", status_code=303)


@router.post("/messages/{item_id}/delete")
async def message_delete(item_id: str, db=Depends(get_db)):
    await db.messages.delete_one({"_id": oid(item_id)})
    return RedirectResponse("/admin/messages?ok=deleted", status_code=303)


# ---------- Profile ----------

@router.get("/profile")
async def profile_page(request: Request, db=Depends(get_db)):
    return _render(request, "profile.html", profile=await get_profile(db))


@router.post("/profile")
async def profile_save(request: Request, db=Depends(get_db)):
    form = await request.form()
    raw = {k: (form.get(k) or "").strip() for k in (
        "name", "headline", "bio", "about", "avatar", "location", "resume_url", "cta_label",
    )}
    raw["tech_stack"] = [t.strip() for t in (form.get("tech_stack") or "").split(",") if t.strip()]
    raw["available_for_work"] = form.get("available_for_work") == "on"
    try:
        raw["socials"] = SocialLinks(**{k: (form.get(f"social_{k}") or "").strip() for k in SocialLinks.model_fields})
        profile = Profile(**raw)
    except ValidationError as e:
        return _render(request, "profile.html", 422, profile=await get_profile(db), error=_errors(e))
    await db.settings.replace_one({"_id": "profile"}, {"_id": "profile", **profile.model_dump()}, upsert=True)
    return RedirectResponse("/admin/profile?ok=saved", status_code=303)
