"""Qdrant storage.

Collections
  <prefix>_chunks     dense (semantic) + sparse BM25 (keyword) vectors, payload = chunk + exact table values
  <prefix>_documents  no vectors, one point per ingested file (registry: hash, stats, user metadata)
"""
from __future__ import annotations

import logging
import math
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient, models

from .config import get_settings
from .domains import UNASSIGNED, validate_domain
from .ingestion.chunker import Chunk
from .llm import AzureEmbedder, get_embedder, get_sparse_embedder

log = logging.getLogger(__name__)
_DOC_NS = uuid.UUID("0b8e2f7e-3c55-4a8e-8f0e-6a0b3c1d2e4f")
DENSE, SPARSE = "dense", "bm25"
EMBED_BATCH = 64


def doc_id_for(file_name: str) -> str:
    """Stable id per file name: re-ingesting an updated file replaces the old version."""
    return str(uuid.uuid5(_DOC_NS, file_name.strip().lower()))


def _filter(filters: dict[str, Any] | None) -> models.Filter | None:
    if not filters:
        return None
    must, must_not = [], []
    for key, value in filters.items():
        if value is None or value == "" or value == []:
            continue
        target = must
        if key.startswith("!"):  # "!field": value -> must_not (e.g. exclude confidential documents)
            key, target = key[1:], must_not
        if isinstance(value, dict):  # {"gte": 3, "lte": 5}
            target.append(models.FieldCondition(key=key, range=models.Range(**value)))
            continue
        match = models.MatchAny(any=value) if isinstance(value, list) else models.MatchValue(value=value)
        target.append(models.FieldCondition(key=key, match=match))
    return models.Filter(must=must or None, must_not=must_not or None) if (must or must_not) else None


