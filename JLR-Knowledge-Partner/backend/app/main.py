"""FastAPI app.  Run:  uvicorn app.main:app --port 8000   (docs at http://localhost:8000/docs)

Access: every endpoint except /api/auth/login needs a Bearer JWT.
  user / superuser / developer -> chat (data access limited by role, see auth.deps)
  developer                    -> documents, ingestion, corrections, search, users, usage
"""
from __future__ import annotations

import json
import re
import logging
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .auth import Principal, access_filters, current_user, init_db, require
from .auth import usage as usage_store
from .auth.routes import router as auth_router
from .classify import suggest_domain
from .cli import _files
from .config import get_settings
from .domains import UNASSIGNED, domains_payload, validate_domain
from .graphs.chat_graph import config_for, delete_session, get_chat_graph, history_of, result_of, run_chat, turn_input
from .graphs.ingest_graph import refresh_images, run_ingest, source_file
from .images import catalog as image_catalog
from .images import describe as image_describe
from .ingestion import SUPPORTED_EXTENSIONS
from .ingestion.preview import build_excel_preview
from .llm import get_chat_model, get_reranker, warm_connections
from .rag import vision
from .rag.vocab import invalidate_vocabulary
from .store import get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
settings = get_settings()
developer = require("developer")
_NOT_FOUND_RE = re.compile(r"\s*I couldn.t find", re.I)  # offline + LLM wording of "not in the documents"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    store = get_store()  # loads embedding models + opens Qdrant once
    get_reranker()
    get_chat_model()
    get_chat_graph()
    yield
    store.close()


app = FastAPI(title="JLR Knowledge Partner API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=settings.top_k, ge=1, le=50)
    mode: Literal["hybrid", "dense", "keyword"] = "hybrid"
    filters: dict[str, Any] | None = Field(default=None, description='e.g. {"file_type": "xlsx", "meta.project": "EDS"}')


class FolderIngestRequest(BaseModel):
    path: str
    meta: dict[str, Any] = {}
    force: bool = False
    domain: str | None = None


class ParseOptionsUpdate(BaseModel):
    parse_options: dict[str, Any] = Field(
        description='{"sheets": {"Sheet1": {"skip": true}}, "tables": {"Sheet1!A1:H20": {"header_rows": 2, "skip": false}}}')


class DomainUpdate(BaseModel):
    domain: str


class BulkDomainUpdate(BaseModel):
    doc_ids: list[str] = Field(min_length=1, max_length=500)
    domain: str


class AccessUpdate(BaseModel):
    confidential: bool


class ImageUpdate(BaseModel):
    included: bool


class DescribeRequest(BaseModel):
    doc_ids: list[str] | None = None  # None = every document
    image_ids: list[str] | None = None


def _checked_domain(domain: str) -> str:
    try:
        return validate_domain(domain)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def _parse_meta(meta: str) -> dict[str, Any]:
    try:
        value = json.loads(meta or "{}")
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"metadata is not valid JSON: {e}") from e
    if not isinstance(value, dict):
        raise HTTPException(422, "metadata must be a JSON object")
    return value


def _visible_documents(p: Principal) -> list[dict]:
    docs = get_store().list_documents()
    allowed = p.allowed_domains()
    return [d for d in docs if (p.sees_confidential or not d.get("confidential"))
            and (allowed is None or d.get("domain") in allowed)]


@app.get("/api/health")
def health(p: Principal = Depends(current_user)):
    store = get_store()
    out = {"status": "ok", "llm": "azure-openai" if settings.llm_enabled else "offline",
           "documents": len(_visible_documents(p))}
    if p.is_developer:
        reranker = get_reranker()
        out.update({"llm_deployment": settings.azure_openai_chat_deployment if settings.llm_enabled else None,
                    "embedding": store.embedder.name, "sparse": store.sparse.name,
                    "reranker": reranker.name if reranker else None, "qdrant": store.location,
                    "supported_extensions": SUPPORTED_EXTENSIONS, "chunks": store.stats()["chunks"]})
    return out


