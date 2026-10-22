"""/api/auth (login, me, password) and developer-only /api/users + /api/usage."""
from __future__ import annotations

import re
import threading
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..domains import DOMAIN_IDS
from . import usage as usage_store
from .db import ROLES, SessionLocal, User, iso, utcnow
from .deps import Principal, current_user, require
from .security import MIN_PASSWORD_LENGTH, create_access_token, hash_password, verify_password

router = APIRouter()
developer = require("developer")
Role = Literal["user", "superuser", "developer"]
_USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,64}$")

# brute-force protection: 5 failed logins per username -> 5 minute lockout
_failures: dict[str, list[float]] = {}
_fail_lock = threading.Lock()
MAX_FAILURES, LOCKOUT_S = 5, 300


def _check_lockout(username: str) -> None:
    with _fail_lock:
        recent = [t for t in _failures.get(username, []) if time.time() - t < LOCKOUT_S]
        _failures[username] = recent
        if len(recent) >= MAX_FAILURES:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in a few minutes.")


def _register_failure(username: str) -> None:
    with _fail_lock:
        _failures.setdefault(username, []).append(time.time())


def user_out(u: User, stats: dict | None = None) -> dict:
    s = stats or {}
    return {
        "id": u.id, "username": u.username, "display_name": u.display_name or u.username, "role": u.role,
        "domains": list(u.domains or []), "is_active": u.is_active,
        "created_at": iso(u.created_at),
        "last_login_at": iso(u.last_login_at),
        "questions_30d": s.get("questions", 0),
        "tokens_30d": s.get("input_tokens", 0) + s.get("output_tokens", 0),
        "last_active": iso(s.get("last_active")),
    }


def _validate_domains(domains: list[str]) -> list[str]:
    bad = [d for d in domains if d not in DOMAIN_IDS]
    if bad:
        raise HTTPException(422, f"Unknown domain(s): {bad}. Valid: {sorted(DOMAIN_IDS)}")
    return list(dict.fromkeys(domains))


def _validate_password(pw: str) -> None:
    if len(pw) < MIN_PASSWORD_LENGTH:
        raise HTTPException(422, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def _active_developers(db, excluding: int | None = None) -> int:
    q = select(func.count()).select_from(User).where(User.role == "developer", User.is_active.is_(True))
    if excluding is not None:
        q = q.where(User.id != excluding)
    return db.scalar(q) or 0


# ------------------------------------------------------------------ auth
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/api/auth/login")
def login(req: LoginRequest):
    name = req.username.strip().lower()
    _check_lockout(name)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.username) == name))
        if user is None or not verify_password(req.password, user.password_hash):
            _register_failure(name)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")
        user.last_login_at = utcnow()
        db.commit()
        token, expires_in = create_access_token(user)
        _failures.pop(name, None)
        return {"access_token": token, "token_type": "bearer", "expires_in": expires_in, "user": user_out(user)}


@router.get("/api/auth/me")
def me(p: Principal = Depends(current_user)):
    return p.public()


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(max_length=256)


@router.post("/api/auth/change-password")
def change_password(req: PasswordChange, p: Principal = Depends(current_user)):
    _validate_password(req.new_password)
    with SessionLocal() as db:
        user = db.get(User, p.id)
        if user is None or not verify_password(req.current_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
        user.password_hash = hash_password(req.new_password)
        user.token_version += 1  # sign out other sessions
        db.commit()
        token, expires_in = create_access_token(user)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


# ------------------------------------------------------------------ users (developer)
class UserCreate(BaseModel):
    username: str
    display_name: str = ""
    password: str = Field(max_length=256)
    role: Role = "user"
    domains: list[str] = []


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: Role | None = None
    domains: list[str] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=256)  # developer reset


@router.get("/api/users")
def list_users(_: Principal = Depends(developer)):
    stats = usage_store.per_user_stats(30)
    with SessionLocal() as db:
        users = db.scalars(select(User).order_by(User.created_at)).all()
    return [user_out(u, stats.get(u.id)) for u in users]


@router.post("/api/users", status_code=201)
def create_user(req: UserCreate, _: Principal = Depends(developer)):
    if not _USERNAME.match(req.username.strip()):
        raise HTTPException(422, "Username: 3-64 characters, letters, digits, dot, dash or underscore")
    _validate_password(req.password)
    domains = _validate_domains(req.domains)
    with SessionLocal() as db:
        if db.scalar(select(User).where(func.lower(User.username) == req.username.strip().lower())):
            raise HTTPException(409, "Username already exists")
        user = User(username=req.username.strip(), display_name=req.display_name.strip(),
                    password_hash=hash_password(req.password), role=req.role, domains=domains)
        db.add(user)
        db.commit()
        return user_out(user)


@router.patch("/api/users/{user_id}")
def update_user(user_id: int, req: UserUpdate, p: Principal = Depends(developer)):
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(404, "User not found")
        losing_dev = user.role == "developer" and user.is_active and (
            (req.role is not None and req.role != "developer") or req.is_active is False)
        if losing_dev and _active_developers(db, excluding=user.id) == 0:
            raise HTTPException(409, "At least one active developer account must remain")
        if req.display_name is not None:
            user.display_name = req.display_name.strip()
        if req.role is not None:
            user.role = req.role
        if req.domains is not None:
            user.domains = _validate_domains(req.domains)
        if req.is_active is not None and req.is_active != user.is_active:
            user.is_active = req.is_active
            user.token_version += 1  # deactivation signs the user out immediately
        if req.password:
            _validate_password(req.password)
            user.password_hash = hash_password(req.password)
            user.token_version += 1
        if req.role is not None:
            user.token_version += 1  # new role takes effect at next sign-in
        db.commit()
        return user_out(user, usage_store.per_user_stats(30).get(user.id))


@router.delete("/api/users/{user_id}")
def delete_user(user_id: int, p: Principal = Depends(developer)):
    if user_id == p.id:
        raise HTTPException(409, "You cannot delete your own account")
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(404, "User not found")
        if user.role == "developer" and _active_developers(db, excluding=user.id) == 0:
            raise HTTPException(409, "At least one active developer account must remain")
        db.delete(user)
        db.commit()
    return {"deleted": user_id}


# ------------------------------------------------------------------ usage (developer)
@router.get("/api/usage/summary")
def usage_summary(days: int = 30, _: Principal = Depends(developer)):
    return usage_store.summary(max(1, min(days, 365)))


__all__ = ["router", "ROLES"]
