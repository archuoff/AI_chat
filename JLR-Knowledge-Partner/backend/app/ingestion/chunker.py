"""Turn parsed elements into embeddable chunks.

* record  -> one chunk per table row; very wide rows are split by column groups,
             each piece repeats the row's key (e.g. the vehicle name) so it stays findable.
* text    -> split with a recursive character splitter (paragraph > line > sentence).
* hierarchical (PDF with headings, see `chunking` / `hierarchical_file_types` in config): consecutive text under one
  heading path forms a section. A short section is one chunk; a long one is split where the meaning changes (neighbour
  sentences are embedded, a new chunk starts where similarity drops) and every piece carries a `section_key` so the
  retriever can bring the whole section back when one piece matches (small to big).
Every chunk carries a context line (file > section > location) that is embedded with it.
"""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import get_settings
from .models import Element, ParsedDocument

_NS = uuid.UUID("6f1c2a52-6d1e-4c41-9a43-0f3f3b0d5e11")


@dataclass
class Chunk:
    id: str
    doc_id: str
    index: int
    kind: str
    text: str
    context: str
    section: list[str]
    location: dict[str, Any]
    fields: dict[str, Any] | None = None
    title: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    breadcrumb: list[str] = field(default_factory=list)  # the path to this chunk: file > sheet / headings > unit > row title
    relations: dict[str, Any] = field(default_factory=dict)  # group, prev / next chunk in that group, parent, row_key (pictures)

    @property
    def embed_text(self) -> str:
        return f"{self.context}\n{self.text}"


def _location_label(loc: dict[str, Any]) -> str:
    for key, label in (("page", "page"), ("slide", "slide"), ("row", "row")):
        if key in loc:
            return f"{label} {loc[key]}"
    return ""


def _unit_label(loc: dict[str, Any]) -> str:
    for key, label in (("slide", "Slide"), ("page", "Page")):
        if loc.get(key) is not None:
            return f"{label} {loc[key]}"
    return ""


def breadcrumb_of(file_name: str, el: Element) -> list[str]:
    """file > sheet / headings > page or slide > the row's own title: where this piece sits, in the document's own words."""
    crumbs = [file_name, *el.section]
    unit = _unit_label(el.location)
    if unit and unit.lower() not in {c.lower() for c in crumbs}:
        crumbs.append(unit)
    if el.kind == "record" and el.title:
        crumbs.append(el.title)
    out: list[str] = []
    for c in crumbs:
        c = " ".join(str(c).split())
        if c and (not out or out[-1] != c):
            out.append(c)
    return out


def _context(file_name: str, el: Element) -> str:
    """The breadcrumb as one line (embedded with the chunk, shown to the judge and to the answer step) + row / page."""
    crumbs = [c for c in breadcrumb_of(file_name, el) if c != _unit_label(el.location)]
    loc = _location_label(el.location)
    return " › ".join(crumbs) + (f" ({loc})" if loc else "")


def _link_key(loc: dict[str, Any]) -> str | None:
    """The key a picture and the text it sits with share: one Excel row, or one slide."""
    if loc.get("sheet") is not None and loc.get("row") is not None:
        return f"{loc['sheet']}!{loc['row']}"
    if loc.get("slide") is not None:
        return f"slide:{loc['slide']}"
    return None


def _group_of(c: "Chunk") -> str:
    loc = c.location
    if c.extra.get("section_key"):
        return c.extra["section_key"]
    if c.kind == "record":
        cols = re.sub(r"\d+", "", str(loc.get("range", "")))
        if loc.get("sheet") is not None:
            return f"table:{loc['sheet']}!{cols}"
        return f"table:{loc.get('section') or loc.get('slide') or ''}#{loc.get('table', '')}"
    return f"text:{loc.get('sheet') or ''}{_unit_label(loc)}"


def add_relations(chunks: list["Chunk"]) -> None:
    """group (same section / table / page), the chunk before and after it in that group, its parent heading and link key."""
    last: dict[str, Chunk] = {}
    for c in chunks:
        g = _group_of(c)
        c.relations = {"group": g, "prev": None, "next": None, "parent": c.section[-1] if c.section else None}
        key = _link_key(c.location)
        if key:
            c.relations["row_key"] = key
        if g in last:
            c.relations["prev"] = last[g].id
            last[g].relations["next"] = c.id
        last[g] = c


def _split_record(el: Element, size: int, splitter: RecursiveCharacterTextSplitter) -> list[tuple[str, dict]]:
    """Return [(text, fields_subset)] pieces for one record."""
    items = list((el.fields or {}).items())
    if len(el.text) <= size * 1.5 or not items:
        return [(el.text, dict(items))]
    key_name, key_val = items[0]
    key_line = f"{key_name}: {key_val}"
    pieces, cur, cur_len = [], {}, 0
    for k, v in items:
        line = f"{k}: {v}"
        if len(line) > size:  # one huge cell -> split its text
            if cur:
                pieces.append(cur)
                cur, cur_len = {}, 0
            for part in splitter.split_text(str(v)):
                pieces.append({k: part})
            continue
        if cur and cur_len + len(line) > size:
            pieces.append(cur)
            cur, cur_len = {}, 0
        cur[k] = v
        cur_len += len(line) + 1
    if cur:
        pieces.append(cur)
    out = []
    for p in pieces:
        text = "\n".join(f"{k}: {v}" for k, v in p.items())
        if key_name not in p:
            text = f"{key_line}\n{text}"
        out.append((text, p))
    return out


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")
MAX_UNITS = 400  # a section with more sentences than this uses the plain splitter (embedding cost / time)


