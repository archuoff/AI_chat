"""Who a platform user is. Read-only view of the platform's tables (tbl_users and the application roles)."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _service():
    try:
        from middleware.permissions_middleware import _PermissionService
        from models.orm_models import User
    except ImportError:  # running outside the platform project
        return None, None
    return _PermissionService(), User


def _row(svc, u) -> dict:
    try:
        roles, _ = svc.fetch_roles_and_permissions(u.id)
    except Exception:  # noqa: BLE001 - a role lookup problem must not hide the user
        log.warning("could not read roles of user %s", u.id, exc_info=True)
        roles = []
    return {"id": u.id, "username": u.username, "display_name": u.display_name or u.username,
            "is_admin": str(u.is_admin).strip().lower() in ("1", "true"), "is_active": str(u.status).strip() == "1", "roles": roles}


def describe_users(ids: list[int]) -> dict[int, dict]:
    """{user_id: {username, display_name, is_admin, is_active, roles}}; empty when the platform tables are not there."""
    svc, User = _service()
    if svc is None or not ids:
        return {}
    try:
        return {u.id: _row(svc, u) for u in svc.session.query(User).filter(User.id.in_(ids)).all()}
    except Exception:  # noqa: BLE001 - names are decoration: never fail a page because of them
        log.warning("could not read users", exc_info=True)
        return {}
    finally:
        svc.session.close()


def search_users(q: str, limit: int = 20) -> list[dict]:
    """Active platform users whose username or display name contains `q` (to give them a domain setting)."""
    svc, User = _service()
    if svc is None or not q.strip():
        return []
    like = f"%{q.strip()}%"
    try:
        rows = (svc.session.query(User).filter(User.is_deleted == 0, User.status == 1)
                .filter(User.username.ilike(like) | User.display_name.ilike(like)).order_by(User.username).limit(limit).all())
        return [_row(svc, u) for u in rows]
    except Exception:  # noqa: BLE001
        log.warning("user search failed", exc_info=True)
        return []
    finally:
        svc.session.close()


def user_names(ids: list[int]) -> dict[int, dict]:
    return {i: {"username": d["username"], "display_name": d["display_name"]} for i, d in describe_users(ids).items()}