# ------------------------------------------------------------------ documents (developer)
@app.post("/api/documents")
def upload_documents(files: list[UploadFile] = File(...), metadata: str = Form("{}"), force: bool = Form(False),
                     domain: str = Form(""), _: Principal = Depends(developer)):
    """Upload one or more files. `metadata` = JSON object of manual fields attached to every chunk;
    `domain` = engineering domain id (see GET /api/domains); empty keeps an existing file's domain."""
    meta = _parse_meta(metadata)
    domain = _checked_domain(domain) if domain else None
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for f in files:
        name = Path(f.filename or "upload").name
        if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            reports.append({"file_name": name, "status": "failed", "error": f"unsupported type; supported: {SUPPORTED_EXTENSIONS}"})
            continue
        dest = upload_dir / name
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        reports.append(run_ingest(dest, file_name=name, meta=meta, force=force, domain=domain))
    return {"results": reports, **get_store().stats()}


@app.post("/api/documents/ingest-folder")
def ingest_folder(req: FolderIngestRequest, _: Principal = Depends(developer)):
    """Ingest every supported file in a server-side folder (e.g. C:\\KG\\DATA)."""
    if not Path(req.path).exists():
        raise HTTPException(404, f"path not found: {req.path}")
    domain = _checked_domain(req.domain) if req.domain else None
    reports = [run_ingest(f, meta=req.meta, force=req.force, domain=domain) for f in _files([req.path])]
    return {"results": reports, **get_store().stats()}


def _doc_or_404(doc_id: str) -> dict:
    doc = get_store().get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    return doc


def _source_or_409(doc: dict) -> Path:
    path = source_file(doc)
    if path is None:
        raise HTTPException(409, "The original file is not stored for this document. Re-upload it to enable preview and corrections.")
    return path


@app.get("/api/documents/{doc_id}/excel-preview")
def excel_preview(doc_id: str, sheet: str | None = None, max_rows: int = 150, max_cols: int = 40,
                  _: Principal = Depends(developer)):
    doc = _doc_or_404(doc_id)
    if doc["file_type"] not in ("xlsx", "xlsm"):
        raise HTTPException(400, "Sheet preview is available for Excel files.")
    try:
        return build_excel_preview(_source_or_409(doc), doc.get("parse_options") or {}, sheet,
                                   max(10, min(max_rows, 500)), max(5, min(max_cols, 80)))
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.put("/api/documents/{doc_id}/parse-options")
def update_parse_options(doc_id: str, req: ParseOptionsUpdate, _: Principal = Depends(developer)):
    """Save corrections (header rows / skipped tables / skipped sheets) and re-process the document."""
    doc = _doc_or_404(doc_id)
    report = run_ingest(_source_or_409(doc), file_name=doc["file_name"], meta=doc.get("meta") or {},
                        domain=doc.get("domain"), parse_options=req.parse_options)
    if report["status"] == "failed":
        raise HTTPException(500, report.get("error") or "re-processing failed")
    return report


@app.post("/api/documents/{doc_id}/reprocess")
def reprocess_document(doc_id: str, _: Principal = Depends(developer)):
    doc = _doc_or_404(doc_id)
    report = run_ingest(_source_or_409(doc), file_name=doc["file_name"], meta=doc.get("meta") or {},
                        domain=doc.get("domain"), force=True)
    if report["status"] == "failed":
        raise HTTPException(500, report.get("error") or "re-processing failed")
    return report


@app.patch("/api/documents/{doc_id}/access")
def update_document_access(doc_id: str, req: AccessUpdate, _: Principal = Depends(developer)):
    """Confidential documents are only searchable by superusers and developers."""
    try:
        return get_store().set_document_confidential(doc_id, req.confidential)
    except KeyError as e:
        raise HTTPException(404, "document not found") from e


@app.patch("/api/documents/{doc_id}")
def update_document_domain(doc_id: str, req: DomainUpdate, _: Principal = Depends(developer)):
    domain = _checked_domain(req.domain)
    try:
        return get_store().set_document_domain(doc_id, domain)
    except KeyError as e:
        raise HTTPException(404, "document not found") from e


