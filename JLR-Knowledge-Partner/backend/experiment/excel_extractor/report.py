"""A self-contained HTML view of the extraction: the sheet drawn with Excel's own sizes, pictures and text boxes at their real anchors,
every region outlined with its kind and confidence, and the inventory verdict. Open report.html in a browser (media/ sits next to it)."""
from __future__ import annotations

import html
from typing import TYPE_CHECKING

from .geometry import EMU_PX, Geometry
from .model import a1

if TYPE_CHECKING:
    from .extract import Extraction
    from .grid import SheetData

MAX_ROWS, MAX_COLS = 300, 40
HEAD_W, HEAD_H = 44, 22
KIND_COLOR = {"table": "#1d6fd8", "transposed_table": "#7a3fd1", "key_value": "#0b8f81", "picture_strip": "#d97a06", "requirement_list": "#b3261e",
              "frame": "#444444", "text": "#888888", "title": "#888888", "stray": "#c0392b", "unknown": "#c0392b"}
CLASS_FILL = {"dark": "#2b3a67", "mid": "#a6b0bf", "light": "#e9edf3"}


def _e(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _fill(st) -> str:
    if st is None or st.fill_class == "none":
        return "#ffffff"
    if st.fill and len(st.fill) == 6 and all(ch in "0123456789ABCDEF" for ch in st.fill):
        return f"#{st.fill}"
    return CLASS_FILL.get(st.fill_class, "#ffffff")


def _lum_dark(hexcolor: str) -> bool:
    try:
        r, g, b = (int(hexcolor[i : i + 2], 16) for i in (1, 3, 5))
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 140
    except ValueError:
        return False


def _sheet_html(sd: "SheetData", idx: int) -> str:
    sh = sd.model
    geo = Geometry(sh)
    rows = min(max(sh.max_row, 1), MAX_ROWS)
    cols = min(max(sh.max_col, 1), MAX_COLS)
    inv = sh.inventory
    parts: list[str] = [f'<section id="s{idx}"><h2>{_e(sh.name)} <small>{_e(sh.state)} · {_e(sh.dims)}</small></h2>']
    verdict = inv.get("verdict", "")
    parts.append(f'<p class="v {verdict}">Inventory: <b>{_e(verdict.replace("_", " "))}</b></p>')
    if inv.get("problems"):
        parts.append("<ul class='problems'>" + "".join(f"<li>{_e(p)}</li>" for p in inv["problems"]) + "</ul>")
    if sh.max_row > MAX_ROWS or sh.max_col > MAX_COLS:
        parts.append(f"<p class='note'>The drawing shows the first {rows} rows and {cols} columns; the model has all {sh.max_row} x {sh.max_col}.</p>")

    W = HEAD_W + geo.left(cols + 1)
    H = HEAD_H + geo.top(rows + 1)
    parts.append(f'<div class="sheet" style="width:{W}px;height:{H}px">')
    # grid
    t = ['<table style="table-layout:fixed;border-collapse:collapse"><colgroup>', f'<col style="width:{HEAD_W}px">']
    t += [f'<col style="width:{geo._col_w(c)}px">' for c in range(1, cols + 1)]
    t.append("</colgroup>")
    t.append(f'<tr style="height:{HEAD_H}px"><th></th>' + "".join(f"<th>{_e(a1(1, c)[:-1])}</th>" for c in range(1, cols + 1)) + "</tr>")
    covered: set[tuple[int, int]] = set()
    for r in range(1, rows + 1):
        h = geo._row_h(r)
        t.append(f'<tr style="height:{h}px"><th>{r}</th>')
        for c in range(1, cols + 1):
            if (r, c) in covered:
                continue
            m = sd.merge_at.get((r, c))
            if m is not None and (m.r0, m.c0) != (r, c):
                continue
            span = ""
            if m is not None:
                span = f' rowspan="{min(m.r1, rows) - m.r0 + 1}" colspan="{min(m.c1, cols) - m.c0 + 1}"'
                for rr in range(m.r0, min(m.r1, rows) + 1):
                    for cc in range(m.c0, min(m.c1, cols) + 1):
                        covered.add((rr, cc))
            cell = sd.cells.get((r, c))
            st = sd.style(r, c)
            bg = _fill(st)
            color = "#fff" if _lum_dark(bg) else "#111"
            bd = "".join(f"border-{n}:1px solid #555;" for ch, n in (("T", "top"), ("R", "right"), ("B", "bottom"), ("L", "left")) if st and ch in st.border)
            text = ""
            if cell is not None and cell.t != "p":
                text = cell.d or ("" if cell.v is None else str(cell.v))
            err = ' class="err"' if cell is not None and cell.t == "e" else ""
            hh = geo.height(r, min(m.r1, rows)) if m else h
            ww = geo.width(c, min(m.c1, cols)) if m else geo._col_w(c)
            weight = "font-weight:700;" if st and st.bold else ""
            t.append(f'<td{span}{err} style="background:{bg};color:{color};{bd}{weight}"><div style="height:{max(hh - 1, 0)}px;width:{max(ww - 1, 0)}px">{_e(text)}</div></td>')
        t.append("</tr>")
    t.append("</table>")
    parts.append("".join(t))

    def box(cls: str, r0: int, c0: int, r1: int, c1: int, extra: str = "") -> str:
        x, y = HEAD_W + geo.left(c0), HEAD_H + geo.top(r0)
        return f'class="{cls}" style="left:{x}px;top:{y}px;width:{geo.width(c0, c1)}px;height:{geo.height(r0, r1)}px;{extra}"'

    # regions (outer first so inner ones stay visible)
    depth: dict[str, int] = {}
    for g in sh.regions:
        depth[g.id] = depth.get(g.parent, -1) + 1 if g.parent else 0
        if g.r0 > rows or g.c0 > cols:
            continue
        col = KIND_COLOR.get(g.kind, "#c0392b")
        label = f"{g.id} {g.kind} {g.confidence:.2f}" + (" ?" if g.needs_llm else "")
        parts.append(f'<div {box("region", g.r0, g.c0, min(g.r1, rows), min(g.c1, cols), f"border-color:{col};margin:{depth[g.id] * 2}px;")}><span style="background:{col}">{_e(label)}</span></div>')
    # pictures at their anchors
    for p in sh.pictures:
        a = p.anchor
        if a.r0 > rows or a.c0 > cols:
            continue
        if not p.media:
            parts.append(f'<div {box("pic missing", a.r0, a.c0, min(a.r1, rows), min(a.c1, cols))}>?<i>{_e(p.id)}</i></div>')
            continue
        src = f"media/{_e(p.media)}"
        tip = _e(f"{p.id} {p.kind} {a.range} alt={p.alt} {p.neighbours.get('row_label', '')}")
        if a.kind == "cell":
            parts.append(f'<div {box("pic", a.r0, a.c0, min(a.r1, rows), min(a.c1, cols))} title="{tip}"><img src="{src}"></div>')
        else:
            x = HEAD_W + geo.left(a.r0 and a.c0) + a.dc0 // EMU_PX
            y = HEAD_H + geo.top(a.r0) + a.dr0 // EMU_PX
            w = max(a.w // EMU_PX, 8)
            h = max(a.h // EMU_PX, 8)
            parts.append(f'<div class="pic float" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px" title="{tip}"><img src="{src}"></div>')
    # shapes with text
    for s in sh.shapes:
        a = s.anchor
        if s.kind in ("connector", "group") or a.r0 > rows or a.c0 > cols:
            continue
        x = HEAD_W + geo.left(a.c0) + a.dc0 // EMU_PX
        y = HEAD_H + geo.top(a.r0) + a.dr0 // EMU_PX
        parts.append(f'<div class="shape" style="left:{x}px;top:{y}px;width:{max(a.w // EMU_PX, 24)}px;height:{max(a.h // EMU_PX, 16)}px" title="{_e(s.id + " " + s.kind)}">'
                     f"<b>{_e(s.kind)}</b> {_e(s.text[:200])}</div>")
    parts.append("</div>")
    # regions table
    parts.append("<h3>Regions</h3><table class='regions'><tr><th>id</th><th>range</th><th>kind</th><th>conf</th><th>title</th><th>headers</th><th>evidence</th></tr>")
    for g in sh.regions:
        parts.append(f"<tr class='{'unsure' if g.needs_llm else ''}'><td>{g.id}{' ↳' + g.parent if g.parent else ''}</td><td>{g.range}</td><td>{g.kind}</td>"
                     f"<td>{g.confidence:.2f}{' ' + _e(g.alternatives) if g.alternatives else ''}</td><td>{_e(g.title)}</td>"
                     f"<td>{_e(' | '.join(h for h in g.headers if h)[:160])}</td><td>{_e('; '.join(g.evidence)[:300])}</td></tr>")
    parts.append("</table></section>")
    return "".join(parts)


CSS = """
body{font:13px/1.35 system-ui,Segoe UI,Arial,sans-serif;margin:16px;color:#111;background:#fafafa}
h1{font-size:18px} h2{font-size:16px;margin:28px 0 6px} h2 small{color:#666;font-weight:400}
.sheet{position:relative;overflow:hidden;background:#fff;border:1px solid #bbb;margin:8px 0}
.sheet table{position:absolute;left:0;top:0}
.sheet th{background:#eceff3;color:#556;font-weight:600;font-size:11px;border:1px solid #cfd5dd;padding:0}
.sheet td{padding:0;border:1px solid #e3e6ea;vertical-align:top;font-size:12px}
.sheet td div{overflow:hidden;padding:1px 3px;white-space:pre-wrap;box-sizing:border-box}
td.err{background:#ffe9e9!important;color:#a00!important}
.region{position:absolute;border:2px solid;pointer-events:none;box-sizing:border-box}
.region span{position:absolute;left:-2px;top:-17px;color:#fff;font-size:10px;padding:1px 4px;border-radius:3px 3px 0 0;white-space:nowrap}
.pic{position:absolute;box-sizing:border-box;border:1px dashed #0a7;background:rgba(0,170,119,.07)}
.pic img{width:100%;height:100%;object-fit:contain;display:block}
.pic.missing{border-color:#c00;color:#c00;font-weight:700} .pic.missing i{font-size:9px;font-weight:400}
.shape{position:absolute;box-sizing:border-box;border:1px dashed #a60;background:rgba(255,200,80,.25);font-size:11px;overflow:hidden;padding:2px}
.v.complete{color:#067} .v.needs_attention{color:#b60} .problems{color:#a40;margin:2px 0 8px}
table.regions{border-collapse:collapse;font-size:12px;margin:6px 0} table.regions td,table.regions th{border:1px solid #ccc;padding:3px 6px;vertical-align:top}
table.regions tr.unsure td{background:#fff6e0} .note{color:#666}
nav a{margin-right:12px}
"""


def write_report(ex: "Extraction", out) -> None:
    body = [f"<h1>{_e(ex.book.file)}</h1>", "<nav>" + "".join(f'<a href="#s{i}">{_e(n)}</a>' for i, n in enumerate(ex.data)) + "</nav>"]
    if ex.book.warnings:
        body.append("<p class='problems'>" + _e("; ".join(ex.book.warnings)) + "</p>")
    body += [_sheet_html(sd, i) for i, sd in enumerate(ex.data.values())]
    (out / "report.html").write_text(f"<!doctype html><meta charset='utf-8'><title>{_e(ex.book.file)}</title><style>{CSS}</style>{''.join(body)}", encoding="utf-8")
