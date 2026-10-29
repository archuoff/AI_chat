"""Who may do what. The platform logs the user in and owns accounts, groups, roles and applications; we only translate.

  platform token (header `access-token`)  ->  decode_token_and_get_user (controller/common/common.py)
  user id                                 ->  roles + application rows (middleware/authentication.py, _PermissionService)
                                          ->  Principal (ours)

Application rows of the platform (tbl_application) given to the person, by DevOps, in the platform's admin screens:
  engismart            the application itself: without it nobody gets in
  engismart_<domain>   one row per domain the person may ask about, e.g. engismart_adas, engismart_eds (ids in domains.py)
Roles (tbl_application_roles) for the application (aliases in settings: ROLE_DEVELOPER, ROLE_SUPERUSER):
  none / user  chat only, only in the domains they were given; never documents marked confidential
  superuser    chat over every domain and confidential documents + Manage knowledge
  developer    everything a superuser can + token usage and plans in the answers
A normal user without any domain row is refused (a person must be given a domain before using Engismart).
Superusers and developers see every domain."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from controller.common.common import decode_token_and_get_user
from middleware.authentication import _PermissionService

from .config import get_settings
from .domains import DOMAIN_IDS

APP_ALIAS = "engismart"
DOMAIN_PREFIX = "engismart_"
ROLES = ("user", "superuser", "developer")
MANAGERS = ("superuser", "developer")  # Manage knowledge
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
        return self.role in MANAGERS

    @property
    def manages_knowledge(self) -> bool:
        return self.role in MANAGERS

    @property
    def is_developer(self) -> bool:
        return self.role == "developer"

    def allowed_domains(self) -> list[str] | None:
        """None = every domain."""
        if self.role != "user":
            return None
        return list(self.domains)

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "username": self.username, "display_name": self.display_name, "role": self.role,
                "domains": list(self.domains) if self.role == "user" else sorted(DOMAIN_IDS)}


def role_of(roles: list[str], is_admin: bool) -> str:
    """Highest of our roles among the platform roles; a platform admin is a developer (setting)."""
    s = get_settings()
    held = set(roles or [])
    if s.role_developer in held or (is_admin and s.admin_is_developer):
        return "developer"
    if s.role_superuser in held:
        return "superuser"
    return "user"


def domains_of(permissions: list[dict]) -> tuple[str, ...]:
    """Domain ids from the person's application rows (engismart_<domain>); unknown ids are ignored."""
    found = {str(p.get("application_alias") or "")[len(DOMAIN_PREFIX):] for p in permissions
             if str(p.get("application_alias") or "").startswith(DOMAIN_PREFIX)}
    return tuple(d for d in sorted(found) if d in DOMAIN_IDS)


_cache: dict[int, tuple[float, Principal]] = {}
_cache_lock = threading.Lock()


def _read_principal(user_id: int, username: str) -> Principal:
    svc = _PermissionService()
    try:
        user = svc.get_user_by_username(username)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
        is_admin = str(user.is_admin).strip().lower() in ("1", "true")
        display = user.display_name or user.username
        roles, permissions = svc.fetch_roles_and_permissions(user_id)
    finally:
        svc.session.close()
    if APP_ALIAS not in {p.get("application_alias") for p in permissions}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to Engismart")
    role = role_of(roles, is_admin)
    domains = domains_of(permissions)
    if role == "user" and not domains:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No domain is assigned to you yet. Ask DevOps to give you an Engismart domain.")
    return Principal(user_id, username, display, role, domains)


def load_principal(user_id: int, username: str) -> Principal:
    """Roles and domains of a person, cached for a few seconds (ACCESS_CACHE_S): a page of thumbnails makes many calls."""
    ttl = get_settings().access_cache_s
    now = time.monotonic()
    if ttl > 0:
        with _cache_lock:
            hit = _cache.get(user_id)
        if hit and hit[0] > now:
            return hit[1]
    p = _read_principal(user_id, username)
    if ttl > 0:
        with _cache_lock:
            _cache[user_id] = (now + ttl, p)
            if len(_cache) > 2000:
                for k in [k for k, (t, _) in _cache.items() if t <= now]:
                    _cache.pop(k, None)
    return p


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def authenticate(request: Request, roles: tuple[str, ...] = ROLES) -> Principal | JSONResponse:
    """Token -> user -> Principal. A JSONResponse (platform envelope) is returned for a bad token; HTTPException for no access.
    Blocking (database): call it in a thread pool."""
    user_info = decode_token_and_get_user(request)
    if isinstance(user_info, JSONResponse):
        return user_info
    p = load_principal(user_info["user_id"], user_info["current_user"])
    if p.role not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this area")
    return p


def access_filters(p: Principal, requested: dict[str, Any] | None) -> dict[str, Any] | None:
    """Combine the user's chosen filters with what their role may see. Enforced in the Qdrant query."""
    f = dict(requested or {})
    allowed = p.allowed_domains()
    if allowed is not None:
        wanted = f.get("domain")
        if wanted is None:
            f["domain"] = allowed or [NO_DOMAIN]
        else:
            wanted_list = wanted if isinstance(wanted, list) else [wanted]
            f["domain"] = [d for d in wanted_list if d in allowed] or [NO_DOMAIN]
    if not p.sees_confidential:
        f["!confidential"] = True  # must_not: confidential == true
    f["!superseded"] = True  # an updated version replaced this document: chat never uses it, whoever asks
    return f or None