@app.post("/api/documents/bulk-domain")
def bulk_update_domain(req: BulkDomainUpdate, _: Principal = Depends(developer)):
    domain = _checked_domain(req.domain)
    updated, missing = [], []
    for doc_id in dict.fromkeys(req.doc_ids):
        try:
            get_store().set_document_domain(doc_id, domain)
            updated.append(doc_id)
        except KeyError:
            missing.append(doc_id)
    return {"domain": domain, "updated": updated, "missing": missing}


@app.post("/api/documents/{doc_id}/suggest-domain")
def suggest_document_domain(doc_id: str, p: Principal = Depends(developer)):
    usage: dict = {}
    try:
        result = suggest_domain(doc_id, usage)
    except KeyError as e:
        raise HTTPException(404, "document not found") from e
    if usage.get("llm_calls"):
        usage_store.record(p.id, kind="classify", usage=usage, mode="azure-openai")
    return result


@app.get("/api/documents")
def list_documents(_: Principal = Depends(developer)):
    pictures = image_catalog.summaries_by_document()
    return [{**d, "images": pictures.get(d["doc_id"])} for d in get_store().list_documents()]


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str, _: Principal = Depends(developer)):
    return _doc_or_404(doc_id)


@app.get("/api/documents/{doc_id}/chunks")
def get_document_chunks(doc_id: str, limit: int = 50, offset: int = 0, _: Principal = Depends(developer)):
    return get_store().get_chunks(doc_id, limit=limit, offset=offset)


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, _: Principal = Depends(developer)):
    if not get_store().delete_document(doc_id):
        raise HTTPException(404, "document not found")
    image_catalog.delete_document(doc_id)
    invalidate_vocabulary()
    return {"deleted": doc_id}


# ------------------------------------------------------------------ document pictures
@app.get("/api/images/summary")
def images_summary(_: Principal = Depends(developer)):
    """Library-wide picture counts, whether describing is switched on, the running job and a cost estimate."""
    return {"counts": image_catalog.summary(), "vision": image_describe.config(), "job": image_describe.status(),
            "estimate": image_describe.estimate(image_catalog.waiting())}


@app.get("/api/documents/{doc_id}/images")
def document_images(doc_id: str, _: Principal = Depends(developer)):
    _doc_or_404(doc_id)
    imgs = image_catalog.list_images(doc_id)
    return {"images": [image_catalog.public(i) for i in imgs], "counts": image_catalog.summary(doc_id),
            "vision": image_describe.config(), "estimate": image_describe.estimate([i for i in imgs if i.status in ("waiting", "failed")])}


@app.get("/api/images/{image_id}/file")
def image_file(image_id: str, thumb: bool = False, p: Principal = Depends(current_user)):
    """The picture itself; same access rules as the document it belongs to (domain + confidential)."""
    img = image_catalog.get_image(image_id)
    doc = get_store().get_document(img.doc_id) if img else None
    allowed = p.allowed_domains()
    if (img is None or doc is None or (doc.get("confidential") and not p.sees_confidential)
            or (allowed is not None and doc.get("domain") not in allowed)):
        raise HTTPException(404, "picture not found")
    path = image_catalog.file_path(img, thumb)
    if not path.exists():
        raise HTTPException(404, "picture file not available")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.patch("/api/images/{image_id}")
def update_image(image_id: str, req: ImageUpdate, _: Principal = Depends(developer)):
    try:
        return image_catalog.public(image_catalog.set_included(image_id, req.included))
    except KeyError as e:
        raise HTTPException(404, "picture not found") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@app.post("/api/images/describe")
def describe_images(req: DescribeRequest, p: Principal = Depends(developer)):
    try:
        return image_describe.start_job(p.id, req.doc_ids, req.image_ids)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e)) from e


@app.get("/api/images/job")
def describe_job(_: Principal = Depends(developer)):
    return image_describe.status()


@app.post("/api/images/job/cancel")
def cancel_describe_job(_: Principal = Depends(developer)):
    image_describe.cancel()
    return image_describe.status()


@app.post("/api/documents/{doc_id}/images/extract")
def extract_document_images(doc_id: str, _: Principal = Depends(developer)):
    """Extract the pictures of an already indexed document from its stored original (text is not re-embedded)."""
    _doc_or_404(doc_id)
    try:
        return refresh_images(doc_id)
    except FileNotFoundError as e:
        raise HTTPException(409, "the original file is not stored; upload it again") from e


