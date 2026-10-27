"""Steps 3-5 of the RAG flow: retrieve -> rerank -> expand into evidence units.

Evidence unit = one source location (a table row, a PDF page, a slide, a Word section), built from
its chunks, so a wide Excel row split into several chunks comes back whole.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any

from ..config import get_settings
from ..llm import get_reranker
from ..store import get_store
from .judge import judge
from .vocab import entity_key, get_vocabulary

log = logging.getLogger(__name__)

EXACT_ID_FLOOR = 0.95
ENTITY_BOOST = 0.2
SHEET_BOOST = 0.1
MAX_STRUCTURED_ROWS = 30
MAX_STRUCTURED_CHUNKS = 40
RERANK_TOP = 40


def _unit_key(c: dict) -> str:
    loc = {k: v for k, v in (c.get("location") or {}).items() if k != "range"}
    return json.dumps([c["doc_id"], c["kind"], loc], sort_keys=True, default=str)


def _merge_filters(base: dict | None, extra: dict) -> dict:
    return {**(base or {}), **extra}


def _dominant_docs(cands: dict[str, dict], share: float) -> list[str]:
    """Documents that hold more than `share` of a (big enough) candidate pool: they may be crowding the others out."""
    if len(cands) < 10:
        return []
    counts: dict[str, int] = {}
    for c in cands.values():
        counts[c["doc_id"]] = counts.get(c["doc_id"], 0) + 1
    return [d for d, n in counts.items() if n / len(cands) > share]  # strictly more: a 50 / 50 split hogs nothing


def _diversify(units: list[dict], k: int, min_per_doc: int, max_share: float) -> list[dict]:
    """units are in rank order. Keep k of them so that every document with equally strong evidence has at least
    `min_per_doc` places and no document has more than `max_share` of them; the rest go by rank. Order is kept."""
    doc = lambda u: u["chunks"][0]["doc_id"]  # noqa: E731
    by_doc: dict[str, list[int]] = {}
    for i, u in enumerate(units):
        by_doc.setdefault(doc(u), []).append(i)
    if len(by_doc) < 2 or len(units) <= k and all(len(v) <= max(min_per_doc, math.ceil(max_share * k)) for v in by_doc.values()):
        return units[:k]
    top = max((u.get("grade") or 0) for u in units)
    cap = max(min_per_doc, math.ceil(max_share * k))
    chosen: set[int] = set()
    for _doc, idxs in sorted(by_doc.items(), key=lambda kv: kv[1][0]):  # best-ranked document first
        strong = [i for i in idxs if (units[i].get("grade") or 0) >= top]  # a weak match never pushes out a strong one
        for i in strong[:min_per_doc]:
            if len(chosen) < k:
                chosen.add(i)
    count: dict[str, int] = {}
    for i in chosen:
        count[doc(units[i])] = count.get(doc(units[i]), 0) + 1
    for i, u in enumerate(units):
        if len(chosen) >= k:
            break
        if i not in chosen and count.get(doc(u), 0) < cap:
            chosen.add(i)
            count[doc(u)] = count.get(doc(u), 0) + 1
    for i in range(len(units)):  # still room (every other document is capped): fill by rank
        if len(chosen) >= k:
            break
        chosen.add(i)
    return [units[i] for i in sorted(chosen)]


def _collect(plan: dict, user_filters: dict | None, named_sheets: list[str]) -> dict[str, dict]:
    s = get_settings()
    store = get_store()
    cands: dict[str, dict] = {}

    def add(hits: list[dict], **flags):
        for h in hits:
            c = cands.setdefault(h["id"], h)
            for k, v in flags.items():
                c[k] = c.get(k) or v

    for q in plan.get("search_queries") or [plan["standalone_question"]]:
        add(store.search(q, s.retrieve_candidates, user_filters))
        if plan.get("sheets"):
            add(store.search(q, s.retrieve_candidates // 2, _merge_filters(user_filters, {"location.sheet": plan["sheets"]})))
    dominant = _dominant_docs(cands, s.hogging_doc_share) if s.diversify_documents else []
    if dominant:  # one document fills the pool: look again at everything else, so a document with the same facts is not lost
        for q in plan.get("search_queries") or [plan["standalone_question"]]:
            add(store.search(q, s.retrieve_candidates // 2, _merge_filters(user_filters, {"!doc_id": dominant})))
    for id_ in plan.get("ids", []):
        hits = store.search(id_, 100, user_filters, mode="keyword")
        add([h for h in hits if id_.lower() in h["text"].lower()], exact=True)
    if plan.get("intent") in ("comparison", "list") and named_sheets:
        rows = store.scroll_chunks(_merge_filters(user_filters, {"location.sheet": named_sheets, "kind": "record"}), limit=400)
        add(rows, structured=True)
    return cands


def _cap(cands: list[dict], limit: int) -> list[dict]:
    """Keep the reranker's work bounded: exact-ID hits, rows of the requested sheet (best first),
    then the best-scoring search hits."""
    by_score = lambda c: c.get("score", 0.0)  # noqa: E731
    exact = [c for c in cands if c.get("exact")]
    structured = sorted((c for c in cands if c.get("structured") and not c.get("exact")), key=by_score, reverse=True)
    searched = sorted((c for c in cands if not c.get("exact") and not c.get("structured")), key=by_score, reverse=True)
    keep = exact + structured[:MAX_STRUCTURED_CHUNKS]
    return keep + searched[: max(limit - len(keep), limit // 2)]


def _rerank_queries(question: str, plan: dict) -> list[str]:
    return list(dict.fromkeys([question] + [q for q in plan.get("sub_questions") or [] if q.strip()]))


def _score(question: str, plan: dict, cands: list[dict]) -> None:
    """Cross-encoder score against the question and each of its parts (best one counts), so evidence
    for one part of a two-part question is not dragged down by the other part."""
    reranker = get_reranker()
    if reranker is not None:
        # the cross-encoder runs ~30 pairs/s on CPU: score the best RERANK_TOP candidates (exact IDs and named-sheet
        # rows first, then by search score); the rest keep rel 0 and can still qualify through embedding similarity
        n = get_settings().rerank_chars
        order = sorted(range(len(cands)), key=lambda i: (bool(cands[i].get("exact")), bool(cands[i].get("structured")),
                                                         cands[i].get("score", 0.0)), reverse=True)[:RERANK_TOP]
        for c in cands:
            c["rel"] = 0.0
        scores = reranker.score(question, [f"{cands[i]['context']}\n{cands[i]['text'][:n]}" for i in order])
        for i, p in zip(order, scores, strict=False):
            cands[i]["rel"] = p
    else:  # no reranker: keep search order
        ordered = sorted(cands, key=lambda c: c.get("score", 0), reverse=True)
        for rank, c in enumerate(ordered):
            c["rel"] = 1 - rank / max(len(ordered), 1)
    entities, sheets = set(plan.get("entities", [])), set(plan.get("sheets", []))
    for c in cands:
        rel = c["rel"]
        if entities and entity_key(c.get("title") or "") in entities:
            rel += ENTITY_BOOST
        if sheets and (c.get("location") or {}).get("sheet") in sheets:
            rel += SHEET_BOOST
        if c.get("exact"):
            rel = max(rel, EXACT_ID_FLOOR)
        c["rel"] = min(rel, 1.0)


def _expand(unit: dict) -> None:
    """Fetch the missing parts of a split row / neighbouring parts of a split text block."""
    first = unit["chunks"][0]
    if first.get("section_key") and (first.get("section_chars") or 0) <= get_settings().expand_section_max_chars:
        # hierarchical chunk: one piece of a short enough section matched -> bring the whole section (small to big)
        have = {c["id"] for c in unit["chunks"]}
        extra = [c for c in get_store().scroll_chunks({"doc_id": first["doc_id"], "section_key": first["section_key"]}, limit=40)
                 if c["id"] not in have]
        unit["chunks"] = sorted(unit["chunks"] + extra, key=lambda c: c["chunk_index"])
        return
    parts = first.get("parts")
    if not parts or len(unit["chunks"]) >= parts:
        return
    loc_filters = {f"location.{k}": v for k, v in first["location"].items() if k != "range"}
    flt = {"doc_id": first["doc_id"], "kind": first["kind"], **loc_filters}
    if first["kind"] == "text":
        idx = [c["chunk_index"] for c in unit["chunks"]]
        flt["chunk_index"] = {"gte": min(idx) - 1, "lte": max(idx) + 1}
    have = {c["id"] for c in unit["chunks"]}
    extra = [c for c in get_store().scroll_chunks(flt, limit=12) if c["id"] not in have]
    unit["chunks"] = sorted(unit["chunks"] + extra, key=lambda c: c["chunk_index"])


def _finalise(unit: dict) -> dict:
    chunks = unit["chunks"]
    head = chunks[0]
    fields: dict[str, Any] = {}
    texts: list[str] = []
    for c in chunks:
        fields.update(c.get("fields") or {})
        texts.append(c["text"])
    if head["kind"] == "record" and fields:
        text = "\n".join(f"{k}: {v}" for k, v in fields.items())
    else:
        text = "\n".join(dict.fromkeys(texts))
    return {
        "score": round(unit["score"], 4), "sim": round(unit.get("sim", 0.0), 4), "grade": unit.get("grade"),
        "relevance": round(max(unit["score"], _sim_scaled(unit.get("sim", 0.0))), 4),  # shown in the UI
        "doc_id": head["doc_id"], "file_name": head["file_name"],
        "file_type": head["file_type"], "kind": head["kind"], "context": head["context"], "location": head["location"],
        "section": head.get("section", []), "breadcrumb": head.get("breadcrumb") or [], "relations": head.get("relations") or {},
        "title": head.get("title"), "text": text, "fields": fields or None,
        "exact": any(c.get("exact") for c in chunks), "structured": any(c.get("structured") for c in chunks),
        "chunk_ids": [c["id"] for c in chunks], "image_id": head.get("image_id"), "linked": bool(unit.get("linked")),
    }


def _semantic_gate_on() -> bool:
    s = get_settings()
    return s.semantic_gate == "on" or (s.semantic_gate == "auto" and s.azure_embeddings_enabled)


def _sim_scaled(sim: float) -> float:
    """Map embedding similarity onto the reranker's 0..1 scale for ordering (0.25 -> 0, 0.55 -> 1)."""
    return min(max((sim - 0.25) / 0.30, 0.0), 1.0)


