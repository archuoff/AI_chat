"""Common helpers of the Engismart endpoints (no HTTP routes here; the routes are in controller.py).

* envelope        ok() / fail(): the platform's {status, data, message, error}
* access          who may do what: platform token -> user -> roles and domains -> Principal; access_filters for the search
* run_endpoint    what every endpoint does, the platform's way:
                    1. read the token and the user (decode_token_and_get_user) - nothing else is read before that
                    2. check the role, read the body
                    3. run the work in a thread pool (the work is blocking: database, Qdrant, LLM)
                    4. on an error: audit log (application_logs) + the platform's 500 envelope
* small helpers   documents, domains, chat sessions, the tbl_files record of an upload

The platform logs the user in and owns accounts, groups, roles and applications; we only translate:
  engismart            the application row: without it nobody gets in
  engismart_<domain>   one application row per domain the person may ask about (e.g. engismart_adas); ids in core/domains.py
  roles (tbl_application_roles, aliases in settings ROLE_DEVELOPER / ROLE_SUPERUSER):
    none / user  chat only, only in the domains they were given; never documents marked confidential
    superuser    chat over every domain and confidential documents + Manage knowledge
    developer    everything a superuser can + token usage and plans in the answers
A normal user without any domain row is refused. Superusers and developers see every domain.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from constants.constant import CONSTANT
from controller.common.common import application_logs, decode_token_and_get_user
from controller.engismart.chat import vision
from controller.engismart.core import usage_log
from controller.engismart.core.config import get_settings
from controller.engismart.core.domains import DOMAIN_IDS, validate_domain
from controller.engismart.core.store import get_store
from controller.engismart.ingestion.ingest_graph import source_file
from middleware.authentication import _PermissionService
from models.model import models
from models.orm_models import File as FileRecord

log = logging.getLogger(__name__)
ModuleName = "engismart"


# ------------------------------------------------------------------ envelope
def ok(data, message: str = "") -> dict:
    return {"status": True, "data": data, "message": message, "error": None}


def fail(message: str, error: str | None = None, data=None) -> dict:
    return {"status": False, "data": data, "message": message, "error": error}


# ------------------------------------------------------------------ access
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


# ------------------------------------------------------------------ start-up
_ready_lock = threading.Lock()
_ready = False


def _open_store() -> None:
    try:
        get_store()
    except Exception:  # noqa: BLE001 - a problem here must never stop the platform from starting; the first request reports it
        log.exception("Engismart: could not open the search index at start-up")


def warm_up() -> None:
    """Open the search index (loads the embedding models, opens Qdrant) in the background when the router is imported, so the
    platform's start-up is not delayed and a failure only affects Engismart. A request that comes earlier simply waits for it."""
    global _ready
    with _ready_lock:
        if _ready or not get_settings().warm_up_on_start:
            return
        _ready = True
    threading.Thread(target=_open_store, name="engismart-warmup", daemon=True).start()


# ------------------------------------------------------------------ the endpoint runner
def _json(payload: dict, status_code: int = 200, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(jsonable_encoder(payload), status_code=status_code, headers=headers)


def audit(user_id: int | None, text: str) -> None:
    try:
        application_logs({"current_user": user_id, "date": datetime.now(), "module_name": ModuleName, "activity_text": text[:255]})
    except Exception:  # noqa: BLE001 - the audit log must never hide the real answer
        log.warning("could not write the audit log", exc_info=True)


async def read_body(request: Request, model: type[BaseModel] | None, form: bool):
    if form:
        return await request.form()
    if model is None:
        return None
    try:
        raw = await request.body()
        return model.model_validate(json.loads(raw) if raw else {})
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"Invalid request: the body is not valid JSON ({e.msg})") from e
    except ValidationError as e:
        first = e.errors()[0] if e.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", ()))
        raise HTTPException(422, f"Invalid request: {where + ': ' if where else ''}{first.get('msg', 'bad value')}") from e


