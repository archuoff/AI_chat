"""LangGraph ingestion pipeline.

    fingerprint ──(unchanged & not forced)──► END  (status=skipped)
         │
         ▼
       parse ──► chunk ──► index ──► images ──► END  (status=indexed)

`images` stores the document's pictures (waiting for a vision model) and restores the search chunks of
pictures described earlier, so re-processing never loses or re-pays for descriptions.

Future nodes (knowledge-graph extraction with Azure OpenAI, entity linking) slot in between
`chunk` and `index` without changing the API.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ..config import get_settings
from ..domains import UNASSIGNED, validate_domain
from ..images import catalog
from ..ingestion import ParsedDocument, parse_file
from ..ingestion.chunker import Chunk, build_chunks
from ..rag.vocab import invalidate_vocabulary
from ..store import doc_id_for, get_store

log = logging.getLogger(__name__)


class IngestState(TypedDict, total=False):
    file_path: str
    file_name: str
    meta: dict[str, Any]
    domain: str
    parse_options: dict[str, Any]
    confidential: bool
    force: bool
    doc_id: str
    content_hash: str
    size_bytes: int
    status: str
    parsed: ParsedDocument
    chunks: list[Chunk]
    report: dict[str, Any]


def fingerprint(state: IngestState) -> IngestState:
    path = Path(state["file_path"])
    data = path.read_bytes()
    file_name = state.get("file_name") or path.name
    doc_id = doc_id_for(file_name)
    content_hash = hashlib.sha256(data).hexdigest()
    store = get_store()
    existing = store.get_document(doc_id) or {}
    # None = "keep what the document already has" (re-upload must not reset a classification or fixes)
    domain = state.get("domain") or existing.get("domain") or UNASSIGNED
    options = state.get("parse_options")
    options = existing.get("parse_options") or {} if options is None else options
    unchanged = (bool(existing) and existing.get("content_hash") == content_hash
                 and existing.get("meta") == state.get("meta", {})
                 and (existing.get("parse_options") or {}) == options)
    out: IngestState = {"file_name": file_name, "doc_id": doc_id, "content_hash": content_hash, "size_bytes": len(data),
                        "domain": domain, "parse_options": options, "confidential": bool(existing.get("confidential", False))}
    if unchanged and not state.get("force"):
        if existing.get("domain") != domain:  # same content, new classification: relabel in place
            doc = store.set_document_domain(doc_id, domain)
            return {**out, "status": "reclassified", "report": {**doc, "reason": f"unchanged content, moved to '{domain}'"}}
        return {**out, "status": "skipped"}
    return {**out, "status": "pending"}


def parse(state: IngestState) -> IngestState:
    parsed = parse_file(state["file_path"], state.get("parse_options") or {})
    parsed.file_name = state["file_name"]
    return {"parsed": parsed}


def chunk(state: IngestState) -> IngestState:
    s = get_settings()
    return {"chunks": build_chunks(state["doc_id"], state["parsed"], s.chunk_size, s.chunk_overlap)}


def index(state: IngestState) -> IngestState:
    parsed = state["parsed"]
    doc = {
        "doc_id": state["doc_id"],
        "file_name": state["file_name"],
        "file_type": parsed.file_type,
        "content_hash": state["content_hash"],
        "size_bytes": state["size_bytes"],
        "records": sum(e.kind == "record" for e in parsed.elements),
        "text_blocks": sum(e.kind == "text" for e in parsed.elements),
        "stats": parsed.stats,
        "warnings": parsed.warnings,
        "domain": state["domain"],
        "confidential": bool(state.get("confidential", False)),
        "parse_options": state.get("parse_options") or {},
        "source_path": str(keep_source_copy(state["file_path"], state["doc_id"], state["file_name"])),
        "embedding_model": get_store().embedder.name,
    }
    n = get_store().index_document(doc, state["chunks"], state.get("meta", {}))
    invalidate_vocabulary()
    return {"status": "indexed", "report": {**doc, "chunks": n}}


def images(state: IngestState) -> IngestState:
    report = dict(state["report"])
    try:
        report["images"] = catalog.sync(state["doc_id"], state["parsed"].images)
        report["chunks"] += catalog.index_described(state["doc_id"])
    except Exception as e:  # noqa: BLE001 - pictures are extra: the text is already indexed
        log.exception("Picture extraction failed for %s", state["file_name"])
        report.setdefault("warnings", []).append(f"Pictures could not be extracted: {type(e).__name__}: {e}")
    return {"report": report}


def refresh_images(doc_id: str) -> dict[str, int]:
    """Extract the pictures of an already indexed document from its stored original (no re-embedding of text)."""
    doc = get_store().get_document(doc_id)
    path = source_file(doc) if doc else None
    if path is None:
        raise FileNotFoundError(doc_id)
    parsed = parse_file(path, doc.get("parse_options") or {})
    out = catalog.sync(doc_id, parsed.images)
    catalog.index_described(doc_id)
    return out


def source_dir(doc_id: str) -> Path:
    return Path(get_settings().upload_dir).parent / "sources" / doc_id


def source_file(doc: dict) -> Path | None:
    """The stored original of a document. The registry keeps an absolute path; after moving the install to
    another folder or PC that path is stale, so fall back to data/sources/<doc_id>/ under the current install."""
    stored = Path(doc.get("source_path") or "")
    if doc.get("source_path") and stored.is_file():
        return stored
    folder = source_dir(doc["doc_id"])
    local = folder / doc.get("file_name", "")
    if local.is_file():
        return local
    files = [f for f in folder.glob("*") if f.is_file()] if folder.is_dir() else []
    return files[0] if len(files) == 1 else None


def keep_source_copy(file_path: str, doc_id: str, file_name: str) -> Path:
    """Keep the exact ingested file so previews / re-processing always use the same bytes."""
    src = Path(file_path)
    folder = source_dir(doc_id)
    dest = folder / file_name
    if src.resolve() != dest.resolve():
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.iterdir():  # one file per document
            if old.name != file_name:
                old.unlink()
        shutil.copy2(src, dest)
    return dest


def _route_after_fingerprint(state: IngestState) -> str:
    return "parse" if state["status"] == "pending" else END


def build_ingest_graph():
    g = StateGraph(IngestState)
    g.add_node("fingerprint", fingerprint)
    g.add_node("parse", parse)
    g.add_node("chunk", chunk)
    g.add_node("index", index)
    g.add_node("images", images)
    g.add_edge(START, "fingerprint")
    g.add_conditional_edges("fingerprint", _route_after_fingerprint, ["parse", END])
    g.add_edge("parse", "chunk")
    g.add_edge("chunk", "index")
    g.add_edge("index", "images")
    g.add_edge("images", END)
    return g.compile()


_graph = None


def run_ingest(file_path: str | Path, file_name: str | None = None, meta: dict[str, Any] | None = None,
               force: bool = False, domain: str | None = None, parse_options: dict | None = None) -> dict[str, Any]:
    """Run the pipeline for one file and return a report (never raises)."""
    global _graph
    if _graph is None:
        _graph = build_ingest_graph()
    started = time.perf_counter()
    name = file_name or Path(file_path).name
    try:
        domain = validate_domain(domain) if domain else None
        out = _graph.invoke({"file_path": str(file_path), "file_name": name, "meta": meta or {}, "force": force,
                             "domain": domain, "parse_options": parse_options})
        report = out.get("report") or {"doc_id": out["doc_id"], "file_name": name, "reason": "unchanged (use force to re-ingest)"}
        report["status"] = out["status"]
    except Exception as e:  # noqa: BLE001 - report every failure back to the caller
        log.exception("Ingestion failed for %s", name)
        report = {"file_name": name, "status": "failed", "error": f"{type(e).__name__}: {e}"}
    report["seconds"] = round(time.perf_counter() - started, 2)
    return report