@app.post("/api/search")
def search(req: SearchRequest, _: Principal = Depends(developer)):
    return get_store().search(req.query, req.top_k, req.filters, req.mode)


# ------------------------------------------------------------------ domains
@app.get("/api/domains")
def list_domains(p: Principal = Depends(current_user)):
    """Developers get document counts; other roles get the domains they may ask about."""
    allowed = p.allowed_domains()
    if not p.is_developer:
        return [d for d in domains_payload() if allowed is None or d["id"] in allowed]
    stats = get_store().domain_stats()
    empty = {"documents": 0, "chunks": 0}
    out = [{**d, **stats.get(d["id"], empty)} for d in domains_payload()]
    out.append({"id": UNASSIGNED, "name": "Unassigned", "description": "Documents not yet classified.",
                **stats.get(UNASSIGNED, empty)})
    return out


# ------------------------------------------------------------------ chat (every role; data limited by role)
class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    filters: dict[str, Any] | None = None
    images: list[str] = Field(default_factory=list, description="Attached images as data URLs (png/jpeg/webp/gif, max 4 x 5 MB)")


def _checked_images(req: ChatRequest) -> list[str]:
    try:
        return vision.validate_images(req.images)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def _thread(p: Principal, session_id: str) -> str:
    """Conversations are stored per user: nobody can open another user's session id."""
    return f"u{p.id}:{session_id}"


def _public_result(p: Principal, session_id: str, res: dict) -> dict:
    out = {**res, "session_id": session_id}
    if not p.is_developer:
        out.pop("plan", None)
        out.pop("usage", None)
    return out


def _record_turn(p: Principal, session_id: str, question: str, res: dict, started: float) -> None:
    try:
        usage_store.record(p.id, session_id=session_id, question=question, usage=res.get("usage"),
                           latency_ms=round((time.perf_counter() - started) * 1000), mode=res.get("mode") or "",
                           intent=res.get("intent") or "", found=not _NOT_FOUND_RE.match(res.get("answer") or ""))
    except Exception:  # noqa: BLE001 - usage accounting must never break a chat
        log.exception("could not record usage")


@app.post("/api/warmup")
def warmup(_: Principal = Depends(current_user)):
    """Called by the UI while the user types: pre-opens the Azure connections (see llm.warm_connections)."""
    return {"started": warm_connections()}


@app.post("/api/chat")
def chat(req: ChatRequest, p: Principal = Depends(current_user)):
    started = time.perf_counter()
    res = run_chat(_thread(p, req.session_id), req.message, access_filters(p, req.filters), _checked_images(req))
    _record_turn(p, req.session_id, req.message, res, started)
    return _public_result(p, req.session_id, res)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, p: Principal = Depends(current_user)):
    """Server-sent events: status / token / reset / final / error  (each line: `data: {json}`)."""
    thread = _thread(p, req.session_id)
    filters = access_filters(p, req.filters)
    images = _checked_images(req)

    def events():
        started = time.perf_counter()
        graph = get_chat_graph()
        ref = vision.hold(images)
        try:
            for mode, chunk in graph.stream(turn_input(req.message, filters, ref), config_for(thread),
                                            stream_mode=["custom", "updates"]):
                if mode == "custom":
                    yield f"data: {json.dumps(chunk)}\n\n"
            res = result_of(thread)
            _record_turn(p, req.session_id, req.message, res, started)
            yield f"data: {json.dumps({'type': 'final', **_public_result(p, req.session_id, res)}, default=str)}\n\n"
        except Exception as e:  # noqa: BLE001 - report to the client instead of dropping the stream
            log.exception("chat stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': f'{type(e).__name__}: {e}'})}\n\n"
        finally:
            vision.release(ref)  # images are used for this question only

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/chat/{session_id}/messages")
def chat_messages(session_id: str, p: Principal = Depends(current_user)):
    return history_of(_thread(p, session_id))


@app.delete("/api/chat/{session_id}")
def chat_delete(session_id: str, p: Principal = Depends(current_user)):
    delete_session(_thread(p, session_id))
    return {"deleted": session_id}
