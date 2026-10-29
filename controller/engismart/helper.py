"""Shared helpers of the Engismart endpoints (no HTTP routes here).

`run_endpoint` is the one place where every endpoint does what the platform's modules do by hand:
  1. read the token and the user (decode_token_and_get_user) - nothing else is read before that
  2. check the role, read the body
  3. run the work in a thread pool (the work is blocking: database, Qdrant, LLM)
  4. on an error: audit log (application_logs) + the platform's 500 envelope
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from controller.common.common import application_logs
from controller.engismart import usage_log
from controller.engismart.access import ROLES, Principal, authenticate
from controller.engismart.config import get_settings
from controller.engismart.domains import validate_domain
from controller.engismart.envelope import fail, ok
from controller.engismart.graphs.ingest_graph import source_file
from controller.engismart.rag import vision
from controller.engismart.store import get_store

log = logging.getLogger(__name__)
ModuleName = "engismart"


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


def _audit(user_id: int | None, text: str) -> None:
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
        await run_in_threadpool(_audit, user_id, f"Exception in {what or request.url.path}: {type(e).__name__}: {e}")
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
