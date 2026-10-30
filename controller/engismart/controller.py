"""Engismart endpoints: every route of the module is here. The routers are mounted by `router/router_outlet.py` at {PREFIX}engismart .

  router       every call is logged by track_module_usage  (me, health, domains, chat, documents, pictures)
  file_router  picture files: many calls per page, not logged

Each endpoint is a thin function: it calls helper.run_endpoint, which does the platform's pattern (token -> user -> role -> the work in a
thread pool -> envelope; on an error the audit log and the platform's 500 answer). The work is done by chat/ and ingestion/ (functions only).
Chat answers, Manage knowledge (documents, pictures) and the small "me / health / domains" endpoints follow in that order.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from starlette.datastructures import UploadFile

from controller.engismart.chat import vision
from controller.engismart.chat.chat_graph import (
    config_for,
    delete_session,
    get_chat_graph,
    history_of,
    result_of,
    rewind_session,
    run_chat,
    turn_input,
)
from controller.engismart.core import usage_log
from controller.engismart.core.config import get_settings
from controller.engismart.core.domains import UNASSIGNED, domains_payload
from controller.engismart.core.llm import get_reranker, warm_connections
from controller.engismart.core.store import doc_id_for, get_store
from controller.engismart.core.vocab import invalidate_vocabulary
from controller.engismart.helper import (
    MANAGERS,
    ROLES,
    Principal,
    access_filters,
    checked_domain,
    checked_images,
    doc_or_404,
    light,
    parse_meta,
    public_result,
    record_turn,
    record_upload,
    run_endpoint,
    source_or_409,
    thread_id,
    visible_documents,
)
from controller.engismart.ingestion import SUPPORTED_EXTENSIONS, parse_file, similarity, uploads
from controller.engismart.ingestion.classify import suggest_domain
from controller.engismart.ingestion.images import catalog as image_catalog
from controller.engismart.ingestion.images import describe as image_describe
from controller.engismart.ingestion.ingest_graph import rebuild_signature, refresh_images, run_ingest
from controller.engismart.ingestion.preview import build_excel_preview
from controller.engismart.validator import (
    AccessUpdate,
    BulkDomainUpdate,
    ChatRequest,
    CommitRequest,
    DescribeRequest,
    DomainUpdate,
    FolderIngestRequest,
    ImageUpdate,
    ParseOptionsUpdate,
    RewindRequest,
    SearchRequest,
    read_limited,
    validate_upload,
)

log = logging.getLogger(__name__)
router = APIRouter()
file_router = APIRouter()


# ================================================================== admin
@router.get("/me")
async def me(request: Request):
    return await run_endpoint(request, lambda p: p.public(), what="/me")


@router.get("/health")
async def health(request: Request):
    def work(p: Principal):
        s = get_settings()
        store = get_store()
        out = {"status": "ok", "llm": "azure-openai" if s.llm_enabled else "offline", "documents": len(visible_documents(p))}
        if p.is_developer:
            reranker = get_reranker()
            out.update({"llm_deployment": s.azure_openai_chat_deployment if s.llm_enabled else None,
                        "embedding": store.embedder.name, "sparse": store.sparse.name,
                        "reranker": reranker.name if reranker else None, "qdrant": store.location,
                        "supported_extensions": SUPPORTED_EXTENSIONS, "chunks": store.stats()["chunks"]})
        return out

    return await run_endpoint(request, work, what="/health")


@router.get("/domains")
async def list_domains(request: Request):
    """Superusers and developers get document counts; a normal user gets the domains they may ask about."""
    def work(p: Principal):
        allowed = p.allowed_domains()
        if not p.manages_knowledge:
            return [d for d in domains_payload() if allowed is None or d["id"] in allowed]
        stats = get_store().domain_stats()
        empty = {"documents": 0, "chunks": 0}
        out = [{**d, **stats.get(d["id"], empty)} for d in domains_payload()]
        out.append({"id": UNASSIGNED, "name": "Unassigned", "description": "Documents not yet classified.",
                    **stats.get(UNASSIGNED, empty)})
        return out

    return await run_endpoint(request, work, what="/domains")


# ================================================================== chat
def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


@router.post("/warmup")
async def warmup(request: Request):
    """Called by the UI while the user types: pre-opens the Azure connections (see llm.warm_connections)."""
    return await run_endpoint(request, lambda p: {"started": warm_connections()}, what="/warmup")


@router.post("/chat")
async def chat(request: Request):
    def work(p: Principal, req: ChatRequest):
        started = time.perf_counter()
        res = run_chat(thread_id(p, req.session_id), req.message, access_filters(p, req.filters), checked_images(req.images))
        record_turn(p, req.session_id, res, _ms(started))
        return public_result(p, req.session_id, res)

    return await run_endpoint(request, work, body=ChatRequest, what="/chat")


@router.post("/chat/stream")
async def chat_stream(request: Request):
    """Server-sent events: status / token / reset / final / error  (each line: `data: {json}`).
    Not wrapped in the JSON envelope: it is a stream. Call it with fetch() and the `access-token` header."""
    def work(p: Principal, req: ChatRequest):
        thread = thread_id(p, req.session_id)
        filters = access_filters(p, req.filters)
        images = checked_images(req.images)

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
                record_turn(p, req.session_id, res, _ms(started))
                yield f"data: {json.dumps({'type': 'final', **public_result(p, req.session_id, res)}, default=str)}\n\n"
            except Exception as e:  # noqa: BLE001 - report to the client instead of dropping the stream
                log.exception("chat stream failed")
                yield f"data: {json.dumps({'type': 'error', 'message': f'{type(e).__name__}: {e}'})}\n\n"
            finally:
                vision.release(ref)  # images are used for this question only

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return await run_endpoint(request, work, body=ChatRequest, what="/chat/stream")


@router.get("/chat/{session_id}/messages")
async def chat_messages(session_id: str, request: Request):
    return await run_endpoint(request, lambda p: history_of(thread_id(p, session_id)), what="/chat/messages")


@router.post("/chat/{session_id}/rewind")
async def chat_rewind(session_id: str, request: Request):
    """Edit and send: the conversation memory goes back to just after turn N, so the edited question is answered without the later turns."""
    def work(p: Principal, req: RewindRequest):
        return {"kept_messages": rewind_session(thread_id(p, session_id), req.turns)}

    return await run_endpoint(request, work, body=RewindRequest, what="/chat/rewind")


@router.delete("/chat/{session_id}")
async def chat_delete(session_id: str, request: Request):
    def work(p: Principal):
        delete_session(thread_id(p, session_id))
        return {"deleted": session_id}

    return await run_endpoint(request, work, what="/chat/delete")


# ================================================================== documents
def _flag(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _files_of(form, key: str) -> list[UploadFile]:
    return [f for f in form.getlist(key) if isinstance(f, UploadFile)]


def _supported_files(root: str) -> list[Path]:
    p = Path(root)
    if p.is_dir():
        return sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith("~$"))
    return [p] if p.exists() else []


@router.post("/documents")
async def upload_documents(request: Request):
    """Upload one or more files (form fields: files, metadata, force, domain). `metadata` = JSON object of manual fields attached to
    every chunk; `domain` = engineering domain id (see GET /domains); empty keeps an existing file's domain."""
    def work(p: Principal, form):
        meta = parse_meta(form.get("metadata") or "{}")
        domain = checked_domain(form.get("domain")) if form.get("domain") else None
        force = _flag(form.get("force"))
        upload_dir = Path(get_settings().upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        reports = []
        for f in _files_of(form, "files"):
            name = Path(f.filename or "upload").name
            try:
                content = read_limited(f.file, name)
                validate_upload(p.id, name, content)
            except HTTPException as e:
                reports.append({"file_name": name, "status": "failed", "error": str(e.detail)})
                continue
            dest = upload_dir / name
            dest.write_bytes(content)
            report = run_ingest(dest, file_name=name, meta=meta, force=force, domain=domain)
            if report["status"] != "failed":
                record_upload(p.id, name, dest, len(content))
            reports.append(report)
        if not reports:
            raise HTTPException(422, "No file was uploaded (form field 'files').")
        return {"results": reports, **get_store().stats()}

    return await run_endpoint(request, work, roles=MANAGERS, form=True, what="/documents")


@router.post("/documents/check")
async def check_upload(request: Request):
    """Step 1 of an upload (form fields: file, domain): keep the file, read it once and suggest similar documents (same file, similar
    name, same content, same topic). The SME then picks "new" or "update of ..." and calls /commit."""
    def work(p: Principal, form):
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise HTTPException(422, "No file was uploaded (form field 'file').")
        domain = form.get("domain") or ""
        name = Path(file.filename or "upload").name
        content = read_limited(file.file, name)
        validate_upload(p.id, name, content)
        digest, size = hashlib.sha256(content).hexdigest(), len(content)
        check_id, path = uploads.new_path(name)
        path.write_bytes(content)
        try:
            parsed = parse_file(path)
            parsed.file_name = name
        except Exception as e:  # noqa: BLE001 - tell the SME which file is the problem
            uploads.discard(check_id)
            raise HTTPException(422, f"{name} could not be read: {type(e).__name__}: {e}") from e
        store = get_store()
        topic = None
        try:
            texts = similarity.sample_texts(parsed)
            topic = similarity.mean_vector(store.embedder.embed_documents(texts)) if texts else None
        except Exception:  # noqa: BLE001 - suggestions still work from name and content
            log.warning("topic vector for %s failed", name, exc_info=True)
        sig = similarity.build_signature(parsed, topic)
        docs = visible_documents(p, include_superseded=True, signatures=True)
        found = similarity.suggest(name, digest, sig, docs, domain)
        uploads.add(uploads.Pending(check_id, p.id, name, path, digest, size, found=found), parsed)
        same_name = next((d for d in docs if d["doc_id"] == doc_id_for(name)), None)
        return {"check_id": check_id, "file_name": name, "size": sig["size"], **found,
                "same_name": light(same_name) | {"superseded": bool(same_name.get("superseded"))} if same_name else None,
                "others": sorted((light(d) for d in docs if not d.get("superseded")), key=lambda d: d["file_name"].lower())}

    return await run_endpoint(request, work, roles=MANAGERS, form=True, what="/documents/check")


@router.post("/documents/commit")
async def commit_upload(request: Request):
    """Step 2 of an upload: ingest the checked file as a new document or as an update of an existing one.
    An update hides the old version from chat (kept, can be restored); nothing is deleted."""
    def work(p: Principal, req: CommitRequest):
        item = uploads.get(req.check_id, p.id)
        if item is None:
            raise HTTPException(404, "This upload check expired. Add the file again.")
        store = get_store()
        name, new_id = item.file_name, doc_id_for(item.file_name)
        same_name = store.get_document(new_id)
        old = None
        if req.intent == "update":
            old = store.get_document(req.replaces or "")
            if old is None:
                raise HTTPException(422, "Choose the existing document this file updates.")
            if same_name and new_id != old["doc_id"]:
                raise HTTPException(409, f"A different document named '{name}' already exists. Rename the file, or update that document.")
        elif same_name:
            raise HTTPException(409, f"A document named '{name}' already exists. Choose 'Update of ...' or rename the file.")
        if not req.allow_duplicate:
            copy = next((d for d in store.list_documents() if d.get("content_hash") == item.fingerprint), None)
            if copy:
                raise HTTPException(409, f"The same file is already in the library as '{copy['file_name']}'.")
        domain = checked_domain(req.domain) if req.domain else (old.get("domain") if old and new_id != old["doc_id"] else None)
        upload_dir = Path(get_settings().upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / name
        shutil.copy2(item.path, dest)
        report = run_ingest(dest, file_name=name, meta=req.metadata, force=req.force, domain=domain, parsed=item.parsed)
        if report["status"] == "failed":
            return {"results": [report], **store.stats()}
        record_upload(p.id, name, dest, item.size_bytes)
        if old is not None and old["doc_id"] != new_id and report["status"] == "indexed":
            try:
                store.set_document_fields(new_id, {"replaces": old["doc_id"]})
                if old.get("confidential"):  # an update of a confidential document stays confidential
                    store.set_document_confidential(new_id, True)
                store.set_document_superseded(old["doc_id"], True, replaced_by=new_id, by=p.display_name)
                report["replaced"] = {"doc_id": old["doc_id"], "file_name": old["file_name"]}
            except Exception as e:  # noqa: BLE001 - the new file is indexed; say that the old one is still visible
                log.exception("could not hide the replaced document %s", old["doc_id"])
                report.setdefault("warnings", []).append(f"'{old['file_name']}' could not be hidden and is still searchable: {e}")
        invalidate_vocabulary()
        uploads.discard(item.check_id)
        return {"results": [report], **store.stats()}

    return await run_endpoint(request, work, roles=MANAGERS, body=CommitRequest, what="/documents/commit")


@router.post("/documents/{doc_id}/restore")
async def restore_document(doc_id: str, request: Request):
    """Undo an update: the replaced document is searchable again."""
    def work(p: Principal):
        doc = doc_or_404(doc_id)
        if not doc.get("superseded"):
            raise HTTPException(409, "This document was not replaced.")
        store = get_store()
        store.set_document_superseded(doc_id, False)
        newer = store.get_document(doc.get("replaced_by") or "")
        if newer and newer.get("replaces") == doc_id:
            store.set_document_fields(newer["doc_id"], {"replaces": None})
        invalidate_vocabulary()
        return {"restored": doc_id}

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/restore")


@router.post("/documents/signatures")
async def build_signatures(request: Request):
    """Build the similar-document data of documents ingested before it existed (from their stored originals)."""
    def work(p: Principal):
        done, missing = 0, []
        for d in get_store().list_documents():
            if "sig_size" in d:
                continue
            try:
                ok = rebuild_signature(d["doc_id"])
            except Exception:  # noqa: BLE001 - report which file, keep going
                log.exception("signature failed for %s", d["file_name"])
                ok = False
            done += ok
            if not ok:
                missing.append(d["file_name"])
        return {"built": done, "failed": missing}

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/signatures")


@router.post("/documents/ingest-folder")
async def ingest_folder(request: Request):
    """Ingest every supported file in a server-side folder. Developers only: it reads a path of the server, not an upload."""
    def work(p: Principal, req: FolderIngestRequest):
        if not Path(req.path).exists():
            raise HTTPException(404, f"path not found: {req.path}")
        domain = checked_domain(req.domain) if req.domain else None
        reports = [run_ingest(f, meta=req.meta, force=req.force, domain=domain) for f in _supported_files(req.path)]
        return {"results": reports, **get_store().stats()}

    return await run_endpoint(request, work, roles=("developer",), body=FolderIngestRequest, what="/documents/ingest-folder")


@router.get("/documents/{doc_id}/excel-preview")
async def excel_preview(doc_id: str, request: Request, sheet: str | None = None, max_rows: int = 150, max_cols: int = 40):
    def work(p: Principal):
        doc = doc_or_404(doc_id)
        if doc["file_type"] not in ("xlsx", "xlsm"):
            raise HTTPException(400, "Sheet preview is available for Excel files.")
        try:
            return build_excel_preview(source_or_409(doc), doc.get("parse_options") or {}, sheet,
                                       max(10, min(max_rows, 500)), max(5, min(max_cols, 80)), doc_id=doc_id)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/excel-preview")


@router.put("/documents/{doc_id}/parse-options")
async def update_parse_options(doc_id: str, request: Request):
    """Save corrections (header rows / skipped tables / skipped sheets) and re-process the document."""
    def work(p: Principal, req: ParseOptionsUpdate):
        doc = doc_or_404(doc_id)
        report = run_ingest(source_or_409(doc), file_name=doc["file_name"], meta=doc.get("meta") or {},
                            domain=doc.get("domain"), parse_options=req.parse_options)
        if report["status"] == "failed":
            raise HTTPException(500, report.get("error") or "re-processing failed")
        return report

    return await run_endpoint(request, work, roles=MANAGERS, body=ParseOptionsUpdate, what="/documents/parse-options")


@router.post("/documents/{doc_id}/reprocess")
async def reprocess_document(doc_id: str, request: Request):
    def work(p: Principal):
        doc = doc_or_404(doc_id)
        report = run_ingest(source_or_409(doc), file_name=doc["file_name"], meta=doc.get("meta") or {},
                            domain=doc.get("domain"), force=True)
        if report["status"] == "failed":
            raise HTTPException(500, report.get("error") or "re-processing failed")
        return report

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/reprocess")


@router.patch("/documents/{doc_id}/access")
async def update_document_access(doc_id: str, request: Request):
    """Confidential documents are only searchable by superusers and developers."""
    def work(p: Principal, req: AccessUpdate):
        try:
            return get_store().set_document_confidential(doc_id, req.confidential)
        except KeyError as e:
            raise HTTPException(404, "document not found") from e

    return await run_endpoint(request, work, roles=MANAGERS, body=AccessUpdate, what="/documents/access")


@router.patch("/documents/{doc_id}")
async def update_document_domain(doc_id: str, request: Request):
    def work(p: Principal, req: DomainUpdate):
        domain = checked_domain(req.domain)
        try:
            return get_store().set_document_domain(doc_id, domain)
        except KeyError as e:
            raise HTTPException(404, "document not found") from e

    return await run_endpoint(request, work, roles=MANAGERS, body=DomainUpdate, what="/documents/domain")


@router.post("/documents/bulk-domain")
async def bulk_update_domain(request: Request):
    def work(p: Principal, req: BulkDomainUpdate):
        domain = checked_domain(req.domain)
        updated, missing = [], []
        for doc_id in dict.fromkeys(req.doc_ids):
            try:
                get_store().set_document_domain(doc_id, domain)
                updated.append(doc_id)
            except KeyError:
                missing.append(doc_id)
        return {"domain": domain, "updated": updated, "missing": missing}

    return await run_endpoint(request, work, roles=MANAGERS, body=BulkDomainUpdate, what="/documents/bulk-domain")


@router.post("/documents/{doc_id}/suggest-domain")
async def suggest_document_domain(doc_id: str, request: Request):
    def work(p: Principal):
        usage: dict = {}
        try:
            result = suggest_domain(doc_id, usage)
        except KeyError as e:
            raise HTTPException(404, "document not found") from e
        if usage.get("llm_calls"):
            usage_log.record(p.id, kind="classify", usage=usage)
        return result

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/suggest-domain")


@router.get("/documents")
async def list_documents(request: Request):
    def work(p: Principal):
        pictures = image_catalog.summaries_by_document()
        return [{**d, "images": pictures.get(d["doc_id"]), "compared": "sig_size" in d} for d in get_store().list_documents()]

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents")


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, request: Request):
    return await run_endpoint(request, lambda p: {k: v for k, v in doc_or_404(doc_id).items() if k != "signature"},
                              roles=MANAGERS, what="/documents/get")


@router.get("/documents/{doc_id}/chunks")
async def get_document_chunks(doc_id: str, request: Request, limit: int = 50, offset: int = 0):
    return await run_endpoint(request, lambda p: get_store().get_chunks(doc_id, limit=limit, offset=offset),
                              roles=MANAGERS, what="/documents/chunks")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request):
    def work(p: Principal):
        store = get_store()
        doc = store.get_document(doc_id) or {}
        if not store.delete_document(doc_id):
            raise HTTPException(404, "document not found")
        older = store.get_document(doc.get("replaces") or "")
        if older and older.get("superseded") and older.get("replaced_by") == doc_id:  # deleting the update brings the old version back
            store.set_document_superseded(older["doc_id"], False)
        image_catalog.delete_document(doc_id)
        invalidate_vocabulary()
        return {"deleted": doc_id}

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/delete")


