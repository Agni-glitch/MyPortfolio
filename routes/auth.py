from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from core.config import get_settings
from core.db import get_db
from core.limiter import limiter
from core.security import (
    COOKIE_NAME,
    create_access_token,
    decode_access_token,
    generate_otp,
    hash_otp,
    hash_password,
    otp_matches,
    validate_password_strength,
    verify_password,
)
from core.templating import templates
from models.schemas import OTP, User
from utils.mailer import send_otp_email

router = APIRouter(prefix="/admin")

# Verified against when the email is unknown, so response timing doesn't
# reveal whether an account exists.
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


def _is_admin_email(email: str) -> bool:
    return email.strip().lower() == get_settings().admin_email_normalized


def _render(request: Request, name: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, f"admin/{name}", ctx, status_code=status_code)


def _set_session(response, user: dict) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user["email"], user.get("password_version", 0)),
        max_age=s.jwt_expire_minutes * 60,
        httponly=True,
        secure=s.is_production,
        samesite="strict",
        path="/",
    )


@router.get("/login")
async def login_page(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token and decode_access_token(token):
        return RedirectResponse("/admin", status_code=303)
    return _render(request, "login.html")


@router.post("/login")
@limiter.limit("10/15minutes")
async def login(request: Request, email: str = Form(""), password: str = Form(""), db=Depends(get_db)):
    email = email.strip().lower()
    user = await db.users.find_one({"email": email}) if _is_admin_email(email) else None
    ok = verify_password(password, user["password_hash"] if user else _DUMMY_HASH)
    if not (user and ok):
        return _render(request, "login.html", 401, error="Invalid email or password.", email=email)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": datetime.now(timezone.utc)}})
    response = RedirectResponse("/admin", status_code=303)
    _set_session(response, user)
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse("/admin/login?ok=logged_out", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


async def _registration_open(db) -> bool:
    return await db.users.count_documents({}) == 0


@router.get("/register")
async def register_page(request: Request, db=Depends(get_db)):
    return _render(request, "register.html", closed=not await _registration_open(db))


@router.post("/register")
@limiter.limit("5/hour")
async def register(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    confirm: str = Form(""),
    db=Depends(get_db),
):
    if not await _registration_open(db):
        return _render(request, "register.html", 403, closed=True)
    if not _is_admin_email(email):
        return _render(request, "register.html", 403, error="Registration is restricted to the site owner.", email=email)
    if password != confirm:
        return _render(request, "register.html", 422, error="Passwords do not match.", email=email)
    if err := validate_password_strength(password):
        return _render(request, "register.html", 422, error=err, email=email)

    user = User(email=email.strip().lower(), password_hash=hash_password(password))
    await db.users.insert_one(user.model_dump())
    return RedirectResponse("/admin/login?ok=registered", status_code=303)


@router.get("/forgot")
async def forgot_page(request: Request):
    return _render(request, "forgot.html")


@router.post("/forgot")
@limiter.limit("3/15minutes")
async def forgot(request: Request, email: str = Form(""), db=Depends(get_db)):
    s = get_settings()
    email = email.strip().lower()
    # Same response either way, so this can't be used to probe for accounts.
    if _is_admin_email(email) and await db.users.find_one({"email": email}, {"_id": 1}):
        code = generate_otp()
        await db.otps.delete_many({"email": email})
        otp = OTP(
            email=email,
            code_hash=hash_otp(code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=s.otp_ttl_minutes),
        )
        await db.otps.insert_one(otp.model_dump())
        await send_otp_email(email, code, s.otp_ttl_minutes)
    return RedirectResponse("/admin/reset?ok=otp_sent", status_code=303)


@router.get("/reset")
async def reset_page(request: Request):
    return _render(request, "reset.html")


@router.post("/reset")
@limiter.limit("10/15minutes")
async def reset(
    request: Request,
    code: str = Form(""),
    password: str = Form(""),
    confirm: str = Form(""),
    db=Depends(get_db),
):
    s = get_settings()
    email = s.admin_email_normalized
    otp = await db.otps.find_one({"email": email})
    invalid = _render(request, "reset.html", 400, error="Invalid or expired code.")

    if not otp or otp["expires_at"] < datetime.now(timezone.utc) or otp["attempts"] >= s.otp_max_attempts:
        return invalid
    if not otp_matches(code.strip(), otp["code_hash"]):
        await db.otps.update_one({"_id": otp["_id"]}, {"$inc": {"attempts": 1}})
        return invalid
    if password != confirm:
        return _render(request, "reset.html", 422, error="Passwords do not match.")
    if err := validate_password_strength(password):
        return _render(request, "reset.html", 422, error=err)

    await db.users.update_one(
        {"email": email},
        {"$set": {"password_hash": hash_password(password)}, "$inc": {"password_version": 1}},
    )
    await db.otps.delete_many({"email": email})
    response = RedirectResponse("/admin/login?ok=reset_ok", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
