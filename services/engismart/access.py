"""Who may do what. The platform logs the user in and owns accounts, groups and roles; we only translate.

  platform token (header `access-token`)  ->  UserContext (platform middleware)  ->  Principal (ours)

Roles come from the platform's application roles for the `engismart` application (names in settings: ROLE_DEVELOPER, ...):
  user       chat only; only their allowed domains; never documents marked confidential
  superuser  chat over every document (confidential included)
  developer  everything + Manage knowledge + Users & usage
A user without any of these roles but with access to the application is a plain `user`. Allowed domains per user live in our
own table (tbl_engismart_user_access), because the platform has no such concept.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, HTTPException, status

from .config import get_settings
from .db import SessionLocal, UserAccess

APP_ALIAS = "engismart"
ROLES = ("user", "superuser", "developer")
NO_DOMAIN = "__no_access__"


@dataclass(frozen=True)
class Principal:
    id: int
    username: str
    display_name: str
    role: str
    domains: tuple[str, ...] = field(default_factory=tuple)

    @property
    def sees_confidential(self) -> bool:
        return self.role in ("superuser", "developer")

    @property
    def is_developer(self) -> bool:
        return self.role == "developer"

    def allowed_domains(self) -> list[str] | None:
        """None = every domain."""
        if self.role != "user" or not self.domains:
            return None
        return list(self.domains)

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "username": self.username, "display_name": self.display_name, "role": self.role,
                "domains": list(self.domains)}


def role_of(roles: list[str], is_admin: bool) -> str:
    """Highest of our three roles among the platform roles; a platform admin is a developer (setting)."""
    s = get_settings()
    held = set(roles or [])
    if s.role_developer in held or (is_admin and s.admin_is_developer):
        return "developer"
    if s.role_superuser in held:
        return "superuser"
    return "user"


def domains_of(user_id: int) -> tuple[str, ...]:
    with SessionLocal() as db:
        row = db.get(UserAccess, user_id)
    return tuple(row.domains or ()) if row else ()


def principal_from(ctx: Any) -> Principal:
    """`ctx` is the platform's UserContext (user_id, username, display_name, is_admin, roles)."""
    return Principal(ctx.user_id, ctx.username, ctx.display_name or ctx.username, role_of(ctx.roles, ctx.is_admin),
                     domains_of(ctx.user_id))


def current_user_dependency():
    """Dependency used by every endpoint: platform login + access to the `engismart` application -> Principal."""
    from middleware.permissions_middleware import check_access

    guard = check_access(app_alias=APP_ALIAS)

    def current_user(ctx=Depends(guard)) -> Principal:  # sync: runs in the thread pool (one small DB read)
        return principal_from(ctx)

    return current_user


current_user = current_user_dependency()


def require(*roles: str):
    def dep(p: Principal = Depends(current_user)) -> Principal:
        if p.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this area")
        return p

    return dep


def access_filters(p: Principal, requested: dict[str, Any] | None) -> dict[str, Any] | None:
    """Combine the user's chosen filters with what their role may see. Enforced in the Qdrant query."""
    f = dict(requested or {})
    allowed = p.allowed_domains()
    if allowed is not None:
        wanted = f.get("domain")
        if wanted is None:
            f["domain"] = allowed
        else:
            wanted_list = wanted if isinstance(wanted, list) else [wanted]
            f["domain"] = [d for d in wanted_list if d in allowed] or [NO_DOMAIN]
    if not p.sees_confidential:
        f["!confidential"] = True  # must_not: confidential == true
    f["!superseded"] = True  # an updated version replaced this document: chat never uses it, whoever asks
    return f or None