def _cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def _units(text: str, long_line: int = 400) -> list[str]:
    """Lines of the section, long lines cut into sentences: the smallest pieces the semantic split may separate."""
    out: list[str] = []
    for line in (l.strip() for l in text.split("\n")):
        if not line:
            continue
        out.extend(p for p in (_SENTENCE.split(line) if len(line) > long_line else [line]) if p.strip())
    return out


def split_semantic(text: str, embed, splitter: RecursiveCharacterTextSplitter, min_chars: int, max_chars: int,
                   percentile: int) -> list[str]:
    """Cut a long section where neighbouring sentences stop being about the same thing.

    A break needs the similarity to fall into the lowest `percentile` % of this section's own values and the piece to
    be at least `min_chars`; a piece never grows past `max_chars`. Any problem -> the plain size splitter (never fails)."""
    units = _units(text)
    if embed is None or not 4 <= len(units) <= MAX_UNITS:
        return splitter.split_text(text)
    try:
        vecs = embed(units)
        sims = [_cosine(vecs[i], vecs[i + 1]) for i in range(len(units) - 1)]
    except Exception:  # noqa: BLE001 - embedding service down: chunking must still work
        return splitter.split_text(text)
    cut = sorted(sims)[max(0, min(len(sims) - 1, int(len(sims) * percentile / 100)))]
    pieces: list[list[str]] = [[units[0]]]
    size = len(units[0])
    for i in range(1, len(units)):
        topic_break = sims[i - 1] < cut and size >= min_chars  # strictly below: ties at the cut must not break everywhere
        if topic_break or size + len(units[i]) > max_chars:
            pieces.append([])
            size = 0
        pieces[-1].append(units[i])
        size += len(units[i]) + 1
    texts = ["\n".join(p) for p in pieces]
    if len(texts) > 1 and len(texts[-1]) < min_chars // 2 and len(texts[-2]) + len(texts[-1]) <= max_chars * 1.25:
        texts[-2:] = ["\n".join(texts[-2:])]  # a tiny tail belongs to the piece before it
    out: list[str] = []
    for t in texts:
        out.extend(splitter.split_text(t) if len(t) > max_chars * 1.5 else [t])  # one huge sentence / table-like line
    return out


def _merge_sections(elements: list[Element]) -> list[tuple[Element, bool]]:
    """Consecutive text elements under the same non-empty heading path become one section element."""
    out: list[tuple[Element, bool]] = []
    for el in elements:
        prev = out[-1][0] if out else None
        if el.kind == "text" and el.section and prev is not None and prev.kind == "text" and prev.section == el.section and out[-1][1]:
            end = el.location.get("page_end", el.location.get("page"))
            merged = Element("text", f"{prev.text}\n{el.text}", prev.section, {**prev.location, "page_end": end})
            out[-1] = (merged, True)
        else:
            out.append((el, el.kind == "text" and bool(el.section)))
    return out


def build_chunks(doc_id: str, doc: ParsedDocument, chunk_size: int, chunk_overlap: int, embed=None) -> list[Chunk]:
    """`embed(list[str]) -> list[vector]` is optional: without it long sections use the plain size splitter."""
    cfg = get_settings()
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    hierarchical = cfg.chunking == "hierarchical" and doc.file_type in {t.strip() for t in cfg.hierarchical_file_types.split(",")}
    items = _merge_sections(doc.elements) if hierarchical else [(el, False) for el in doc.elements]
    chunks: list[Chunk] = []
    sections = 0

    def add(el: Element, text: str, fields: dict | None, part: int | None, parts: int, extra_more: dict | None = None):
        idx = len(chunks)
        extra = {"part": part, "parts": parts} if parts > 1 else {}
        extra.update(extra_more or {})
        chunks.append(Chunk(str(uuid.uuid5(_NS, f"{doc_id}:{idx}")), doc_id, idx, el.kind, text,
                            _context(doc.file_name, el), list(el.section), dict(el.location), fields, el.title, extra,
                            breadcrumb_of(doc.file_name, el)))

    for el, is_section in items:
        if el.kind == "record":
            pieces = _split_record(el, chunk_size, splitter)
            for i, (text, fields) in enumerate(pieces, start=1):
                add(el, text, fields, i, len(pieces))
        elif is_section:
            sections += 1
            if len(el.text) <= cfg.section_max_chars:
                parts = [el.text]
            else:
                parts = split_semantic(el.text, embed if cfg.semantic_split else None, splitter, cfg.chunk_min_chars,
                                       chunk_size, cfg.semantic_percentile)
            more = {"section_key": f"{doc_id}:s{sections}", "section_chars": len(el.text)}
            for i, text in enumerate(parts, start=1):
                add(el, text, None, i, len(parts), more)
        else:
            parts = splitter.split_text(el.text)
            for i, text in enumerate(parts, start=1):
                add(el, text, None, i, len(parts))
    add_relations(chunks)
    return chunks
