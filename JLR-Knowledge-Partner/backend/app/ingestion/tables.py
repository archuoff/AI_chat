"""Shared logic for tables found inside Word / PowerPoint documents."""
from __future__ import annotations

from typing import Any

from .models import Element
from .utils import clean_text, render_fields, unique_keys


def _has_header(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False
    head = rows[0]
    return all(h and len(h) <= 80 for h in head) and len(set(head)) == len(head)


def table_to_elements(rows: list[list[str]], section: list[str], location: dict[str, Any], table_no: int) -> list[Element]:
    rows = [[clean_text(c) for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    loc = {**location, "table": table_no}
    if not _has_header(rows):
        # layout table (boxes of text) -> treat as prose
        text = "\n".join(" | ".join(c for c in r if c) for r in rows)
        return [Element("text", text, section, loc)]
    headers = unique_keys(rows[0], [f"Column {i + 1}" for i in range(len(rows[0]))])
    out = []
    for i, r in enumerate(rows[1:], start=1):
        fields = {h: v for h, v in zip(headers, r) if v}
        if fields:
            out.append(Element("record", render_fields(fields), section, {**loc, "row": i}, fields, next(iter(fields.values()))[:150]))
    return out


def dedupe_merged(cells: list[Any]) -> list[Any]:
    """python-docx / python-pptx repeat a merged cell once per grid column; keep one copy."""
    out, last = [], object()
    for c in cells:
        key = id(getattr(c, "_tc", c))
        if key != last:
            out.append(c)
        last = key
    return out