def _passes_gates(u: dict) -> bool:
    s = get_settings()
    return u["score"] >= s.min_relevance or (_semantic_gate_on() and u["sim"] >= s.semantic_min_similarity)


def _table_rows(unit: dict, limit: int) -> list[dict]:
    """All record chunks of the table this unit's row belongs to (Excel table, Word/PowerPoint table)."""
    head = unit["chunks"][0]
    loc = head.get("location") or {}
    flt: dict[str, Any] = {"doc_id": head["doc_id"], "kind": "record"}
    same_cols = None
    if "table" in loc:  # Word / PowerPoint table
        flt["location.table"] = loc["table"]
        for k in ("section", "slide"):
            if k in loc:
                flt[f"location.{k}"] = loc[k]
    elif "sheet" in loc:  # Excel: same sheet + same column span = same table
        flt["location.sheet"] = loc["sheet"]
        same_cols = re.sub(r"\d+", "", loc.get("range", ""))
    else:
        return []
    rows = get_store().scroll_chunks(flt, limit=limit * 4)
    if same_cols is not None:
        rows = [r for r in rows if re.sub(r"\d+", "", (r.get("location") or {}).get("range", "")) == same_cols]
    return rows


def _table_key(u: dict) -> str | None:
    head = u["chunks"][0]
    if head["kind"] != "record":
        return None
    loc = head.get("location") or {}
    if "table" in loc:
        return json.dumps([head["doc_id"], loc.get("section"), loc.get("slide"), loc["table"]], default=str)
    if "sheet" in loc:
        return json.dumps([head["doc_id"], loc["sheet"], re.sub(r"\d+", "", loc.get("range", ""))])
    return None


