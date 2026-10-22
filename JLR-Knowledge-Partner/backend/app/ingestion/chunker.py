"""Turn parsed elements into embeddable chunks.

* record  -> one chunk per table row; very wide rows are split by column groups,
             each piece repeats the row's key (e.g. the vehicle name) so it stays findable.
* text    -> split with a recursive character splitter (paragraph > line > sentence).
Every chunk carries a context line (file > section > location) that is embedded with it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

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

    @property
    def embed_text(self) -> str:
        return f"{self.context}\n{self.text}"


def _location_label(loc: dict[str, Any]) -> str:
    for key, label in (("page", "page"), ("slide", "slide"), ("row", "row")):
        if key in loc:
            return f"{label} {loc[key]}"
    return ""


def _context(file_name: str, el: Element) -> str:
    parts = [file_name, *el.section]
    loc = _location_label(el.location)
    return " › ".join(p for p in parts if p) + (f" ({loc})" if loc else "")


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


def build_chunks(doc_id: str, doc: ParsedDocument, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks: list[Chunk] = []

    def add(el: Element, text: str, fields: dict | None, part: int | None, parts: int):
        idx = len(chunks)
        extra = {"part": part, "parts": parts} if parts > 1 else {}
        chunks.append(Chunk(str(uuid.uuid5(_NS, f"{doc_id}:{idx}")), doc_id, idx, el.kind, text,
                            _context(doc.file_name, el), list(el.section), dict(el.location), fields, el.title, extra))

    for el in doc.elements:
        if el.kind == "record":
            pieces = _split_record(el, chunk_size, splitter)
            for i, (text, fields) in enumerate(pieces, start=1):
                add(el, text, fields, i, len(pieces))
        else:
            parts = splitter.split_text(el.text)
            for i, text in enumerate(parts, start=1):
                add(el, text, None, i, len(parts))
    return chunks
