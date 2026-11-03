import math
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import ValidationError

from core.config import get_settings
from core.db import get_db, ping
from core.limiter import client_ip, limiter
from core.templating import templates
from models.schemas import Message
from routes.common import get_profile
from utils.mailer import send_email
from utils.text import video_embed_url

router = APIRouter()

PUBLISHED = {"status": "published"}
POSTS_PER_PAGE = 9


@router.get("/healthz", include_in_schema=False)
async def healthz():
    # db=false after deploy usually means Atlas Network Access is blocking Vercel.
    db_ok = await ping()
    return JSONResponse({"ok": db_ok, "db": db_ok}, status_code=200 if db_ok else 503)


@router.get("/")
async def home(request: Request, db=Depends(get_db)):
    profile = await get_profile(db)
    featured = await db.projects.find({**PUBLISHED, "featured": True}).sort([("order", 1), ("created_at", -1)]).to_list(6)
    if not featured:
        featured = await db.projects.find(PUBLISHED).sort([("order", 1), ("created_at", -1)]).to_list(6)
    posts = await db.posts.find(PUBLISHED).sort("published_at", -1).to_list(3)
    return templates.TemplateResponse(request, "public/home.html", {
        "profile": profile, "projects": featured, "posts": posts,
    })


@router.get("/projects")
async def projects(request: Request, tag: str = "", category: str = "", db=Depends(get_db)):
    query: dict = dict(PUBLISHED)
    if tag:
        query["tags"] = tag.lower()
    if category:
        query["category"] = category
    items = await db.projects.find(query).sort([("order", 1), ("created_at", -1)]).to_list(200)
    all_tags = sorted(await db.projects.distinct("tags", PUBLISHED))
    categories = sorted(c for c in await db.projects.distinct("category", PUBLISHED) if c)
    return templates.TemplateResponse(request, "public/projects.html", {
        "profile": await get_profile(db), "projects": items, "tags": all_tags,
        "categories": categories, "active_tag": tag.lower(), "active_category": category,
    })


@router.get("/projects/{slug}")
async def project_detail(request: Request, slug: str, db=Depends(get_db)):
    project = await db.projects.find_one({**PUBLISHED, "slug": slug})
    if not project:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "public/project_detail.html", {
        "profile": await get_profile(db), "project": project,
        "video_embed": video_embed_url(project.get("video_url")),
    })


@router.get("/blog")
async def blog(request: Request, tag: str = "", kind: str = "", page: int = 1, db=Depends(get_db)):
    query: dict = dict(PUBLISHED)
    if tag:
        query["tags"] = tag.lower()
    if kind in ("blog", "vlog"):
        query["kind"] = kind
    total = await db.posts.count_documents(query)
    pages = max(1, math.ceil(total / POSTS_PER_PAGE))
    page = min(max(1, page), pages)
    posts = await db.posts.find(query).sort("published_at", -1).skip((page - 1) * POSTS_PER_PAGE).to_list(POSTS_PER_PAGE)
    return templates.TemplateResponse(request, "public/blog.html", {
        "profile": await get_profile(db), "posts": posts, "page": page, "pages": pages,
        "tags": sorted(await db.posts.distinct("tags", PUBLISHED)),
        "active_tag": tag.lower(), "active_kind": kind,
    })


@router.get("/blog/{slug}")
async def post_detail(request: Request, slug: str, db=Depends(get_db)):
    post = await db.posts.find_one({**PUBLISHED, "slug": slug})
    if not post:
        raise HTTPException(status_code=404)
    related = await db.posts.find(
        {**PUBLISHED, "_id": {"$ne": post["_id"]}, "tags": {"$in": post.get("tags", [])}}
    ).sort("published_at", -1).to_list(3)
    return templates.TemplateResponse(request, "public/post_detail.html", {
        "profile": await get_profile(db), "post": post, "related": related,
        "video_embed": video_embed_url(post.get("video_url")),
    })


@router.get("/contact")
async def contact_page(request: Request, db=Depends(get_db)):
    return templates.TemplateResponse(request, "public/contact.html", {"profile": await get_profile(db), "values": {}})


@router.post("/contact")
@limiter.limit("5/hour")
async def contact_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    subject: str = Form(""),
    body: str = Form(""),
    website: str = Form(""),  # honeypot: humans never see/fill it
    db=Depends(get_db),
):
    if website:
        return RedirectResponse("/contact?ok=sent", status_code=303)
    values = {"name": name, "email": email, "subject": subject, "body": body}
    try:
        msg = Message(name=name.strip(), email=email.strip(), subject=subject.strip(), body=body.strip(), ip=client_ip(request))
    except ValidationError as e:
        fields = sorted({str(err["loc"][0]) for err in e.errors()})
        return templates.TemplateResponse(request, "public/contact.html", {
            "profile": await get_profile(db), "values": values,
            "error": f"Please check: {', '.join(fields)}.",
        }, status_code=422)

    await db.messages.insert_one(msg.model_dump())
    s = get_settings()
    # Awaited rather than a BackgroundTask: serverless instances may freeze
    # right after the response, dropping post-response work.
    await send_email(
        s.admin_email,
        f"[{s.site_name}] New message: {msg.subject or 'No subject'}",
        f"From: {msg.name} <{msg.email}>\n\n{msg.body}",
        reply_to=str(msg.email),
    )
    return RedirectResponse("/contact?ok=sent", status_code=303)


@router.get("/robots.txt", include_in_schema=False)
async def robots():
    base = get_settings().site_url.rstrip("/")
    return PlainTextResponse(f"User-agent: *\nDisallow: /admin\nSitemap: {base}/sitemap.xml\n")


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap(db=Depends(get_db)):
    base = get_settings().site_url.rstrip("/")
    urls = [(f"{base}{p}", None) for p in ("/", "/projects", "/blog", "/contact")]
    async for p in db.projects.find(PUBLISHED, {"slug": 1, "updated_at": 1}):
        urls.append((f"{base}/projects/{p['slug']}", p.get("updated_at")))
    async for p in db.posts.find(PUBLISHED, {"slug": 1, "updated_at": 1}):
        urls.append((f"{base}/blog/{p['slug']}", p.get("updated_at")))
    body = "".join(
        f"<url><loc>{escape(u)}</loc>{f'<lastmod>{m.date().isoformat()}</lastmod>' if m else ''}</url>"
        for u, m in urls
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return Response(xml, media_type="application/xml")
