"""Password hashing (Argon2) and JWT access tokens (HS256)."""
from __future__ import annotations

import secrets
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import jwt
from pwdlib import PasswordHash

from ..config import BASE_DIR, get_settings
from .db import User, utcnow

_hasher = PasswordHash.recommended()
ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password, password_hash)
    except Exception:  # noqa: BLE001 - malformed hash = no match
        return False


@lru_cache
def _secret() -> str:
    s = get_settings().jwt_secret
    if s:
        return s
    path = BASE_DIR / "data" / ".jwt_secret"  # generated once, kept out of the code and .env
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    return value


def create_access_token(user: User) -> tuple[str, int]:
    minutes = get_settings().jwt_expire_minutes
    now = utcnow()
    payload = {"sub": str(user.id), "role": user.role, "ver": user.token_version,
               "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=minutes)).timestamp())}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM), minutes * 60


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError when invalid or expired."""
    return jwt.decode(token, _secret(), algorithms=[ALGORITHM], options={"require": ["sub", "exp", "iat"]})
