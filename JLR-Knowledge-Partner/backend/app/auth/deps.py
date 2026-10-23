"""Request authentication (Bearer JWT) and role / data-access rules.

Roles
  user       chat only; only their allowed domains; never documents marked confidential
  superuser  chat over every document (confidential included)
  developer  everything + Manage knowledge + Users & usage
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import SessionLocal, User
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)
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


def _unauthorized(detail: str = "Not signed in") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        claims = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError as e:
        raise _unauthorized("Session expired, please sign in again") from e
    except jwt.PyJWTError as e:
        raise _unauthorized("Invalid token") from e
    with SessionLocal() as db:
        user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active or user.token_version != claims.get("ver", -1):
        raise _unauthorized("Account disabled or token revoked")
    return Principal(user.id, user.username, user.display_name or user.username, user.role, tuple(user.domains or ()))


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
