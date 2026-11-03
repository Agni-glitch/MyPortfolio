from fastapi import Depends, Request

from core.db import get_db
from core.security import COOKIE_NAME, decode_access_token


class AdminRedirect(Exception):
    """Raised when an admin page is requested without a valid session."""


async def get_current_admin(request: Request, db=Depends(get_db)) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    payload = decode_access_token(token) if token else None
    if not payload:
        raise AdminRedirect()
    user = await db.users.find_one({"email": payload["sub"]})
    if not user or user.get("password_version", 0) != payload.get("pv"):
        raise AdminRedirect()
    return user
