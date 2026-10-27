"""Shared helpers of the Engismart endpoints (no HTTP routes here)."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from services.engismart import usage as usage_store
from services.engismart.access import Principal
from services.engismart.db import SessionLocal, UploadDecision, init_db
from services.engismart.domains import validate_domain
from services.engismart.graphs.ingest_graph import source_file
from services.engismart.rag import vision
from services.engismart.store import get_store

log = logging.getLogger(__name__)
_ready_lock = threading.Lock()
_ready = False


def ensure_ready() -> None:
    """Router dependency: opens the database and the search index once (first request after start-up pays the cost)."""
    global _ready
    if _ready:
        return
    with _ready_lock:
        if not _ready:
            init_db()
            get_store()  # loads the embedding models and opens Qdrant
            _ready = True


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


def log_decision(p: Principal, item, req, report: dict) -> None:
    try:
        with SessionLocal() as db:
            db.add(UploadDecision(user_id=p.id, check_id=item.check_id[:64], file_name=item.file_name[:255], domain=req.domain[:64],
                                  intent=req.intent, replaces=(req.replaces or "")[:64], exact=item.found.get("exact", []),
                                  suggestions=[{"doc_id": s["doc_id"], "label": s["label"], "scores": s["scores"]}
                                               for s in item.found.get("suggestions", [])],
                                  result_status=report.get("status", "")[:16]))
            db.commit()
    except Exception:  # noqa: BLE001 - the log must never fail an upload
        log.warning("could not log the upload decision", exc_info=True)


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


def record_turn(p: Principal, session_id: str, question: str, res: dict, started: float, found: bool) -> None:
    try:
        usage_store.record(p.id, session_id=session_id, question=question, usage=res.get("usage"),
                           latency_ms=round((time.perf_counter() - started) * 1000), mode=res.get("mode") or "",
                           intent=res.get("intent") or "", found=found)
    except Exception:  # noqa: BLE001 - usage accounting must never break a chat
        log.exception("could not record usage")
