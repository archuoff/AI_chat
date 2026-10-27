"""Documents: upload (check -> commit), library, corrections, access, domains, search. Developer role."""
from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from controller.engismart.envelope import EnvelopeRoute
from controller.engismart.helper import (
    checked_domain,
    doc_or_404,
    light,
    log_decision,
    parse_meta,
    source_or_409,
    visible_documents,
)
from controller.engismart.validator import (
    AccessUpdate,
    BulkDomainUpdate,
    CommitRequest,
    DomainUpdate,
    FolderIngestRequest,
    ParseOptionsUpdate,
    SearchRequest,
)
from services.engismart import uploads
from services.engismart import usage as usage_store
from services.engismart.access import Principal, require
from services.engismart.classify import suggest_domain
from services.engismart.config import get_settings
from services.engismart.graphs.ingest_graph import rebuild_signature, run_ingest
from services.engismart.images import catalog as image_catalog
from services.engismart.ingestion import SUPPORTED_EXTENSIONS, parse_file, similarity
from services.engismart.ingestion.preview import build_excel_preview
from services.engismart.rag.vocab import invalidate_vocabulary
from services.engismart.store import doc_id_for, get_store

log = logging.getLogger(__name__)
router = APIRouter(route_class=EnvelopeRoute)
developer = require("developer")


def _supported_files(root: str) -> list[Path]:
    p = Path(root)
    if p.is_dir():
        return sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith("~$"))
    return [p] if p.exists() else []


@router.post("/documents")
def upload_documents(files: list[UploadFile] = File(...), metadata: str = Form("{}"), force: bool = Form(False),
                     domain: str = Form(""), _: Principal = Depends(developer)):
    """Upload one or more files. `metadata` = JSON object of manual fields attached to every chunk;
    `domain` = engineering domain id (see GET /domains); empty keeps an existing file's domain."""
    meta = parse_meta(metadata)
    domain = checked_domain(domain) if domain else None
    upload_dir = Path(get_settings().upload_dir)
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


@router.post("/documents/check")
def check_upload(file: UploadFile = File(...), domain: str = Form(""), p: Principal = Depends(developer)):
    """Step 1 of an upload: keep the file, read it once and suggest similar documents (same file, similar name,
    same content, same topic). The SME then picks "new" or "update of ..." and calls /commit."""
    name = Path(file.filename or "upload").name
    if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, f"unsupported type; supported: {SUPPORTED_EXTENSIONS}")
    check_id, path = uploads.new_path(name)
    digest, size = hashlib.sha256(), 0
    with path.open("wb") as out:
        while block := file.file.read(1 << 20):
            out.write(block)
            digest.update(block)
            size += len(block)
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
    found = similarity.suggest(name, digest.hexdigest(), sig, docs, domain)
    uploads.add(uploads.Pending(check_id, p.id, name, path, digest.hexdigest(), size, found=found), parsed)
    same_name = next((d for d in docs if d["doc_id"] == doc_id_for(name)), None)
    return {"check_id": check_id, "file_name": name, "size": sig["size"], **found,
            "same_name": light(same_name) | {"superseded": bool(same_name.get("superseded"))} if same_name else None,
            "others": sorted((light(d) for d in docs if not d.get("superseded")), key=lambda d: d["file_name"].lower())}


@router.post("/documents/commit")
def commit_upload(req: CommitRequest, p: Principal = Depends(developer)):
    """Step 2 of an upload: ingest the checked file as a new document or as an update of an existing one.
    An update hides the old version from chat (kept, can be restored); nothing is deleted."""
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
        log_decision(p, item, req, report)
        return {"results": [report], **store.stats()}
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
    log_decision(p, item, req, report)
    uploads.discard(item.check_id)
    return {"results": [report], **store.stats()}


@router.post("/documents/{doc_id}/restore")
def restore_document(doc_id: str, _: Principal = Depends(developer)):
    """Undo an update: the replaced document is searchable again."""
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


@router.post("/documents/signatures")
def build_signatures(_: Principal = Depends(developer)):
    """Build the similar-document data of documents ingested before it existed (from their stored originals)."""
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