class KGStore:
    def __init__(self):
        s = get_settings()
        self.settings = s
        self.client = QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key or None) if s.qdrant_url else QdrantClient(path=s.qdrant_path)
        self.location = s.qdrant_url or s.qdrant_path
        self.embedder = get_embedder()
        self.sparse = get_sparse_embedder()
        self._lock = threading.RLock()
        self._qcache: OrderedDict[str, tuple] = OrderedDict()
        self._ensure_collections()

    # ------------------------------------------------------------------ setup
    def _ensure_collections(self):
        s = self.settings
        with self._lock:
            if self.client.collection_exists(s.chunks_collection):
                size = self.client.get_collection(s.chunks_collection).config.params.vectors[DENSE].size
                if size != self.embedder.dim:
                    raise RuntimeError(
                        f"Collection '{s.chunks_collection}' has vector size {size} but embedder '{self.embedder.name}' "
                        f"produces {self.embedder.dim}. Set a new COLLECTION_PREFIX and re-ingest.")
            else:
                self.client.create_collection(
                    s.chunks_collection,
                    vectors_config={DENSE: models.VectorParams(size=self.embedder.dim, distance=models.Distance.COSINE)},
                    sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
                )
                if s.qdrant_url:  # payload indexes only matter on a real server
                    for key in ("doc_id", "file_type", "kind", "domain"):
                        self.client.create_payload_index(s.chunks_collection, key, models.PayloadSchemaType.KEYWORD)
                    self.client.create_payload_index(s.chunks_collection, "confidential", models.PayloadSchemaType.BOOL)
            if s.qdrant_url:  # collections created before versions existed
                try:
                    self.client.create_payload_index(s.chunks_collection, "superseded", models.PayloadSchemaType.BOOL)
                except Exception:  # noqa: BLE001 - index already there
                    pass
            if not self.client.collection_exists(s.documents_collection):
                self.client.create_collection(s.documents_collection, vectors_config={})

    def close(self):
        self.client.close()

    # ------------------------------------------------------------------ documents
    def get_document(self, doc_id: str) -> dict | None:
        with self._lock:
            recs = self.client.retrieve(self.settings.documents_collection, [doc_id], with_payload=True)
        return recs[0].payload if recs else None

    def list_documents(self, include_signature: bool = False) -> list[dict]:
        """Registry entries. The signature (content codes + topic vector, ~30 KB each) only when asked for."""
        payload = True if include_signature else models.PayloadSelectorExclude(exclude=["signature"])
        out, offset = [], None
        with self._lock:
            while True:
                recs, offset = self.client.scroll(self.settings.documents_collection, limit=256, offset=offset, with_payload=payload)
                out.extend(r.payload for r in recs)
                if offset is None:
                    break
        return sorted(out, key=lambda d: d.get("ingested_at", ""), reverse=True)

    def delete_document(self, doc_id: str) -> bool:
        with self._lock:
            existed = self.get_document(doc_id) is not None
            self.client.delete(self.settings.chunks_collection, points_selector=models.FilterSelector(filter=_filter({"doc_id": doc_id})))
            self.client.delete(self.settings.documents_collection, points_selector=models.PointIdsList(points=[doc_id]))
        return existed

    def set_document_domain(self, doc_id: str, domain: str) -> dict:
        """Re-classify a document: payload update on its chunks + registry entry (no re-embedding)."""
        domain = validate_domain(domain)
        with self._lock:
            doc = self.get_document(doc_id)
            if doc is None:
                raise KeyError(doc_id)
            self.client.set_payload(self.settings.chunks_collection, payload={"domain": domain},
                                    points=models.FilterSelector(filter=_filter({"doc_id": doc_id})), wait=True)
            self.client.set_payload(self.settings.documents_collection, payload={"domain": domain},
                                    points=[doc_id], wait=True)
            moved = self.client.count(self.settings.chunks_collection, count_filter=_filter({"doc_id": doc_id, "domain": domain})).count
            total = self.client.count(self.settings.chunks_collection, count_filter=_filter({"doc_id": doc_id})).count
        if moved != total:  # verify every chunk carries the new label
            raise RuntimeError(f"Domain update incomplete for {doc_id}: {moved}/{total} chunks updated")
        return {**doc, "domain": domain}

    def set_document_confidential(self, doc_id: str, confidential: bool) -> dict:
        """Mark a document confidential (hidden from role 'user'): payload update on its chunks + registry."""
        with self._lock:
            doc = self.get_document(doc_id)
            if doc is None:
                raise KeyError(doc_id)
            self.client.set_payload(self.settings.chunks_collection, payload={"confidential": confidential},
                                    points=models.FilterSelector(filter=_filter({"doc_id": doc_id})), wait=True)
            self.client.set_payload(self.settings.documents_collection, payload={"confidential": confidential},
                                    points=[doc_id], wait=True)
            flagged = self.client.count(self.settings.chunks_collection,
                                        count_filter=_filter({"doc_id": doc_id, "confidential": confidential})).count
            total = self.client.count(self.settings.chunks_collection, count_filter=_filter({"doc_id": doc_id})).count
        if flagged != total:
            raise RuntimeError(f"Confidential flag update incomplete for {doc_id}: {flagged}/{total} chunks")
        return {**doc, "confidential": confidential}

    def set_document_fields(self, doc_id: str, fields: dict[str, Any]) -> None:
        """Update registry-only fields of a document (signature, replaces ...)."""
        with self._lock:
            self.client.set_payload(self.settings.documents_collection, payload=fields, points=[doc_id], wait=True)

    def set_document_superseded(self, doc_id: str, superseded: bool, replaced_by: str | None = None, by: str | None = None) -> dict:
        """Hide a document from chat (an updated version replaced it) or bring it back. Nothing is deleted:
        payload update on its chunks + registry, verified like the domain / confidential updates."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            doc = self.get_document(doc_id)
            if doc is None:
                raise KeyError(doc_id)
            self.client.set_payload(self.settings.chunks_collection, payload={"superseded": superseded},
                                    points=models.FilterSelector(filter=_filter({"doc_id": doc_id})), wait=True)
            fields = ({"superseded": True, "replaced_by": replaced_by, "replaced_at": now, "replaced_by_user": by}
                      if superseded else {"superseded": False, "replaced_by": None, "replaced_at": None, "replaced_by_user": None})
            self.client.set_payload(self.settings.documents_collection, payload=fields, points=[doc_id], wait=True)
            marked = self.client.count(self.settings.chunks_collection,
                                       count_filter=_filter({"doc_id": doc_id, "superseded": superseded})).count
            total = self.client.count(self.settings.chunks_collection, count_filter=_filter({"doc_id": doc_id})).count
        if marked != total:
            raise RuntimeError(f"Version update incomplete for {doc_id}: {marked}/{total} chunks")
        return {**doc, **fields}

    def document_vectors_mean(self, doc_id: str, limit: int = 600) -> list[float] | None:
        """What the document is about: mean of the stored (text) chunk vectors, no embedding call."""
        vectors: list[list[float]] = []
        offset = None
        with self._lock:
            while len(vectors) < limit:
                recs, offset = self.client.scroll(self.settings.chunks_collection,
                                                  scroll_filter=_filter({"doc_id": doc_id, "!kind": "image"}),
                                                  limit=min(256, limit - len(vectors)), offset=offset,
                                                  with_payload=False, with_vectors=[DENSE])
                for r in recs:
                    v = r.vector.get(DENSE) if isinstance(r.vector, dict) else r.vector
                    if v:
                        vectors.append(v)
                if offset is None:
                    break
        from .ingestion.similarity import mean_vector

        return mean_vector(vectors)

    def domain_stats(self) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for d in self.list_documents():
            if d.get("superseded"):
                continue
            s = stats.setdefault(d.get("domain") or UNASSIGNED, {"documents": 0, "chunks": 0})
            s["documents"] += 1
            s["chunks"] += d.get("chunks", 0)
        return stats

    # ------------------------------------------------------------------ indexing
    def index_document(self, doc: dict[str, Any], chunks: list[Chunk], meta: dict[str, Any]) -> int:
        """Replace all chunks of the document, then write its registry entry."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        points = self._points(doc, chunks, meta, now)
        with self._lock:
            self.client.delete(self.settings.chunks_collection, points_selector=models.FilterSelector(filter=_filter({"doc_id": doc["doc_id"]})))
            for start in range(0, len(points), 256):
                self.client.upsert(self.settings.chunks_collection, points[start : start + 256])
            self.client.upsert(self.settings.documents_collection, [
                models.PointStruct(id=doc["doc_id"], vector={}, payload={**doc, "chunks": len(points), "meta": meta, "ingested_at": now})])
        return len(points)

    def replace_image_chunks(self, doc: dict[str, Any], chunks: list[Chunk]) -> int:
        """Swap only the document's picture-description chunks (kind "image"); text and records stay untouched."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        points = self._points(doc, chunks, doc.get("meta") or {}, now)
        with self._lock:
            self.client.delete(self.settings.chunks_collection,
                               points_selector=models.FilterSelector(filter=_filter({"doc_id": doc["doc_id"], "kind": "image"})))
            for start in range(0, len(points), 256):
                self.client.upsert(self.settings.chunks_collection, points[start : start + 256])
            total = self.client.count(self.settings.chunks_collection, count_filter=_filter({"doc_id": doc["doc_id"]})).count
            self.client.set_payload(self.settings.documents_collection, payload={"chunks": total, "image_chunks": len(points)},
                                    points=[doc["doc_id"]], wait=True)
        return len(points)

    def _points(self, doc: dict[str, Any], chunks: list[Chunk], meta: dict[str, Any], now: str) -> list[models.PointStruct]:
        points = []
        for start in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[start : start + EMBED_BATCH]
            texts = [c.embed_text for c in batch]
            dense = self.embedder.embed_documents(texts)
            sparse = self.sparse.embed_documents(texts)
            for c, dv, (idx, val) in zip(batch, dense, sparse):
                payload = {
                    "doc_id": c.doc_id, "file_name": doc["file_name"], "file_type": doc["file_type"],
                    "chunk_index": c.index, "kind": c.kind, "text": c.text, "context": c.context,
                    "section": c.section, "location": c.location, "fields": c.fields, "title": c.title,
                    **c.extra, "meta": meta, "domain": doc.get("domain", UNASSIGNED),
                    "confidential": bool(doc.get("confidential", False)), "superseded": bool(doc.get("superseded", False)),
                    "ingested_at": now,
                }
                points.append(models.PointStruct(id=c.id, vector={DENSE: dv, SPARSE: models.SparseVector(indices=idx, values=val)}, payload=payload))
        return points

    # ------------------------------------------------------------------ retrieval
    def _query_vectors(self, query: str) -> tuple[list[float], models.SparseVector]:
        """Embed a query once; the same question is searched several times (sub-queries, sheet filters)."""
        cached = self._qcache.get(query)
        if cached is None:
            dense = self.embedder.embed_query(query)  # network call with Azure embeddings
            idx, val = self.sparse.embed_query(query)
            cached = (dense, models.SparseVector(indices=idx, values=val))
            self._qcache[query] = cached
            if len(self._qcache) > 512:
                self._qcache.popitem(last=False)
        else:
            self._qcache.move_to_end(query)
        return cached

    def prefetch_queries(self, queries: list[str]) -> None:
        """Embed several query phrasings at once: one Azure request instead of one per phrasing."""
        missing = [q for q in dict.fromkeys(queries) if q not in self._qcache]
        if not missing:
            return
        if isinstance(self.embedder, AzureEmbedder) and len(missing) > 1:
            dense = self.embedder.embed_documents(missing)  # text-embedding-3: same vectors as embed_query
            for q, dv in zip(missing, dense):
                idx, val = self.sparse.embed_query(q)
                self._qcache[q] = (dv, models.SparseVector(indices=idx, values=val))
        else:
            for q in missing:
                self._query_vectors(q)

    def dense_similarity(self, queries: list[str], ids: list[str]) -> dict[str, float]:
        """Cosine similarity of stored chunk vectors to the best-matching query (meaning-level match)."""
        if not ids or not queries:
            return {}
        qvs = [self._query_vectors(q)[0] for q in queries]
        qvs = [(v, math.sqrt(sum(x * x for x in v)) or 1.0) for v in qvs]
        with self._lock:
            recs = self.client.retrieve(self.settings.chunks_collection, ids, with_payload=False, with_vectors=[DENSE])
        out: dict[str, float] = {}
        for r in recs:
            vec = r.vector.get(DENSE) if isinstance(r.vector, dict) else r.vector
            if not vec:
                continue
            n = math.sqrt(sum(x * x for x in vec)) or 1.0
            out[str(r.id)] = max(sum(a * b for a, b in zip(vec, qv)) / (n * qn) for qv, qn in qvs)
        return out

    def search(self, query: str, top_k: int = 8, filters: dict[str, Any] | None = None, mode: str = "hybrid") -> list[dict]:
        flt = _filter(filters)
        dense_q, sparse_q = self._query_vectors(query)
        col = self.settings.chunks_collection
        with self._lock:
            if mode == "dense":
                res = self.client.query_points(col, query=dense_q, using=DENSE, query_filter=flt, limit=top_k, with_payload=True)
            elif mode == "keyword":
                res = self.client.query_points(col, query=sparse_q, using=SPARSE, query_filter=flt, limit=top_k, with_payload=True)
            else:
                res = self.client.query_points(
                    col,
                    prefetch=[models.Prefetch(query=dense_q, using=DENSE, filter=flt, limit=top_k * 4),
                              models.Prefetch(query=sparse_q, using=SPARSE, filter=flt, limit=top_k * 4)],
                    query=models.FusionQuery(fusion=models.Fusion.RRF), limit=top_k, with_payload=True)
        return [{"id": str(p.id), "score": round(p.score, 4), **p.payload} for p in res.points]

    def scroll_chunks(self, filters: dict[str, Any], limit: int = 500, fields: list[str] | bool = True) -> list[dict]:
        out, offset = [], None
        with self._lock:
            while len(out) < limit:
                recs, offset = self.client.scroll(self.settings.chunks_collection, scroll_filter=_filter(filters),
                                                  limit=min(256, limit - len(out)), offset=offset, with_payload=fields)
                out.extend({"id": str(r.id), **(r.payload or {})} for r in recs)
                if offset is None:
                    break
        return out

    def get_chunks(self, doc_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._lock:
            recs, _ = self.client.scroll(self.settings.chunks_collection, scroll_filter=_filter({"doc_id": doc_id}), limit=2000, with_payload=True)
        recs = sorted(recs, key=lambda r: r.payload.get("chunk_index", 0))
        return [{"id": str(r.id), **r.payload} for r in recs[offset : offset + limit]]

    def stats(self) -> dict:
        with self._lock:
            return {
                "chunks": self.client.count(self.settings.chunks_collection).count,
                "documents": self.client.count(self.settings.documents_collection).count,
            }


@lru_cache
def get_store() -> KGStore:
    return KGStore()
