"""Find the "boxes" of a sheet: where each table, grid, card, picture strip, list or text block starts and ends, what it is, and why we think so.

Deterministic on purpose: every decision comes with evidence, and anything uncertain is flagged `needs_llm`. The later AI step only has to confirm
or correct these candidates; it never has to find them.

Pipeline: content mask (values, pictures, shapes, merged areas) -> blocks (blank-gap separated) -> frames (bordered boxes divided into cells)
-> title bars (split stacked tables) -> leaf analysis (headers, orientation, kind) -> attach pictures / shapes -> neighbours of every picture.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .grid import SheetData
from .model import Region, rng

Bounds = tuple[int, int, int, int]  # r0, c0, r1, c1
ID_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z ._-]{1,30}?[ _-]?\d{5,}\b|\b[A-Z]{2,6}-\d{3,}(?:-\d+)*\b|\breq-\d{5,}")
MAX_OBJECT_CELLS = 20000
FRAME_LIMIT = 4.0  # fills / borders only help when they are not the whole sheet


# ------------------------------------------------------------------ small helpers
def _runs(values: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for x in sorted(set(values)):
        if out and x == out[-1][1] + 1:
            out[-1] = (out[-1][0], x)
        else:
            out.append((x, x))
    return out


def _sig(text: str) -> str:
    """Shape of a value: digits -> 9, letters -> a, runs squeezed ('0.15 m' -> '9.9 a')."""
    s = re.sub(r"[A-Za-zÀ-ɏ]+", "a", re.sub(r"\d+", "9", text.strip()))
    return re.sub(r"\s+", " ", s)[:24]


def _is_number(text: str) -> bool:
    return bool(re.fullmatch(r"[-+]?[\d.,]+\s*(%|[A-Za-z°/²³µ]{0,6})", text.strip()))


@dataclass
class Item:
    r: int
    c: int
    c_end: int  # last column of the (merged) item
    r_end: int
    text: str
    kind: str  # text | number | picture | object | error
    bold: bool
    fill: str
    pic: str | None = None

    @property
    def span(self) -> int:
        return self.c_end - self.c + 1


class Sheeter:
    """Everything the finder needs to know about one sheet, with the masks built once."""

    def __init__(self, data: SheetData):
        self.d = data
        self.sh = data.model
        self.warnings: list[str] = []
        self.content: set[tuple[int, int]] = set()
        self.obj_at: dict[tuple[int, int], list[str]] = defaultdict(list)
        self._items: dict[int, list[Item]] = {}
        self._by_row: dict[int, list[tuple[int, object]]] = defaultdict(list)
        for (r, c), cell in data.cells.items():
            self._by_row[r].append((c, cell))
        self._build()

    # --- masks
    def _build(self) -> None:
        d, sh = self.d, self.sh
        for (r, c), cell in d.cells.items():
            if cell.v is not None or cell.t in ("p", "f"):
                self.content.add((r, c))
        for m in sh.merges:
            if (m.r0, m.c0) in self.content and (m.r1 - m.r0 + 1) * (m.c1 - m.c0 + 1) <= MAX_OBJECT_CELLS:
                for r in range(m.r0, m.r1 + 1):
                    for c in range(m.c0, m.c1 + 1):
                        self.content.add((r, c))
        for obj in [*sh.pictures, *[s for s in sh.shapes if self._counts(s)]]:
            a = obj.anchor
            if a.kind == "cell":
                continue
            if (a.r1 - a.r0 + 1) * (a.c1 - a.c0 + 1) > MAX_OBJECT_CELLS:
                self.warnings.append(f"{obj.id} covers a huge area ({a.range}); only its first cell is used")
                cells = [(a.r0, a.c0)]
            else:
                cells = [(r, c) for r in range(a.r0, a.r1 + 1) for c in range(a.c0, a.c1 + 1)]
            for rc in cells:
                self.content.add(rc)
                self.obj_at[rc].append(obj.id)
        for p in sh.pictures:  # in-cell pictures sit on a cell that already has content
            if p.anchor.kind == "cell":
                self.obj_at[(p.anchor.r0, p.anchor.c0)].append(p.id)

    @staticmethod
    def _counts(s) -> bool:
        return s.kind in ("textbox", "chart", "smartart", "ole", "form_control") or (s.kind == "shape" and bool(s.text))

    def frame_cells(self) -> set[tuple[int, int]]:
        """Cells that only carry a fill or a border; used to keep bordered boxes together, ignored when they cover most of the sheet."""
        f = set(self.d.frames)
        return f if len(f) <= FRAME_LIMIT * max(len(self.content), 1) else set()

    # --- items of a row
    def items(self, r: int) -> list[Item]:
        if r in self._items:
            return self._items[r]
        d, sh = self.d, self.sh
        out: list[Item] = []
        for c, cell in sorted(self._by_row.get(r, []), key=lambda x: x[0]):
            m = d.merge_at.get((r, c))
            if m is not None and (m.r0, m.c0) != (r, c):
                continue
            r_end, c_end = (m.r1, m.c1) if m else (r, c)
            st = d.model.styles[cell.s]
            if cell.t == "p":
                kind, text = "picture", ""
            elif cell.t == "e":
                kind, text = "error", str(cell.v)
            elif cell.v is None:
                continue
            else:
                text = str(cell.v).strip()
                kind = "number" if cell.t in ("n", "d", "b") or (cell.t == "s" and _is_number(text)) else "text"
            out.append(Item(r, c, c_end, r_end, text, kind, st.bold, st.fill_class, next((f[4:] for f in cell.flags if f.startswith("pic:")), None)))
        self._items[r] = out
        return out

    def row_items(self, r: int, c0: int, c1: int) -> list[Item]:
        return [i for i in self.items(r) if i.c <= c1 and i.c_end >= c0]

    def covered_rows_items(self, r0: int, r1: int, c0: int, c1: int) -> dict[int, list[Item]]:
        return {r: self.row_items(r, c0, c1) for r in range(r0, r1 + 1)}

    def border(self, r: int, c: int, side: str) -> bool:
        st = self.d.style(r, c)
        m = self.d.merge_at.get((r, c))
        if m is not None:  # a merged area's border lives on the cells at its edge
            if side == "L" and c != m.c0 or side == "R" and c != m.c1 or side == "T" and r != m.r0 or side == "B" and r != m.r1:
                return False
        return bool(st and side in st.border)

    def edge(self, r: int, c: int, side: str) -> bool:
        """Is there a line on this side of the cell (either neighbour may draw it)?"""
        if self.border(r, c, side):
            return True
        nr, nc, opp = {"T": (r - 1, c, "B"), "B": (r + 1, c, "T"), "L": (r, c - 1, "R"), "R": (r, c + 1, "L")}[side]
        return nr >= 1 and nc >= 1 and self.border(nr, nc, opp)


# ------------------------------------------------------------------ blocks
def find_blocks(cells: set[tuple[int, int]]) -> list[Bounds]:
    """Rectangles separated by blank rows, then blank columns. Column groups that cover (nearly) the same rows are one block with
    spacer columns; groups on different rows are separate side-by-side blocks."""
    by_row: dict[int, list[int]] = defaultdict(list)
    for r, c in cells:
        by_row[r].append(c)
    blocks: list[Bounds] = []
    for r0, r1 in _runs(list(by_row)):
        rows = range(r0, r1 + 1)
        cols = _runs([c for r in rows for c in by_row.get(r, [])])
        groups: list[list] = []  # [c0, c1, rowset]
        for c0, c1 in cols:
            rs = {r for r in rows if any(c0 <= c <= c1 for c in by_row.get(r, []))}
            if groups and len(rs & groups[-1][2]) / len(rs | groups[-1][2]) >= 0.6:
                groups[-1][1], groups[-1][2] = c1, groups[-1][2] | rs
            else:
                groups.append([c0, c1, rs])
        blocks.extend((min(rs), c0, max(rs), c1) for c0, c1, rs in groups)
    return sorted(blocks)


# ------------------------------------------------------------------ the finder
class Finder:
    def __init__(self, data: SheetData):
        self.S = Sheeter(data)
        self.d = data
        self.regions: list[Region] = []
        self._n = 0

    def run(self) -> list[Region]:
        S = self.S
        cells = set(S.content) | S.frame_cells()
        content_only = [b for b in find_blocks(cells)]
        for b in content_only:
            b = self._trim(b)
            if b is None:
                continue
            self._analyse(b, None, 0)
        self._attach_objects()
        self.S.sh.warnings.extend(self.S.warnings)
        return self.regions

    # --- bookkeeping
    def _new(self, b: Bounds, parent: str | None) -> Region:
        self._n += 1
        reg = Region(id=f"R{self._n}", r0=b[0], c0=b[1], r1=b[2], c1=b[3], parent=parent)
        self.regions.append(reg)
        if parent:
            next(r for r in self.regions if r.id == parent).children.append(reg.id)
        return reg

    def _trim(self, b: Bounds) -> Bounds | None:
        """Shrink to the rows / columns that really hold content (frames only extend a block, never decide its bounds alone)."""
        r0, c0, r1, c1 = b
        pts = [(r, c) for (r, c) in self.S.content if r0 <= r <= r1 and c0 <= c <= c1]
        if not pts:
            return None
        fr = [(r, c) for (r, c) in self.d.frames if r0 <= r <= r1 and c0 <= c <= c1]
        rows = [r for r, _ in pts + fr]
        cols = [c for _, c in pts + fr]
        return min(rows), min(cols), max(rows), max(cols)

    def _has_content(self, b: Bounds) -> bool:
        r0, c0, r1, c1 = b
        return any(r0 <= r <= r1 and c0 <= c <= c1 for (r, c) in self.S.content)

    # --- frames: bordered boxes divided into cells
    def _outer_border(self, b: Bounds) -> float:
        r0, c0, r1, c1 = b
        S = self.S
        n = hits = 0
        for c in range(c0, c1 + 1):
            n += 2
            hits += S.edge(r0, c, "T") + S.edge(r1, c, "B")
        for r in range(r0, r1 + 1):
            n += 2
            hits += S.edge(r, c0, "L") + S.edge(r, c1, "R")
        return hits / n if n else 0.0

    def _dividers(self, b: Bounds) -> tuple[list[int], list[int]]:
        """Column boundaries (after column c) and row boundaries (after row r) that carry a line along (nearly) the whole box."""
        r0, c0, r1, c1 = b
        S = self.S
        vs = [c for c in range(c0, c1) if sum(S.edge(r, c, "R") or S.edge(r, c + 1, "L") for r in range(r0, r1 + 1)) >= 0.8 * (r1 - r0 + 1)]
        hs = [r for r in range(r0, r1) if sum(S.edge(r, c, "B") or S.edge(r + 1, c, "T") for c in range(c0, c1 + 1)) >= 0.8 * (c1 - c0 + 1)]
        return vs, hs

    def _split_frame(self, b: Bounds) -> list[Bounds] | None:
        r0, c0, r1, c1 = b
        if (r1 - r0 + 1) * (c1 - c0 + 1) < 6 or self._outer_border(b) < 0.8:
            return None
        vs, hs = self._dividers(b)
        v_share = len(vs) / max(c1 - c0, 1)
        h_share = len(hs) / max(r1 - r0, 1)
        if not vs and not hs:
            return None
        if v_share >= 0.6 or h_share >= 0.6:  # lines between (nearly) every row or column: a bordered table or a ruled list, not a frame of cells
            return None
        col_cuts = [c0 - 1, *vs, c1]
        row_cuts = [r0 - 1, *hs, r1]
        cells = [(row_cuts[i] + 1, col_cuts[j] + 1, row_cuts[i + 1], col_cuts[j + 1]) for i in range(len(row_cuts) - 1) for j in range(len(col_cuts) - 1)]
        cells = [x for x in cells if self._has_content(x)]
        return cells if len(cells) >= 2 else None

    # --- title bars
    def _bar(self, r: int, b: Bounds) -> tuple[int, list[str]]:
        """How much does row r look like a title bar over the block (0..8) and why."""
        _, c0, r1, c1 = b
        S = self.S
        its = S.row_items(r, c0, c1)
        if len(its) != 1 or its[0].kind not in ("text", "number"):
            return 0, []
        it, width = its[0], c1 - c0 + 1
        ev, score = [], 0
        st = self.d.style(it.r, it.c)
        if it.span >= max(2, 0.8 * width):
            score += 2
            ev.append(f"spans {it.span} of {width} columns")
        if st and st.fill_class in ("dark", "mid"):
            score += 2
            ev.append(f"{st.fill_class} fill")
        if it.bold or (st and st.size and st.size >= 13):
            score += 1
            ev.append("bold / large text")
        if r + 1 <= r1:
            nxt = self._profile(r + it.r_end - it.r + 1, b)
            if nxt["header_like"]:
                score += 2
                ev.append("followed by a header-like row")
            elif nxt["n"] >= 2:
                score -= 1
        return score, ev

    def _profile(self, r: int, b: Bounds) -> dict:
        S = self.S
        its = S.row_items(r, b[1], b[3])
        n = len(its)
        text = sum(i.kind == "text" and not _is_number(i.text) for i in its)
        styled = sum(i.bold or i.fill in ("dark", "mid") for i in its)
        pics = sum(i.kind == "picture" for i in its)
        return {"n": n, "text_ratio": text / n if n else 0, "styled_ratio": styled / n if n else 0, "pics": pics,
                "header_like": n >= 2 and text / n >= 0.7 and styled / n >= 0.5, "items": its}

    # --- analysis driver
    def _analyse(self, b: Bounds, parent: str | None, depth: int) -> None:
        r0, c0, r1, c1 = b
        if depth < 3:
            cells = self._split_frame(b)
            if cells:
                reg = self._new(b, parent)
                reg.kind, reg.confidence = "frame", 0.8
                vs, hs = self._dividers(b)
                reg.evidence = [f"outer border + {len(vs)} vertical / {len(hs)} horizontal dividers split it into {len(cells)} cells"]
                title_rows = self._leading_title_rows(b)
                if title_rows:
                    reg.title_rows, reg.title = title_rows, self._title_text(title_rows, b)
                for cb in cells:
                    cb = self._trim(cb)
                    if cb is not None:
                        self._analyse(cb, reg.id, depth + 1)
                return
        # split stacked tables on strong title bars
        cuts = []
        for r in range(r0 + 1, r1 + 1):
            score, _ = self._bar(r, b)
            if score >= 5 and not (cuts and cuts[-1] == r - 1):
                cuts.append(r)
        if cuts:
            edges = [r0, *cuts, r1 + 1]
            parts = [(edges[i], c0, edges[i + 1] - 1, c1) for i in range(len(edges) - 1)]
            for p in parts:
                p2 = self._trim(p)
                if p2 is not None:
                    self._leaf(p2, parent)
            return
        self._leaf(b, parent)

    def _leading_title_rows(self, b: Bounds) -> list[int]:
        r0, c0, r1, c1 = b
        out = []
        r = r0
        while r <= r1:
            its = self.S.row_items(r, c0, c1)
            if len(its) == 1 and its[0].kind == "text" and (its[0].span >= max(2, 0.6 * (c1 - c0 + 1)) or self._bar(r, b)[0] >= 3):
                out.append(r)
                r = its[0].r_end + 1
            else:
                break
        return out

    def _title_text(self, rows: list[int], b: Bounds) -> str:
        return " | ".join(i.text for r in rows for i in self.S.row_items(r, b[1], b[3]) if i.text)

    # --- one leaf region
    def _leaf(self, b: Bounds, parent: str | None) -> None:
        S = self.S
        r0, c0, r1, c1 = b
        reg = self._new(b, parent)
        rows = {r: S.row_items(r, c0, c1) for r in range(r0, r1 + 1)}
        # preamble: leading single-text rows (titles, notes) when something table-like follows
        title_rows = []
        r = r0
        while r <= r1:
            its = rows[r]
            if len(its) == 1 and its[0].kind == "text" and not self._profile(r, b)["header_like"] and (its[0].span >= 2 or r == r0):
                nxt = r + (its[0].r_end - its[0].r) + 1
                if nxt <= r1 and (len(rows.get(nxt, [])) >= 2 or self._bar(r, b)[0] >= 3 or r == r0):
                    title_rows.append(r)
                    r = nxt
                    continue
            break
        body = [r for r in range(r0, r1 + 1) if r not in title_rows and rows[r]]
        reg.title_rows = title_rows
        reg.title = self._title_text(title_rows, b)
        pics_in = [p for p in S.sh.pictures if r0 <= p.anchor.r0 <= r1 and c0 <= p.anchor.c0 <= c1]
        shapes_in = [s for s in S.sh.shapes if S._counts(s) and r0 <= s.anchor.r0 <= r1 and c0 <= s.anchor.c0 <= c1]
        feats = self._features(b, body, rows, reg)
        self._classify(reg, b, body, rows, feats, pics_in, shapes_in)

    # --- headers, data rows, uniformity
    def _features(self, b: Bounds, body: list[int], rows: dict[int, list[Item]], reg: Region) -> dict:
        S = self.S
        r0, c0, r1, c1 = b
        f: dict = {"header_rows": [], "data_rows": [], "section_rows": [], "corner": "", "corner_rows": []}
        if not body:
            return f
        h0 = body[0]
        prof = self._profile(h0, b)
        header_rows: list[int] = []
        later = [self._profile(r, b) for r in body[1:4]]
        differs = bool(later) and (prof["text_ratio"] - later[0]["text_ratio"] >= 0.3 or prof["styled_ratio"] - later[0]["styled_ratio"] >= 0.4)
        if prof["n"] >= 2 and prof["text_ratio"] >= 0.7 and (prof["styled_ratio"] >= 0.5 or differs):
            header_rows = [h0]
            last = h0
            # vertical merges: a merged label only extends the header when the cells beside it are header-like too
            for it in prof["items"]:
                if it.r_end > it.r:
                    below_ok = True
                    for rr in range(it.r + 1, it.r_end + 1):
                        others = [x for x in rows.get(rr, []) if not (it.c <= x.c <= it.c_end)]
                        pr = self._profile(rr, b)
                        if not (others and pr["header_like"]):
                            below_ok = False
                    if below_ok:
                        last = max(last, it.r_end)
                    elif it.c == c0:
                        f["corner"], f["corner_rows"] = it.text, list(range(it.r, it.r_end + 1))
                        reg.evidence.append(f"merged label '{it.text[:30]}' spans rows {it.r}-{it.r_end} but the cells beside it are not header text: not part of the header")
            header_rows = list(range(h0, last + 1))
            # horizontal parents: the next row under merged header cells is a sub-header
            while len(header_rows) < 4:
                nxt = header_rows[-1] + 1
                if nxt not in rows or not any(i.span >= 2 for i in S.row_items(header_rows[-1], c0, c1)):
                    break
                pn = self._profile(nxt, b)
                if pn["header_like"]:
                    header_rows.append(nxt)
                else:
                    break
        f["header_rows"] = header_rows
        rest = [r for r in body if r not in header_rows]
        data, sections = [], []
        # a section row is one text cell spanning the table (a group label) between rows of values; it may open the body
        for i, r in enumerate(rest):
            its = rows[r]
            if not its:
                continue
            single = len(its) == 1 and its[0].kind == "text" and (its[0].span >= 2 or len(rest) > 2)
            after_multi = i + 1 < len(rest) and len(rows[rest[i + 1]]) >= 2
            if single and after_multi and (i == 0 or any(len(rows[p]) >= 2 for p in rest[:i])):
                sections.append(r)
            else:
                data.append(r)
        f["data_rows"], f["section_rows"] = data, sections
        return f

    def _headers(self, b: Bounds, header_rows: list[int]) -> list[str]:
        out = []
        for c in range(b[1], b[3] + 1):
            parts: list[str] = []
            for r in header_rows:
                t = self.d.text_at(r, c)
                if t and (not parts or parts[-1] != t):
                    parts.append(t)
            out.append(" > ".join(parts))
        return out

    # --- classification
    def _classify(self, reg: Region, b: Bounds, body: list[int], rows: dict[int, list[Item]], f: dict, pics: list, shapes: list) -> None:
        S = self.S
        r0, c0, r1, c1 = b
        header_rows, data_rows = f["header_rows"], f["data_rows"]
        n_cols = c1 - c0 + 1
        all_items = [i for r in body for i in rows[r]]
        texts = [i for i in all_items if i.kind == "text"]
        reg.header_rows, reg.data_rows, reg.section_rows = header_rows, data_rows, f["section_rows"]
        reg.corner_label = f["corner"]
        scores: dict[str, float] = {}
        ev: list[str] = []

        # uniformity of the data rows (pictures / errors do not count)
        value_rows = [r for r in data_rows if any(i.kind in ("text", "number") for i in rows[r])]
        cols_sig: dict[int, list[str]] = defaultdict(list)
        row_u: list[float] = []
        for r in value_rows:
            sigs = []
            for i in rows[r]:
                if i.kind in ("text", "number") and i.c > c0 + (0 if len(rows[r]) == 1 else 0):
                    sigs.append((i.c, _sig(i.text)))
            for c, s in sigs:
                cols_sig[c].append(s)
            body_sigs = [s for c, s in sigs if c != c0]
            if len(body_sigs) >= 2:
                row_u.append(Counter(body_sigs).most_common(1)[0][1] / len(body_sigs))
        col_u = [Counter(v).most_common(1)[0][1] / len(v) for c, v in cols_sig.items() if c != c0 and len(v) >= 2]
        u_col = sum(col_u) / len(col_u) if col_u else 0.0
        u_row = sum(row_u) / len(row_u) if row_u else 0.0
        first_col = [rows[r][0] for r in value_rows if rows[r]]
        label_share = sum(1 for i in first_col if i.c == c0 and i.kind == "text" and not _is_number(i.text)) / len(first_col) if first_col else 0
        n_value_cols = len({i.c for r in value_rows for i in rows[r] if i.c != c0})

        n_data = len(data_rows)
        pic_items = [i for r in body for i in rows[r] if i.kind == "picture"]
        id_rows = sum(1 for r in body if any(ID_TOKEN.search(i.text) for i in rows[r] if i.kind == "text"))

        if header_rows and n_data >= 2 and n_cols >= 2:
            scores["table"] = min(0.95, 0.5 + 0.4 * u_col - 0.35 * max(0.0, u_row - u_col))
            if n_value_cols >= 2:
                scores["transposed_table"] = min(0.95, 0.35 + 0.7 * max(0.0, u_row - u_col) + (0.12 if label_share >= 0.8 else 0))
            if n_value_cols == 1 and label_share >= 0.6:
                scores["key_value"] = 0.8
                ev.append("one value column under a header: a card of attribute / value pairs")
        if not header_rows and n_cols <= 4 and len(value_rows) >= 3 and label_share >= 0.8:
            scores["key_value"] = 0.78 if n_cols == 2 else 0.6
            ev.append("label column + value column, no header row")
        if id_rows >= 3 or (id_rows >= 2 and id_rows >= 0.6 * max(len(body), 1)):
            scores["requirement_list"] = 0.82
            ev.append(f"{id_rows} rows carry ID-like tokens")
        # a strip of pictures, each with a caption row (or a caption-only label row) above or below
        if (pics or pic_items) and len(texts) <= 2 * (len(pics) + len(pic_items)) + 2 and not header_rows:
            scores["picture_strip"] = 0.75
            ev.append(f"{len(pics) + len(pic_items)} picture(s) with {len(texts)} text cell(s)")
        elif pic_items and not header_rows and n_value_cols <= 1:
            pic_rows = {i.r for i in pic_items}
            caption_rows = [r for r in body if r not in pic_rows and rows[r] and all(i.kind == "text" for i in rows[r])]
            if len(caption_rows) >= len(pic_rows) - 1:
                scores["picture_strip"] = 0.72
                ev.append(f"{len(pic_rows)} picture row(s) with {len(caption_rows)} caption row(s)")
        if len(all_items) == 1 and all_items[0].kind == "text" and not pics:
            scores["title"] = 0.9
        elif n_cols <= 2 and texts and not header_rows and len(texts) >= 1 and len(texts) >= 0.8 * max(len(all_items), 1) and "key_value" not in scores:
            scores["text"] = 0.6 if len(texts) > 1 else 0.7
        if len(all_items) + len(pics) + len(shapes) <= 2 and not scores.get("title"):
            scores["stray"] = 0.55
        if shapes and not texts and not pics and not scores:
            scores["text"] = 0.55
            ev.append("only shapes / text boxes")
        if not scores:
            scores["unknown"] = 0.3

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        reg.kind, reg.confidence = ranked[0][0], round(ranked[0][1], 2)
        reg.alternatives = [(k, round(v, 2)) for k, v in ranked[1:3]]
        reg.evidence = [*reg.evidence, *ev]
        if header_rows:
            reg.evidence.append(f"header row(s) {header_rows}")
        if reg.kind in ("table", "transposed_table"):
            reg.evidence.append(f"uniformity down columns {u_col:.2f} vs along rows {u_row:.2f}")
        reg.orientation = {"table": "rows", "transposed_table": "columns", "requirement_list": "rows", "key_value": "rows"}.get(reg.kind, "none")
        if reg.kind in ("table", "transposed_table", "key_value"):
            reg.headers = self._headers(b, header_rows)
        if reg.kind in ("table", "key_value") and label_share >= 0.8 and len({i.text for i in first_col}) >= 0.8 * max(len(first_col), 1):
            reg.key_col = c0
        if f["corner"]:
            reg.corner_label = f["corner"]
        close = len(ranked) > 1 and ranked[0][1] - ranked[1][1] < 0.15
        if reg.confidence < 0.7 or close or (len(value_rows) < 2 and reg.kind in ("table", "transposed_table")):
            reg.needs_llm = True
        if pic_items:
            reg.evidence.append(f"{len(pic_items)} in-cell picture(s) inside the table")

    # --- objects -> regions
    def _deepest(self, r: int, c: int) -> Region | None:
        best = None
        for reg in self.regions:
            if reg.r0 <= r <= reg.r1 and reg.c0 <= c <= reg.c1 and (best is None or (reg.r1 - reg.r0 + 1) * (reg.c1 - reg.c0 + 1) <= (best.r1 - best.r0 + 1) * (best.c1 - best.c0 + 1)):
                best = reg
        return best

    def _attach_objects(self) -> None:
        S, sh = self.S, self.S.sh
        for obj in [*sh.pictures, *sh.shapes]:
            a = obj.anchor
            r, c = (a.r0 + a.r1) // 2, (a.c0 + a.c1) // 2
            reg = self._deepest(a.r0, a.c0) or self._deepest(r, c)
            if reg is None or (obj.__class__.__name__ == "Shape" and not S._counts(obj)):
                continue
            obj.region = reg.id
            (reg.pictures if obj.__class__.__name__ == "Picture" else reg.shapes).append(obj.id)
        for p in sh.pictures:
            p.neighbours = self._neighbours(p)

    def _neighbours(self, p) -> dict:
        S = self.S
        reg = next((r for r in self.regions if r.id == p.region), None)
        a = p.anchor
        n: dict = {}
        if reg is None:
            return n
        top = reg
        while top.parent:
            top = next(x for x in self.regions if x.id == top.parent)
        n["box_title"] = top.title or reg.title
        if reg.parent and reg.title:
            n["sub_box_title"] = reg.title
        n["region"] = {"id": reg.id, "kind": reg.kind, "range": reg.range}
        # column header (what is this column about) and row label (what is this row about)
        if reg.kind in ("table", "transposed_table", "key_value") and reg.headers:
            h = reg.headers[min(max(a.c0 - reg.c0, 0), len(reg.headers) - 1)]
            if h:
                n["column_header"] = h
        label = ""
        for r in range(a.r0, a.r1 + 1):
            first = next((i for i in S.row_items(r, reg.c0, reg.c1) if i.c < a.c0 and i.kind == "text"), None)
            if first:
                label = first.text
                break
        if not label and reg.corner_label and a.r0 in range(reg.r0, reg.r1 + 1) and any(a.r0 > r for r in reg.header_rows):
            label = reg.corner_label
        if label:
            n["row_label"] = label[:120]
        for key, rr in (("caption_above", a.r0 - 1), ("caption_below", a.r1 + 1)):
            if reg.r0 <= rr <= reg.r1:
                t = [i.text for i in S.row_items(rr, a.c0, a.c1) if i.kind == "text" and i.text]
                if t:
                    n[key] = " | ".join(t)[:200]
        same = [i.text for r in range(a.r0, a.r1 + 1) for i in S.row_items(r, reg.c0, reg.c1) if i.kind == "text" and i.text and not (a.c0 <= i.c <= a.c1)]
        if same:
            n["same_row"] = [s[:160] for s in same[:6]]
        near_shapes = [s.text[:160] for s in S.sh.shapes if s.text and s.region == reg.id and abs(s.anchor.r0 - a.r0) <= 2]
        if near_shapes:
            n["text_boxes"] = near_shapes[:3]
        if p.alt:
            n["alt"] = p.alt
        return n


def find_regions(data: SheetData) -> list[Region]:
    """Entry point: regions of one sheet (ids R1.. in reading order of discovery)."""
    reg = Finder(data).run()
    data.model.regions = reg
    return reg
