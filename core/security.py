import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from core.config import get_settings

COOKIE_NAME = "admin_session"


# bcrypt is used directly: passlib is unmaintained and breaks on bcrypt>=4.1.
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def validate_password_strength(password: str) -> str | None:
    if len(password) < 10:
        return "Password must be at least 10 characters."
    if password.isalpha() or password.isdigit():
        return "Password must mix letters with numbers or symbols."
    return None


def create_access_token(email: str, password_version: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "pv": password_version,  # bumped on password change -> invalidates old sessions
        "iat": now,
        "exp": now + timedelta(minutes=s.jwt_expire_minutes),
    }
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm], options={"require": ["sub", "exp"]})
    except jwt.PyJWTError:
        return None


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    key = get_settings().jwt_secret_key.encode()
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def otp_matches(code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(code), stored_hash)