@router.post("/search")
async def search(request: Request):
    return await run_endpoint(request, lambda p, req: get_store().search(req.query, req.top_k, req.filters, req.mode),
                              roles=MANAGERS, body=SearchRequest, what="/search")


# ================================================================== pictures
@router.get("/images/summary")
async def images_summary(request: Request):
    """Library-wide picture counts, whether describing is switched on, the running job and a cost estimate."""
    def work(p: Principal):
        return {"counts": image_catalog.summary(), "vision": image_describe.config(), "job": image_describe.status(),
                "estimate": image_describe.estimate(image_catalog.waiting())}

    return await run_endpoint(request, work, roles=MANAGERS, what="/images/summary")


@router.get("/documents/{doc_id}/images")
async def document_images(doc_id: str, request: Request):
    def work(p: Principal):
        doc_or_404(doc_id)
        imgs = image_catalog.list_images(doc_id)
        return {"images": [image_catalog.public(i) for i in imgs], "counts": image_catalog.summary(doc_id),
                "vision": image_describe.config(),
                "estimate": image_describe.estimate([i for i in imgs if i.status in ("waiting", "failed")])}

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/images")


@file_router.get("/images/{image_id}/file")
async def image_file(image_id: str, request: Request, thumb: bool = False):
    """The picture itself; same access rules as the document it belongs to (domain + confidential)."""
    def work(p: Principal):
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

    return await run_endpoint(request, work, roles=ROLES, what="/images/file")


