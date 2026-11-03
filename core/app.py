from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import BASE_DIR, get_settings
from core.deps import AdminRedirect
from core.limiter import limiter
from core.templating import templates
from routes import admin, auth, public


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.site_name,
        docs_url=None if s.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if s.is_production else "/openapi.json",
    )
    app.state.limiter = limiter

    # On Vercel, /static is served by the CDN; this mount covers local dev.
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    # auth before admin: login/reset routes must not inherit the admin guard.
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(public.router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if s.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.exception_handler(AdminRedirect)
    async def _admin_redirect(request: Request, exc: AdminRedirect):
        if request.url.path.startswith("/admin/api/"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse("/admin/login", status_code=303)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, exc: RateLimitExceeded):
        return templates.TemplateResponse(
            request, "error.html",
            {"code": 429, "title": "Too many requests", "message": "Please wait a few minutes and try again."},
            status_code=429,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/admin/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        title = {404: "Page not found", 403: "Forbidden"}.get(exc.status_code, "Something went wrong")
        return templates.TemplateResponse(
            request, "error.html",
            {"code": exc.status_code, "title": title, "message": ""},
            status_code=exc.status_code,
        )

    return app
