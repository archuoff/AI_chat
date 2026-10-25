"""The "sheet model": everything we can read from a workbook, as plain JSON-friendly dataclasses.

One address convention everywhere: rows and columns are 1-based, ranges are inclusive, `a1` strings are for people.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from openpyxl.utils import get_column_letter


def a1(r: int, c: int) -> str:
    return f"{get_column_letter(c)}{r}"


def rng(r0: int, c0: int, r1: int, c1: int) -> str:
    return a1(r0, c0) if (r0, c0) == (r1, c1) else f"{a1(r0, c0)}:{a1(r1, c1)}"


@dataclass
class Style:
    id: int
    fill: str | None = None  # "RRGGBB" or "theme:N[+tint]"
    fill_class: str = "none"  # none | light | mid | dark (luminance guess, used for title-bar detection)
    bold: bool = False
    italic: bool = False
    size: float | None = None
    color: str | None = None
    halign: str | None = None
    valign: str | None = None
    wrap: bool = False
    border: str = ""  # sides that have a line: any of "TRBL"
    numfmt: str = "General"


@dataclass
class Cell:
    r: int
    c: int
    v: Any = None  # cached value (dates as ISO text)
    t: str = "s"  # s text | n number | b bool | d date | e error | f formula without cached value
    d: str | None = None  # display text when a number format changes how it reads (12% / 2026-03-01 / 1,200)
    s: int = 0  # style id
    f: str | None = None  # formula text
    flags: list[str] = field(default_factory=list)  # merged_master | merged_covered | hidden | picture | comment | link | error:<kind> | formula_no_cache
    merge: str | None = None  # range of the merged area this cell belongs to
    eff: Any = None  # effective value for covered merged cells (the master's value)

    @property
    def a1(self) -> str:
        return a1(self.r, self.c)


@dataclass
class Merge:
    r0: int
    c0: int
    r1: int
    c1: int

    @property
    def range(self) -> str:
        return rng(self.r0, self.c0, self.r1, self.c1)


@dataclass
class Anchor:
    kind: str  # cell (inside one cell) | oneCell | twoCell | absolute
    r0: int
    c0: int
    r1: int  # last cell the object touches (computed from sizes when the file stores only a size)
    c1: int
    dr0: int = 0  # offsets inside the first cell, EMU
    dc0: int = 0
    dr1: int = 0
    dc1: int = 0
    w: int = 0  # size in EMU (0 when unknown)
    h: int = 0
    x: int = 0  # absolute position in EMU (absolute anchors / computed top-left)
    y: int = 0

    @property
    def range(self) -> str:
        return rng(self.r0, self.c0, self.r1, self.c1)


@dataclass
class Picture:
    id: str
    kind: str  # cell (Place in Cell) | floating | linked (=IMAGE(url), not embedded) | web
    source: str  # richvalue | drawing | image_formula
    anchor: Anchor
    media: str | None = None  # file name inside media/
    ext: str = ""
    sha256: str = ""
    width: int = 0  # pixels of the picture itself
    height: int = 0
    bytes: int = 0
    name: str = ""
    alt: str = ""
    url: str = ""
    in_group: str | None = None
    z: int = 0  # drawing order
    region: str | None = None
    neighbours: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)  # emf / svg kept as is, missing_media, repeated ...


@dataclass
class Shape:
    id: str
    kind: str  # textbox | shape | connector | group | smartart | chart | ole | form_control
    anchor: Anchor
    name: str = ""
    text: str = ""
    alt: str = ""
    detail: dict[str, Any] = field(default_factory=dict)  # chart: types / title / series refs; ole: progId / target
    region: str | None = None
    flags: list[str] = field(default_factory=list)


@dataclass
class Comment:
    ref: str
    author: str = ""
    text: str = ""
    kind: str = "legacy"  # legacy | threaded
    replies: int = 0


@dataclass
class Link:
    ref: str
    target: str = ""  # url / file
    location: str = ""  # place inside the workbook
    tip: str = ""


@dataclass
class Region:
    id: str
    r0: int
    c0: int
    r1: int
    c1: int
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    kind: str = "unknown"  # title | table | transposed_table | key_value | picture_strip | requirement_list | text | frame | stray | unknown
    confidence: float = 0.0
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    title: str = ""
    title_rows: list[int] = field(default_factory=list)
    header_rows: list[int] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)  # one name per column (multi-level joined with " > ")
    orientation: str = "none"  # rows (record per row) | columns (record per column) | none
    key_col: int | None = None
    corner_label: str = ""  # merged label that sits above / beside the first column
    data_rows: list[int] = field(default_factory=list)
    section_rows: list[int] = field(default_factory=list)
    pictures: list[str] = field(default_factory=list)
    shapes: list[str] = field(default_factory=list)
    needs_llm: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def range(self) -> str:
        return rng(self.r0, self.c0, self.r1, self.c1)


@dataclass
class Sheet:
    name: str
    index: int
    state: str = "visible"  # visible | hidden | veryHidden
    max_row: int = 0
    max_col: int = 0
    dims: str = ""
    non_empty: int = 0
    default_col_w: float = 9.140625  # stored width units (64 px)
    default_row_h: float = 15.0
    col_w: dict[int, float] = field(default_factory=dict)  # only columns that differ from the default
    row_h: dict[int, float] = field(default_factory=dict)
    hidden_rows: list[int] = field(default_factory=list)
    hidden_cols: list[int] = field(default_factory=list)
    outline_rows: dict[int, int] = field(default_factory=dict)
    freeze: str = ""
    autofilter: str = ""
    merges: list[Merge] = field(default_factory=list)
    styles: list[Style] = field(default_factory=list)
    pictures: list[Picture] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)  # Excel "Format as Table" objects
    validations: list[dict[str, Any]] = field(default_factory=list)
    defined_names: list[dict[str, str]] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    inventory: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Workbook:
    file: str
    sheets: list[Sheet] = field(default_factory=list)
    defined_names: list[dict[str, str]] = field(default_factory=list)
    parts: dict[str, int] = field(default_factory=dict)  # zip part groups -> count (richData, media, embeddings ...)
    warnings: list[str] = field(default_factory=list)


_ALWAYS = {"v", "eff", "r", "c", "id"}  # a cell value of 0 / False is data, never noise


def _empty(x: Any) -> bool:
    return x is None or x is False or x == "" or x == [] or x == {} or (isinstance(x, (int, float)) and not isinstance(x, bool) and x == 0)


def to_json(obj: Any) -> Any:
    """dataclasses -> dicts, dropping empty / default noise (None, "", [], {}, 0, False) so the JSON stays small."""
    if is_dataclass(obj):
        return {k: to_json(v) for k, v in asdict(obj).items() if (k in _ALWAYS and not (k == "eff" and v is None)) or (k not in _ALWAYS and not _empty(v))}
    if isinstance(obj, dict):
        return {str(k): to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    return obj