@router.patch("/images/{image_id}")
async def update_image(image_id: str, request: Request):
    def work(p: Principal, req: ImageUpdate):
        try:
            return image_catalog.public(image_catalog.set_included(image_id, req.included))
        except KeyError as e:
            raise HTTPException(404, "picture not found") from e
        except ValueError as e:
            raise HTTPException(409, str(e)) from e

    return await run_endpoint(request, work, roles=MANAGERS, body=ImageUpdate, what="/images/update")


@router.post("/images/describe")
async def describe_images(request: Request):
    def work(p: Principal, req: DescribeRequest):
        try:
            return image_describe.start_job(p.id, req.doc_ids, req.image_ids)
        except (RuntimeError, ValueError) as e:
            raise HTTPException(409, str(e)) from e

    return await run_endpoint(request, work, roles=MANAGERS, body=DescribeRequest, what="/images/describe")


@router.get("/images/job")
async def describe_job(request: Request):
    return await run_endpoint(request, lambda p: image_describe.status(), roles=MANAGERS, what="/images/job")


@router.post("/images/job/cancel")
async def cancel_describe_job(request: Request):
    def work(p: Principal):
        image_describe.cancel()
        return image_describe.status()

    return await run_endpoint(request, work, roles=MANAGERS, what="/images/job/cancel")


@router.post("/documents/{doc_id}/images/extract")
async def extract_document_images(doc_id: str, request: Request):
    """Extract the pictures of an already indexed document from its stored original (text is not re-embedded)."""
    def work(p: Principal):
        doc_or_404(doc_id)
        try:
            return refresh_images(doc_id)
        except FileNotFoundError as e:
            raise HTTPException(409, "the original file is not stored; upload it again") from e

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/images/extract")
