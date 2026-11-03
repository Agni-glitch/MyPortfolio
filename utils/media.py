"""Cloudinary helpers.

Uploads go directly from the admin's browser to Cloudinary using a
server-generated signature. That keeps large images off the serverless
function (Vercel caps request bodies at ~4.5 MB) while the API secret
never leaves the server.
"""
import asyncio
import time
from urllib.parse import unquote, urlparse

import cloudinary
import cloudinary.uploader
import cloudinary.utils

from core.config import get_settings

_configured = False

# Applied at upload time: cap stored originals at 2400px wide.
UPLOAD_TRANSFORMATION = "c_limit,w_2400"


def _ensure_config() -> None:
    global _configured
    if not _configured:
        # Parsed explicitly: the SDK only auto-reads CLOUDINARY_URL from
        # os.environ, which pydantic-settings does not populate from .env.
        p = urlparse(get_settings().cloudinary_url)
        if p.scheme == "cloudinary" and p.hostname:
            cloudinary.config(cloud_name=p.hostname, api_key=unquote(p.username or ""),
                              api_secret=unquote(p.password or ""), secure=True)
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
    _ensure_config()
    try:
        await asyncio.to_thread(cloudinary.uploader.destroy, public_id, invalidate=True)
    except Exception:  # cleanup is best-effort; never block a DB delete on it
        pass


def cld_url(public_id: str | None, width: int | None = None, height: int | None = None, crop: str = "fill") -> str:
    """Optimized delivery URL: f_auto + q_auto, optional resize."""
    if not public_id:
        return ""
    _ensure_config()
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