def _group_tables(units: list[dict]) -> list[dict]:
    """Keep each table's rows together and in sheet order, placed where the table first appears."""
    groups: dict[str, list[dict]] = {}
    for u in units:
        k = _table_key(u)
        if k:
            groups.setdefault(k, []).append(u)
    out, placed = [], set()
    for u in units:
        k = _table_key(u)
        if k is None:
            out.append(u)
        elif k not in placed:
            placed.add(k)
            out.extend(sorted(groups[k], key=lambda x: (x["chunks"][0].get("location") or {}).get("row", 0)))
    return out


def _link_pictures(final: list[dict], cap: int) -> int:
    """A picture and the text it sits with travel together (no graph needed: same document + same sheet row / slide).

    * Excel: a selected row record brings the pictures of that row; a selected picture brings its row record.
    * PowerPoint: a selected slide text / table row brings the slide's pictures; a picture brings the slide text.
    The linked chunks become their own evidence items (own citation, own picture) placed next to the item they belong to."""
    store = get_store()
    seen = {_unit_key(c) for u in final for c in u["chunks"]}
    out: list[dict] = []
    added = 0
    for u in final:
        head = u["chunks"][0]
        loc = head.get("location") or {}
        before: list[dict] = []
        after: list[dict] = []
        if added < cap and head["kind"] in ("record", "image", "text") and ("slide" in loc or ("sheet" in loc and "row" in loc)):
            if "slide" in loc:
                flt: dict[str, Any] = {"doc_id": head["doc_id"], "location.slide": loc["slide"]}
            else:
                flt = {"doc_id": head["doc_id"], "location.sheet": loc["sheet"], "location.row": loc["row"]}
            is_picture = head["kind"] == "image"
            if "sheet" in loc and head["kind"] == "text":
                pass  # a sheet's free text has no row: nothing to link
            else:
                for c in store.scroll_chunks(flt, limit=12):
                    if (c["kind"] == "image") == is_picture or _unit_key(c) in seen or added >= cap:
                        continue  # a picture links to text, text links to pictures; never twice
                    seen.add(_unit_key(c))
                    linked = {"chunks": [c], "score": u["score"], "sim": u["sim"], "grade": u.get("grade", 0), "linked": True}
                    (before if is_picture else after).append(linked)
                    added += 1
        out.extend(before)
        out.append(u)
        out.extend(after)
    final[:] = out
    return added


