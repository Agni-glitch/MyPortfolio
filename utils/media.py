"""Cloudinary helpers.

Uploads go directly from the admin's browser to Cloudinary using a
server-generated signature. That keeps large images off the serverless
function (Vercel caps request bodies at ~4.5 MB) while the API secret
never leaves the server.
"""
import asyncio
import os
import time
from urllib.parse import unquote, urlparse

# The SDK parses CLOUDINARY_URL from os.environ at import time and raises on
# a malformed value, which would take down the whole app. Hide it during the
# import; _ensure_config() parses it leniently instead.
_env_url = os.environ.pop("CLOUDINARY_URL", None)
try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.utils
finally:
    if _env_url is not None:
        os.environ["CLOUDINARY_URL"] = _env_url

from core.config import get_settings

_configured = False

# Applied at upload time: cap stored originals at 2400px wide.
UPLOAD_TRANSFORMATION = "c_limit,w_2400"


class CloudinaryNotConfigured(RuntimeError):
    pass


def _ensure_config() -> None:
    global _configured
    if _configured:
        return
    # Parsed explicitly: the SDK only auto-reads CLOUDINARY_URL from
    # os.environ, which pydantic-settings does not populate from .env.
    # Tolerate values pasted into the Vercel dashboard with surrounding
    # quotes/whitespace or a leading "CLOUDINARY_URL=".
    raw = get_settings().cloudinary_url.strip().strip("'\"").strip()
    if raw.upper().startswith("CLOUDINARY_URL="):
        raw = raw.split("=", 1)[1].strip().strip("'\"")
    if not raw:
        raise CloudinaryNotConfigured("CLOUDINARY_URL environment variable is not set")
    p = urlparse(raw)
    # p.hostname would lowercase the cloud name, so take it from netloc.
    cloud_name = p.netloc.rpartition("@")[2]
    if p.scheme != "cloudinary" or not (cloud_name and p.username and p.password):
        raise CloudinaryNotConfigured(
            "CLOUDINARY_URL must look like cloudinary://<api_key>:<api_secret>@<cloud_name>")
    cloudinary.config(cloud_name=cloud_name, api_key=unquote(p.username),
                      api_secret=unquote(p.password), secure=True)
    _configured = True


def upload_signature(kind: str) -> dict:
    """Return the params the browser needs for a signed direct upload."""
    _ensure_config()
    cfg = cloudinary.config()
    params = {
        "timestamp": int(time.time()),
        "folder": f"{get_settings().cloudinary_folder}/{kind}",
        "transformation": UPLOAD_TRANSFORMATION,
    }
    params["signature"] = cloudinary.utils.api_sign_request(params, cfg.api_secret)
    params["api_key"] = cfg.api_key
    params["cloud_name"] = cfg.cloud_name
    return params


async def delete_asset(public_id: str) -> None:
    if not public_id:
        return
    try:
        _ensure_config()
        await asyncio.to_thread(cloudinary.uploader.destroy, public_id, invalidate=True)
    except Exception:  # cleanup is best-effort; never block a DB delete on it
        pass


def cld_url(public_id: str | None, width: int | None = None, height: int | None = None, crop: str = "fill") -> str:
    """Optimized delivery URL: f_auto + q_auto, optional resize."""
    if not public_id:
        return ""
    try:
        _ensure_config()
    except CloudinaryNotConfigured:
        return ""
    opts: dict = {"fetch_format": "auto", "quality": "auto", "secure": True}
    if width:
        opts.update(width=width, crop=crop if height else "limit")
    if height:
        opts["height"] = height
        opts["gravity"] = "auto"
    url, _ = cloudinary.utils.cloudinary_url(public_id, **opts)
    return url


def cld_srcset(public_id: str | None, widths: tuple[int, ...] = (400, 800, 1200, 1600), ratio: float | None = None) -> str:
    if not public_id:
        return ""
    parts = []
    for w in widths:
        h = int(w / ratio) if ratio else None
        parts.append(f"{cld_url(public_id, w, h)} {w}w")
    return ", ".join(parts)