async def run_endpoint(request: Request, work: Callable[..., Any], *, roles: tuple[str, ...] = ROLES,
                       body: type[BaseModel] | None = None, form: bool = False, what: str = "") -> Response:
    """work(p) or work(p, payload) -> data. A Response (stream, file) is returned as it is, anything else goes into the envelope."""
    user_id = None
    try:
        p = await run_in_threadpool(authenticate, request, roles)
        if isinstance(p, JSONResponse):  # bad or missing token: the platform's own answer
            return p
        user_id = p.id
        payload = await read_body(request, body, form)
        data = await run_in_threadpool(work, p) if payload is None else await run_in_threadpool(work, p, payload)
        return data if isinstance(data, Response) else _json(ok(data))
    except HTTPException as e:
        return _json(fail(str(e.detail), error=f"http_{e.status_code}"), e.status_code, e.headers)
    except Exception as e:  # noqa: BLE001 - the platform's 500 answer
        log.exception("engismart %s failed", what or request.url.path)
        await run_in_threadpool(audit, user_id, f"Exception in {what or request.url.path}: {type(e).__name__}: {e}")
        return _json(fail("Something went wrong!", error=str(e), data=[]), 500)


# ------------------------------------------------------------------ small helpers
def checked_domain(domain: str) -> str:
    try:
        return validate_domain(domain)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def parse_meta(meta: str) -> dict[str, Any]:
    try:
        value = json.loads(meta or "{}")
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"metadata is not valid JSON: {e}") from e
    if not isinstance(value, dict):
        raise HTTPException(422, "metadata must be a JSON object")
    return value


def visible_documents(p: Principal, include_superseded: bool = False, signatures: bool = False) -> list[dict]:
    docs = get_store().list_documents(include_signature=signatures)
    allowed = p.allowed_domains()
    return [d for d in docs if (p.sees_confidential or not d.get("confidential"))
            and (allowed is None or d.get("domain") in allowed)
            and (include_superseded or not d.get("superseded"))]


def doc_or_404(doc_id: str) -> dict:
    doc = get_store().get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    return doc


def source_or_409(doc: dict) -> Path:
    path = source_file(doc)
    if path is None:
        raise HTTPException(409, "The original file is not stored for this document. Re-upload it to enable preview and corrections.")
    return path


def light(d: dict) -> dict:
    return {"doc_id": d["doc_id"], "file_name": d["file_name"], "domain": d.get("domain", ""), "sig_size": d.get("sig_size")}


def checked_images(images: list[str]) -> list[str]:
    try:
        return vision.validate_images(images)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def thread_id(p: Principal, session_id: str) -> str:
    """Conversations are stored per user: nobody can open another user's session id."""
    return f"u{p.id}:{session_id}"


def public_result(p: Principal, session_id: str, res: dict) -> dict:
    out = {**res, "session_id": session_id}
    if not p.is_developer:
        out.pop("plan", None)
        out.pop("usage", None)
    return out


def record_turn(p: Principal, session_id: str, res: dict, latency_ms: int) -> None:
    usage_log.record(p.id, session_id=session_id, usage=res.get("usage"), latency_ms=latency_ms)


# ------------------------------------------------------------------ uploads
def record_upload(user_id: int, original_name: str, stored_path: Path, size_bytes: int) -> None:
    """One tbl_files row per accepted document (the platform's file list) and the audit line. Never fails the upload.
    tbl_files.file_type is a fixed list in the platform: `pdf` for PDFs, `file` for everything else; the real type stays in the name."""
    now = datetime.now()
    ext = Path(original_name).suffix.lower()
    file_type = "pdf" if ext == ".pdf" else "file"
    try:
        with models() as db:
            db.insert_record(FileRecord, {
                "datetime": now, "user_id": user_id, "filename": stored_path.name[:200], "original_filename": original_name[:255],
                "module": ModuleName, "file_type": file_type, "file_type_display_name": CONSTANT.get(file_type, "Document"),
                "file_size": round(size_bytes / 1_000_000, 4), "file_path": str(stored_path)[:255],
                "extra": str({"extension": ext}), "created_on": now,
            })
    except Exception:  # noqa: BLE001
        log.warning("could not record %s in tbl_files", original_name, exc_info=True)
    audit(user_id, f"Successfully uploaded a {ext} file: {original_name}")
