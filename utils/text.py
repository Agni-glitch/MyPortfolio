import math
import re
import unicodedata
from urllib.parse import parse_qs, urlparse

import markdown as md
import nh3
from markupsafe import Markup

_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "del", "div", "em", "h1", "h2", "h3", "h4",
    "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "span", "strong", "sub", "sup",
    "table", "tbody", "td", "th", "thead", "tr", "ul", "figure", "figcaption",
}
_ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "code": {"class"},
    "span": {"class"},
    "div": {"class"},
    "th": {"align"},
    "td": {"align"},
    "h2": {"id"}, "h3": {"id"}, "h4": {"id"},
}


def render_markdown(text: str | None) -> Markup:
    """Markdown -> sanitized HTML. Safe to render with |safe semantics."""
    if not text:
        return Markup("")
    html = md.markdown(text, extensions=["fenced_code", "tables", "toc", "sane_lists"])
    clean = nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )
    return Markup(clean)


def reading_time(text: str | None) -> int:
    words = len(re.findall(r"\w+", text or ""))
    return max(1, math.ceil(words / 220))


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s_]+", "-", value).strip("-")[:80] or "item"


def parse_tags(raw: str | None) -> list[str]:
    seen: dict[str, None] = {}
    for t in (raw or "").split(","):
        t = t.strip().lower()
        if t:
            seen.setdefault(t[:40], None)
    return list(seen)[:20]


def video_embed_url(url: str | None) -> str | None:
    """Turn a YouTube/Vimeo watch URL into a privacy-friendly embed URL."""
    if not url:
        return None
    try:
        p = urlparse(url.strip())
    except ValueError:
        return None
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    vid = None
    if host == "youtu.be":
        vid = p.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if p.path == "/watch":
            vid = parse_qs(p.query).get("v", [None])[0]
        elif p.path.startswith(("/embed/", "/shorts/", "/live/")):
            vid = p.path.split("/")[2]
    if vid and re.fullmatch(r"[\w-]{6,20}", vid):
        return f"https://www.youtube-nocookie.com/embed/{vid}"
    if host in ("vimeo.com", "player.vimeo.com"):
        m = re.search(r"/(\d{5,12})(?:/|$)", p.path)
        if m:
            return f"https://player.vimeo.com/video/{m.group(1)}"
    return None


def safe_http_url(url: str | None) -> str:
    """Accept only absolute http(s) URLs; anything else becomes empty."""
    url = (url or "").strip()
    p = urlparse(url)
    return url if p.scheme in ("http", "https") and p.netloc else ""