def retrieve(question: str, plan: dict, user_filters: dict | None = None, timings: dict | None = None,
             usage: dict | None = None) -> list[dict]:
    s = get_settings()
    store = get_store()
    timings = timings if timings is not None else {}
    queries = plan.get("search_queries") or [plan["standalone_question"]]
    sim_queries = list(dict.fromkeys(queries + _rerank_queries(question, plan)))

    t0 = time.perf_counter()
    store.prefetch_queries(sim_queries)  # one embedding request for all phrasings, cached for every sub-search
    timings["embed"] = timings.get("embed", 0) + round((time.perf_counter() - t0) * 1000)

    # whole-sheet loading only for sheets the user actually named (rule match); LLM-guessed sheets just steer the search
    vocab = get_vocabulary()
    named = set(vocab.match_sheets(question)) | set(vocab.match_sheets(plan.get("standalone_question") or ""))
    named_sheets = [sh for sh in plan.get("sheets") or [] if sh in named]

    t0 = time.perf_counter()
    cands = _cap(list(_collect(plan, user_filters, named_sheets).values()), s.max_rerank_candidates)
    timings["search"] = timings.get("search", 0) + round((time.perf_counter() - t0) * 1000)
    timings["candidates"] = len(cands)
    if not cands:
        return []

    t0 = time.perf_counter()
    _score(question, plan, cands)
    sims = store.dense_similarity(sim_queries, [c["id"] for c in cands]) if _semantic_gate_on() else {}
    for c in cands:
        c["sim"] = sims.get(c["id"], 0.0)
    timings["rerank"] = timings.get("rerank", 0) + round((time.perf_counter() - t0) * 1000)

    units: dict[str, dict] = {}
    for c in sorted(cands, key=lambda c: c["rel"], reverse=True):
        u = units.setdefault(_unit_key(c), {"chunks": [], "score": c["rel"], "sim": 0.0})
        u["chunks"].append(c)
        u["sim"] = max(u["sim"], c["sim"])
    order = lambda u: max(u["score"], _sim_scaled(u["sim"]))  # noqa: E731
    ranked = sorted(units.values(), key=order, reverse=True)
    structured_on = plan.get("intent") in ("comparison", "list") and bool(named_sheets)
    sheet_rows = [u for u in ranked if structured_on and any(c.get("structured") for c in u["chunks"])][:MAX_STRUCTURED_ROWS]
    pool = [u for u in ranked if u not in sheet_rows][: s.judge_candidates]

    # ---- which evidence is relevant: LLM judge (quality mode) or score gates (fallback / offline)
    t0 = time.perf_counter()
    verdict = None
    if s.llm_judge:
        verdict = judge(plan.get("standalone_question") or question, plan.get("sub_questions") or [],
                        [f"{u['chunks'][0]['context']}\n" + "\n".join(c["text"] for c in u["chunks"]) for u in pool], usage)
    if verdict is not None:
        timings["judge"] = round((time.perf_counter() - t0) * 1000)
        for i, u in enumerate(pool):
            u["grade"] = verdict.get(i, 0)
        selected = sorted((u for u in pool if u["grade"]), key=lambda u: (u["grade"], order(u)), reverse=True)
        exact = [u for u in pool if any(c.get("exact") for c in u["chunks"]) and u not in selected]
        selected = selected + exact
        selected = (_diversify(selected, s.top_k + 2, s.evidence_min_per_doc, s.evidence_max_doc_share)
                    if s.diversify_documents else selected[: s.top_k + 2])
    else:
        selected = [u for u in pool if _passes_gates(u)]
        selected = (_diversify(selected, s.top_k, s.evidence_min_per_doc, s.evidence_max_doc_share)
                    if s.diversify_documents else selected[: s.top_k])
        if structured_on and not selected and not any(_passes_gates(u) for u in sheet_rows):
            sheet_rows = []  # nothing relevant at all -> "not found"
    if not selected and not sheet_rows:
        return []

    # ---- list / comparison questions: the whole table, not just the rows that matched
    t0 = time.perf_counter()
    final: list[dict] = list(sheet_rows) + [u for u in selected if u not in sheet_rows]
    # (not when the user named a sheet: that sheet is already complete, other tables would only add noise)
    if plan.get("intent") in ("list", "comparison") and not structured_on:
        seen = {_unit_key(u["chunks"][0]) for u in final}
        added = 0
        for u in list(selected):
            if u["chunks"][0]["kind"] != "record" or added >= s.max_table_rows:
                continue
            if verdict is not None and u.get("grade") != 2:  # only tables the judge found directly relevant
                continue
            rows: dict[str, dict] = {}
            for r in _table_rows(u, s.max_table_rows):
                rows.setdefault(_unit_key(r), {"chunks": [], "score": u["score"], "sim": u["sim"], "grade": u.get("grade", 0)})["chunks"].append(r)
            for key, ru in sorted(rows.items(), key=lambda kv: kv[1]["chunks"][0].get("chunk_index", 0)):
                if key not in seen and added < s.max_table_rows:
                    seen.add(key)
                    final.append(ru)
                    added += 1
        timings["table_rows"] = added
        final = _group_tables(final)
    for u in final:
        u["chunks"].sort(key=lambda c: c["chunk_index"])
        _expand(u)
    if s.link_pictures:
        timings["linked"] = _link_pictures(final, s.max_linked_chunks)
    evidence = [_finalise(u) for u in final]
    for n, e in enumerate(evidence, start=1):
        e["n"] = n
    timings["expand"] = timings.get("expand", 0) + round((time.perf_counter() - t0) * 1000)
    return evidence
