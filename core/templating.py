from datetime import datetime

from fastapi.templating import Jinja2Templates

from core.config import BASE_DIR, get_settings
from utils.media import cld_srcset, cld_url
from utils.text import render_markdown

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_env = templates.env
_env.filters["cld"] = cld_url
_env.filters["cld_srcset"] = cld_srcset
_env.filters["markdown"] = render_markdown


def _fmt_date(value: datetime | None, fmt: str = "%b %d, %Y") -> str:
    return value.strftime(fmt) if value else ""


_env.filters["date"] = _fmt_date
_env.globals["settings"] = get_settings()
_env.globals["now"] = datetime.now
_env.globals["ui"] = {
    "input": "mt-1 block w-full rounded-lg border-slate-300 bg-white shadow-sm focus:border-brand-500 "
             "focus:ring-brand-500 dark:border-slate-700 dark:bg-slate-900",
    "btn": "rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60",
    "btn_outline": "rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold hover:bg-slate-50 "
                   "dark:border-slate-700 dark:hover:bg-slate-800",
}

FLASH_MESSAGES = {
    "saved": ("success", "Saved."),
    "deleted": ("success", "Deleted."),
    "sent": ("success", "Thanks! Your message has been sent."),
    "otp_sent": ("success", "If that email is registered, a 6-digit code has been sent."),
    "reset_ok": ("success", "Password updated. Please log in."),
    "registered": ("success", "Admin account created. Please log in."),
    "logged_out": ("info", "You have been logged out."),
}


def flash_from(request) -> tuple[str, str] | None:
    """Map a whitelisted ?ok= code to a message (never reflects raw input)."""
    return FLASH_MESSAGES.get(request.query_params.get("ok", ""))


_env.globals["flash_from"] = flash_from