@router.post("/documents/ingest-folder")
def ingest_folder(req: FolderIngestRequest, _: Principal = Depends(developer)):
    """Ingest every supported file in a server-side folder."""
    if not Path(req.path).exists():
        raise HTTPException(404, f"path not found: {req.path}")
    domain = checked_domain(req.domain) if req.domain else None
    reports = [run_ingest(f, meta=req.meta, force=req.force, domain=domain) for f in _supported_files(req.path)]
    return {"results": reports, **get_store().stats()}


@router.get("/documents/{doc_id}/excel-preview")
def excel_preview(doc_id: str, sheet: str | None = None, max_rows: int = 150, max_cols: int = 40,
                  _: Principal = Depends(developer)):
    doc = doc_or_404(doc_id)
    if doc["file_type"] not in ("xlsx", "xlsm"):
        raise HTTPException(400, "Sheet preview is available for Excel files.")
    try:
        return build_excel_preview(source_or_409(doc), doc.get("parse_options") or {}, sheet,
                                   max(10, min(max_rows, 500)), max(5, min(max_cols, 80)), doc_id=doc_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.put("/documents/{doc_id}/parse-options")
def update_parse_options(doc_id: str, req: ParseOptionsUpdate, _: Principal = Depends(developer)):
    """Save corrections (header rows / skipped tables / skipped sheets) and re-process the document."""
    doc = doc_or_404(doc_id)
    report = run_ingest(source_or_409(doc), file_name=doc["file_name"], meta=doc.get("meta") or {},
                        domain=doc.get("domain"), parse_options=req.parse_options)
    if report["status"] == "failed":
        raise HTTPException(500, report.get("error") or "re-processing failed")
    return report


@router.post("/documents/{doc_id}/reprocess")
def reprocess_document(doc_id: str, _: Principal = Depends(developer)):
    doc = doc_or_404(doc_id)
    report = run_ingest(source_or_409(doc), file_name=doc["file_name"], meta=doc.get("meta") or {},
                        domain=doc.get("domain"), force=True)
    if report["status"] == "failed":
        raise HTTPException(500, report.get("error") or "re-processing failed")
    return report


@router.patch("/documents/{doc_id}/access")
def update_document_access(doc_id: str, req: AccessUpdate, _: Principal = Depends(developer)):
    """Confidential documents are only searchable by superusers and developers."""
    try:
        return get_store().set_document_confidential(doc_id, req.confidential)
    except KeyError as e:
        raise HTTPException(404, "document not found") from e


@router.patch("/documents/{doc_id}")
def update_document_domain(doc_id: str, req: DomainUpdate, _: Principal = Depends(developer)):
    domain = checked_domain(req.domain)
    try:
        return get_store().set_document_domain(doc_id, domain)
    except KeyError as e:
        raise HTTPException(404, "document not found") from e


@router.post("/documents/bulk-domain")
def bulk_update_domain(req: BulkDomainUpdate, _: Principal = Depends(developer)):
    domain = checked_domain(req.domain)
    updated, missing = [], []
    for doc_id in dict.fromkeys(req.doc_ids):
        try:
            get_store().set_document_domain(doc_id, domain)
            updated.append(doc_id)
        except KeyError:
            missing.append(doc_id)
    return {"domain": domain, "updated": updated, "missing": missing}


@router.post("/documents/{doc_id}/suggest-domain")
def suggest_document_domain(doc_id: str, p: Principal = Depends(developer)):
    usage: dict = {}
    try:
        result = suggest_domain(doc_id, usage)
    except KeyError as e:
        raise HTTPException(404, "document not found") from e
    if usage.get("llm_calls"):
        usage_store.record(p.id, kind="classify", usage=usage, mode="azure-openai")
    return result


@router.get("/documents")
def list_documents(_: Principal = Depends(developer)):
    pictures = image_catalog.summaries_by_document()
    return [{**d, "images": pictures.get(d["doc_id"]), "compared": "sig_size" in d} for d in get_store().list_documents()]


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, _: Principal = Depends(developer)):
    return {k: v for k, v in doc_or_404(doc_id).items() if k != "signature"}


@router.get("/documents/{doc_id}/chunks")
def get_document_chunks(doc_id: str, limit: int = 50, offset: int = 0, _: Principal = Depends(developer)):
    return get_store().get_chunks(doc_id, limit=limit, offset=offset)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, _: Principal = Depends(developer)):
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


@router.post("/search")
def search(req: SearchRequest, _: Principal = Depends(developer)):
    return get_store().search(req.query, req.top_k, req.filters, req.mode)
