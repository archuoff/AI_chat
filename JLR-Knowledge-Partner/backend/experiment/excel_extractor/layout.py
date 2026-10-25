"""The compact layout summary: what the later "Analyst" LLM call reads instead of the whole workbook.

Small and bounded by design: regions with headers, a few sample rows, per-column patterns, pictures with anchors and their neighbours, objects,
and what is still uncertain. Big tables are described by pattern, never dumped. Every string is shortened; if the result is still too big for
`max_chars` per sheet, detail is dropped step by step (samples, patterns, picture lists ...) and the omission is stated.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING, Any

from .model import Sheet, rng

if TYPE_CHECKING:
    from .extract import Extraction
    from .grid import SheetData

CELL = 48


def _t(s: Any, n: int = CELL) -> str:
    s = "" if s is None else str(s).replace("\n", " ⏎ ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _row(data: "SheetData", r: int, c0: int, c1: int, limit: int = 6) -> list[str]:
    cells = []
    for c in range(c0, c1 + 1):
        m = data.merge_at.get((r, c))
        if m is not None and (m.r0, m.c0) != (r, c) and m.r0 != r:
            continue
        cell = data.cells.get((r, c))
        if cell is None:
            continue
        cells.append(f"{cell.a1}={'[picture]' if cell.t == 'p' else _t(cell.d or cell.v)}")
    return cells[:limit] + ([f"+{len(cells) - limit} more"] if len(cells) > limit else [])


def _region(data: "SheetData", g, detail: int) -> dict:
    out: dict[str, Any] = {"id": g.id, "range": g.range, "kind": g.kind, "confidence": g.confidence}
    if g.parent:
        out["parent"] = g.parent
    if g.alternatives:
        out["alternatives"] = [f"{k} {v}" for k, v in g.alternatives]
    if g.title:
        out["title"] = _t(g.title, 80)
    if g.needs_llm:
        out["uncertain"] = True
    if g.children:
        out["children"] = g.children
    if g.kind in ("table", "transposed_table", "key_value"):
        out["orientation"] = g.orientation
        if g.header_rows:
            out["header_rows"] = g.header_rows
        if g.headers:
            hs = [_t(h, 40) for h in g.headers]
            out["headers"] = hs[: 12 if detail else 6] + ([f"+{len(hs) - (12 if detail else 6)} more"] if len(hs) > (12 if detail else 6) else [])
        if g.corner_label:
            out["corner_label"] = _t(g.corner_label, 60)
        out["data_rows"] = len(g.data_rows)
        if g.section_rows:
            out["section_rows"] = g.section_rows[:6]
        if detail and g.data_rows:
            picks = sorted({g.data_rows[0], g.data_rows[len(g.data_rows) // 2], g.data_rows[-1]} | set(g.data_rows[:2]))[: 4 if detail > 1 else 2]
            out["sample_rows"] = [_row(data, r, g.c0, g.c1) for r in picks]
        if detail > 1 and len(g.data_rows) > 6:
            pats = []
            for c in range(g.c0, min(g.c1, g.c0 + 7) + 1):
                vals = [data.text_at(r, c) for r in g.data_rows if data.text_at(r, c)]
                if vals:
                    kinds = Counter("number" if v.replace(".", "", 1).replace("-", "", 1).isdigit() else "text" for v in vals)
                    pats.append(f"{rng(g.r0, c, g.r0, c)[:-1]}: {kinds.most_common(1)[0][0]} ({len(vals)} values)")
            out["column_patterns"] = pats
    if g.evidence and detail > 1:
        out["evidence"] = [_t(e, 110) for e in g.evidence[:4]]
    return out


def _sheet_layout(data: "SheetData", detail: int, pic_cap: int) -> dict:
    sh: Sheet = data.model
    out: dict[str, Any] = {"name": sh.name, "state": sh.state, "used_range": sh.dims, "cells_with_values": sh.non_empty, "merged_areas": len(sh.merges)}
    if sh.hidden_rows or sh.hidden_cols:
        out["hidden"] = {"rows": len(sh.hidden_rows), "columns": len(sh.hidden_cols)}
    out["regions"] = [_region(data, g, detail) for g in sh.regions]
    pics = []
    for p in sh.pictures:
        d = {"id": p.id, "kind": p.kind, "at": p.anchor.range, "region": p.region, "size": f"{p.width}x{p.height}" if p.width else "?"}
        if p.alt:
            d["alt"] = _t(p.alt, 60)
        if detail:
            nb = {k: (_t(v, 90) if isinstance(v, str) else v) for k, v in p.neighbours.items() if k not in ("region",) and v}
            if nb:
                d["neighbours"] = nb
        if p.flags:
            d["flags"] = p.flags[:3]
        pics.append(d)
    if len(pics) > pic_cap:
        by_region = Counter(p["region"] for p in pics)
        out["pictures"] = {"total": len(pics), "by_region": dict(by_region), "examples": pics[:pic_cap]}
    elif pics:
        out["pictures"] = pics
    objs = []
    for s in sh.shapes:
        if s.kind in ("connector", "group"):
            continue
        d = {"id": s.id, "kind": s.kind, "at": s.anchor.range, "region": s.region}
        if s.text:
            d["text"] = _t(s.text, 120)
        if s.kind == "chart":
            d["chart"] = {"types": s.detail.get("types"), "title": s.detail.get("title"), "series": len(s.detail.get("series", []))}
        if s.flags:
            d["flags"] = s.flags
        objs.append(d)
    if objs:
        out["objects"] = objs[:30] + ([{"more": len(objs) - 30}] if len(objs) > 30 else [])
    if sh.comments:
        out["comments"] = [{"at": c.ref, "text": _t(c.text, 80)} for c in sh.comments[:5]] + ([{"more": len(sh.comments) - 5}] if len(sh.comments) > 5 else [])
    if sh.links:
        out["links"] = len(sh.links)
    if sh.tables:
        out["excel_tables"] = [{"name": t["name"], "ref": t["ref"]} for t in sh.tables]
    inv = sh.inventory
    out["inventory"] = {"verdict": inv.get("verdict"), "problems": inv.get("problems", [])[:6]}
    if sh.warnings:
        out["warnings"] = sh.warnings[:5]
    return out


def build_layout(ex: "Extraction", max_chars: int = 12000) -> dict:
    sheets = []
    for sd in ex.data.values():
        for detail, cap in ((2, 40), (1, 25), (1, 10), (0, 6)):
            lay = _sheet_layout(sd, detail, cap)
            if len(json.dumps(lay, ensure_ascii=False)) <= max_chars:
                break
        else:
            keep: list[dict] = []
            for reg in lay["regions"]:  # still too big: keep regions while they fit and say how many were left out
                keep.append(reg)
                if len(json.dumps({**lay, "regions": keep}, ensure_ascii=False)) > max_chars:
                    keep.pop()
                    break
            lay["omitted_regions"] = len(lay["regions"]) - len(keep)
            lay["regions"] = keep
        lay["detail_level"] = detail
        sheets.append(lay)
    return {"file": ex.book.file, "parts": ex.book.parts, "defined_names": ex.book.defined_names[:20], "warnings": ex.book.warnings, "sheets": sheets}
