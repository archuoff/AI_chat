"""What openpyxl cannot see, read straight from the XML parts.

* Place-in-Cell pictures ("rich values"): cell attribute vm -> xl/metadata.xml -> xl/richData/rdrichvalue.xml -> richValueRel -> media
* =IMAGE("url") formulas
* every drawing object with its real anchor: pictures, text boxes / shapes, groups (children placed through the group transform), connectors,
  charts, SmartArt (flagged), embedded OLE objects, form controls (counted)
* threaded comments
All of it comes back as Picture / Shape / Comment records; nothing here changes a cell value.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

from .geometry import EMU_PX, Geometry
from .grid import SheetData
from .media import MediaRegistry
from .model import Anchor, Comment, Picture, Shape
from .package import NS_REL, Package, local

IMAGE_FORMULA = re.compile(r"IMAGE\(\s*\"([^\"]*)\"", re.IGNORECASE)


# ------------------------------------------------------------------ workbook / sheets
def sheet_parts(pkg: Package) -> dict[str, str]:
    """sheet name -> part path (xl/worksheets/sheet1.xml)."""
    root = pkg.xml("xl/workbook.xml")
    rels = pkg.rels("xl/workbook.xml")
    out: dict[str, str] = {}
    if root is None:
        return out
    for sh in root.iter("{*}sheet"):
        rel = rels.get(sh.get(f"{{{NS_REL}}}id", ""))
        if rel is not None and not rel.external:
            out[sh.get("name", "")] = rel.target
    return out


# ------------------------------------------------------------------ rich values (Place in Cell)
@dataclass
class RichImage:
    part: str | None  # media part inside the zip
    alt: str = ""
    kind: str = "_localImage"
    problem: str = ""


@dataclass
class RichIndex:
    vm_to_rv: dict[int, int] = field(default_factory=dict)
    rvs: list[RichImage | None] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def image(self, vm: int) -> RichImage | None:
        i = self.vm_to_rv.get(vm)
        return self.rvs[i] if i is not None and i < len(self.rvs) else None


def read_richvalues(pkg: Package) -> RichIndex:
    idx = RichIndex()
    meta = pkg.xml("xl/metadata.xml")
    if meta is None:
        return idx
    types = [t.get("name", "") for t in meta.iterfind("{*}metadataTypes/{*}metadataType")]
    if "XLRICHVALUE" not in types:
        return idx
    rich_t = types.index("XLRICHVALUE") + 1
    future: list[int | None] = []
    for fm in meta.iterfind("{*}futureMetadata"):
        if fm.get("name") == "XLRICHVALUE":
            for bk in fm.iterfind("{*}bk"):
                rvb = next(bk.iter("{*}rvb"), None)
                future.append(int(rvb.get("i")) if rvb is not None and rvb.get("i") is not None else None)
    vm_bk = meta.find("{*}valueMetadata")
    for n, bk in enumerate(vm_bk.iterfind("{*}bk") if vm_bk is not None else [], start=1):
        for rc in bk.iterfind("{*}rc"):
            if rc.get("t") == str(rich_t) and rc.get("v") is not None and int(rc.get("v")) < len(future) and future[int(rc.get("v"))] is not None:
                idx.vm_to_rv[n] = future[int(rc.get("v"))]
    # structures: ordered key names per structure
    structs: list[tuple[str, list[str]]] = []
    root = pkg.xml("xl/richData/rdrichvaluestructure.xml")
    for s in root.iterfind("{*}s") if root is not None else []:
        structs.append((s.get("t", ""), [k.get("n", "") for k in s.iterfind("{*}k")]))
    # relation list of richValueRel (image targets)
    rel_part = next((n for n in sorted(pkg.names) if n.startswith("xl/richData/richValueRel") and n.endswith(".xml") and "/_rels/" not in n), None)
    rel_ids: list[str] = []
    if rel_part:
        rr = pkg.xml(rel_part)
        rel_ids = [e.get(f"{{{NS_REL}}}id", "") for e in (rr if rr is not None else []) if local(e) == "rel"]
        rels = pkg.rels(rel_part)
    else:
        rels = {}
    values = pkg.xml("xl/richData/rdrichvalue.xml")
    for rv in values.iterfind("{*}rv") if values is not None else []:
        s_idx = int(rv.get("s", "0"))
        stype, keys = structs[s_idx] if s_idx < len(structs) else ("", [])
        vals = [(v.text or "") for v in rv.iterfind("{*}v")]
        get = lambda name: vals[keys.index(name)] if name in keys and keys.index(name) < len(vals) else None  # noqa: E731
        ident = get("_rvRel:LocalImageIdentifier")
        if ident is None:  # a rich value that is not a local picture (web image, linked data type ...)
            idx.rvs.append(RichImage(None, kind=stype, problem=f"rich value of type {stype or '?'} is not a local picture"))
            continue
        try:
            rid = rel_ids[int(ident)]
            target = rels[rid].target
        except (IndexError, KeyError, ValueError):
            idx.rvs.append(RichImage(None, kind=stype, problem="picture relation not found"))
            continue
        idx.rvs.append(RichImage(target, alt=(get("Text") or "").strip(), kind=stype))
    return idx


# ------------------------------------------------------------------ anchors
def _marker(m) -> tuple[int, int, int, int]:
    g = lambda t: int(float(m.findtext(f"{{*}}{t}") or 0))  # noqa: E731
    return g("col") + 1, g("colOff"), g("row") + 1, g("rowOff")  # col, colOff, row, rowOff (1-based cell, EMU offsets)


def rect_to_anchor(geo: Geometry, x: float, y: float, w: float, h: float, kind: str = "absolute") -> Anchor:
    """A rectangle in EMU (sheet coordinates) -> the cells it covers."""
    xp, yp = x / EMU_PX, y / EMU_PX
    wp, hp = max(w / EMU_PX, 1), max(h / EMU_PX, 1)
    c0, r0 = geo.col_at(int(xp)), geo.row_at(int(yp))
    c1, r1 = geo.col_at(int(xp + wp - 1)), geo.row_at(int(yp + hp - 1))
    return Anchor(kind, r0, c0, max(r0, r1), max(c0, c1), dr0=int((yp - geo.top(r0)) * EMU_PX), dc0=int((xp - geo.left(c0)) * EMU_PX),
                  w=int(w), h=int(h), x=int(x), y=int(y))


def read_anchor(a, geo: Geometry) -> Anchor | None:
    kind = local(a)
    frm, to, ext, pos = a.find("{*}from"), a.find("{*}to"), a.find("{*}ext"), a.find("{*}pos")
    if kind == "twoCellAnchor" and frm is not None and to is not None:
        c0, dc0, r0, dr0 = _marker(frm)
        c1, dc1, r1, dr1 = _marker(to)
        x0, y0 = geo.left(c0) * EMU_PX + dc0, geo.top(r0) * EMU_PX + dr0
        x1, y1 = geo.left(c1) * EMU_PX + dc1, geo.top(r1) * EMU_PX + dr1
        last_c = c1 - 1 if (dc1 == 0 and c1 > c0) else c1  # an object that ends exactly on a gridline does not touch the next cell
        last_r = r1 - 1 if (dr1 == 0 and r1 > r0) else r1
        return Anchor("twoCell", r0, c0, last_r, last_c, dr0, dc0, dr1, dc1, w=max(x1 - x0, 0), h=max(y1 - y0, 0), x=x0, y=y0)
    if kind == "oneCellAnchor" and frm is not None and ext is not None:
        c0, dc0, r0, dr0 = _marker(frm)
        x0, y0 = geo.left(c0) * EMU_PX + dc0, geo.top(r0) * EMU_PX + dr0
        an = rect_to_anchor(geo, x0, y0, int(ext.get("cx", 0)), int(ext.get("cy", 0)), "oneCell")
        an.dr0, an.dc0 = dr0, dc0
        return an
    if kind == "absoluteAnchor" and pos is not None and ext is not None:
        return rect_to_anchor(geo, int(pos.get("x", 0)), int(pos.get("y", 0)), int(ext.get("cx", 0)), int(ext.get("cy", 0)))
    return None


# ------------------------------------------------------------------ drawings
@dataclass
class _Ctx:
    pkg: Package
    sheet_data: SheetData
    geo: Geometry
    media: MediaRegistry
    rels: dict
    part: str
    pictures: list[Picture] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)
    z: int = 0
    n: int = 0

    def next_id(self, prefix: str) -> str:
        self.n += 1
        return f"{self.sheet_data.model.index}-{prefix}{self.n}"


def _cnv(el, container: str) -> dict[str, str]:
    c = el.find(f"{{*}}{container}/{{*}}cNvPr")
    return {k: (c.get(k) or "") for k in ("id", "name", "descr", "title")} if c is not None else {"id": "", "name": "", "descr": "", "title": ""}


def _text(el) -> str:
    tx = el.find("{*}txBody")
    if tx is None:
        return ""
    lines = []
    for p in tx.iterfind("{*}p"):
        parts = []
        for node in p:
            if local(node) == "r":
                parts.append(node.findtext("{*}t") or "")
            elif local(node) == "br":
                parts.append("\n")
            elif local(node) == "fld":
                parts.append(node.findtext("{*}t") or "")
        lines.append("".join(parts))
    return "\n".join(lines).strip()


def _xfrm(el):
    """(off x, off y, ext cx, ext cy, chOff x, chOff y, chExt cx, chExt cy) of the object's transform, or None."""
    x = next((e for e in (el.find("{*}spPr/{*}xfrm"), el.find("{*}grpSpPr/{*}xfrm"), el.find("{*}xfrm")) if e is not None), None)
    if x is None:
        return None
    off, ext = x.find("{*}off"), x.find("{*}ext")
    if off is None or ext is None:
        return None
    ch_off, ch_ext = x.find("{*}chOff"), x.find("{*}chExt")
    g = lambda e, k: int(float(e.get(k, 0))) if e is not None else 0  # noqa: E731
    return (g(off, "x"), g(off, "y"), g(ext, "cx"), g(ext, "cy"), g(ch_off, "x"), g(ch_off, "y"), g(ch_ext, "cx"), g(ch_ext, "cy"))


def _walk(el, ctx: _Ctx, anchor: Anchor, group: str | None = None, gx=None) -> None:
    """One drawing object (or the objects inside an AlternateContent / group wrapper)."""
    name = local(el)
    if name == "AlternateContent":
        choice = next((c for c in el if local(c) == "Choice"), None) or next(iter(el), None)
        for child in choice if choice is not None else []:
            _walk(child, ctx, anchor, group, gx)
        return

    def child_anchor() -> Anchor:
        """Inside a group the child's own transform is mapped through the group's; otherwise the drawing anchor stands."""
        if gx is None:
            return anchor
        xf = _xfrm(el)
        if xf is None:
            return anchor
        ox, oy, cx, cy, _, _, _, _ = xf
        gox, goy, gcx, gcy, chx, chy, chcx, chcy = gx
        sx, sy = (gcx / chcx if chcx else 1.0), (gcy / chcy if chcy else 1.0)
        return rect_to_anchor(ctx.geo, gox + (ox - chx) * sx, goy + (oy - chy) * sy, cx * sx, cy * sy)

    ctx.z += 1
    if name == "pic":
        nv = _cnv(el, "nvPicPr")
        blip = next(el.iter("{*}blip"), None)
        rid = blip.get(f"{{{NS_REL}}}embed") if blip is not None else None
        link = blip.get(f"{{{NS_REL}}}link") if blip is not None else None
        rel = ctx.rels.get(rid or "")
        info = ctx.media.get(rel.target) if rel is not None and not rel.external else None
        pic = Picture(id=ctx.next_id("p"), kind="floating", source="drawing", anchor=child_anchor(), name=nv["name"], alt=nv["descr"] or nv["title"],
                      in_group=group, z=ctx.z)
        if info is not None:
            pic.media, pic.ext, pic.sha256, pic.width, pic.height, pic.bytes = info.name, info.ext, info.sha256, info.width, info.height, info.bytes
            pic.flags += info.flags
        elif link or (rel is not None and rel.external):
            pic.flags.append("linked_not_embedded")
            pic.url = link and ctx.rels.get(link).target if link and ctx.rels.get(link) else ""
        else:
            pic.flags.append("missing_media")
        ctx.pictures.append(pic)
    elif name == "sp":
        nv = _cnv(el, "nvSpPr")
        txbox = el.find("{*}nvSpPr/{*}cNvSpPr")
        kind = "textbox" if (txbox is not None and txbox.get("txBox") == "1") or _text(el) else "shape"
        sh = Shape(id=ctx.next_id("s"), kind=kind, anchor=child_anchor(), name=nv["name"], text=_text(el), alt=nv["descr"])
        if el.find("{*}spPr/{*}blipFill") is not None:
            sh.flags.append("image_fill")
        ctx.shapes.append(sh)
    elif name == "cxnSp":
        nv = _cnv(el, "nvCxnSpPr")
        ctx.shapes.append(Shape(id=ctx.next_id("s"), kind="connector", anchor=child_anchor(), name=nv["name"]))
    elif name == "grpSp":
        nv = _cnv(el, "nvGrpSpPr")
        gid = ctx.next_id("g")
        xf = _xfrm(el)
        mapped = xf
        if gx is not None and xf is not None:  # a group inside a group: map its own box through the parent first
            gox, goy, gcx, gcy, chx, chy, chcx, chcy = gx
            sx, sy = (gcx / chcx if chcx else 1.0), (gcy / chcy if chcy else 1.0)
            mapped = (gox + (xf[0] - chx) * sx, goy + (xf[1] - chy) * sy, xf[2] * sx, xf[3] * sy, xf[4], xf[5], xf[6], xf[7])
        ga = child_anchor() if xf is not None else anchor
        ctx.shapes.append(Shape(id=gid, kind="group", anchor=ga, name=nv["name"], alt=nv["descr"]))
        for child in el:
            if local(child) in ("pic", "sp", "grpSp", "cxnSp", "graphicFrame", "AlternateContent"):
                _walk(child, ctx, anchor if mapped is None else ga, gid, mapped)
    elif name == "graphicFrame":
        nv = _cnv(el, "nvGraphicFramePr")
        gd = next(el.iter("{*}graphicData"), None)
        uri = (gd.get("uri") if gd is not None else "") or ""
        if uri.endswith("/chart"):
            ch = next(gd.iter("{*}chart"), None)
            rel = ctx.rels.get(ch.get(f"{{{NS_REL}}}id", "")) if ch is not None else None
            ctx.shapes.append(Shape(id=ctx.next_id("c"), kind="chart", anchor=child_anchor(), name=nv["name"], alt=nv["descr"],
                                    detail=_chart(ctx.pkg, rel.target) if rel is not None else {}))
        elif uri.endswith("/diagram"):
            ctx.shapes.append(Shape(id=ctx.next_id("s"), kind="smartart", anchor=child_anchor(), name=nv["name"], flags=["not_readable"]))
        else:
            ctx.shapes.append(Shape(id=ctx.next_id("s"), kind="shape", anchor=child_anchor(), name=nv["name"], detail={"uri": uri}, flags=["not_readable"]))
    elif name == "contentPart":
        ctx.shapes.append(Shape(id=ctx.next_id("s"), kind="shape", anchor=anchor, name="ink / content part", flags=["not_readable"]))


def _chart(pkg: Package, part: str) -> dict:
    root = pkg.xml(part)
    if root is None:
        return {}
    plot = next(root.iter("{*}plotArea"), None)
    types = [local(e) for e in plot if local(e).endswith("Chart")] if plot is not None else []
    title = next((t for t in root.iterfind("{*}chart/{*}title")), None)
    title_text = "".join(t.text or "" for t in title.iter("{*}t")) if title is not None else ""
    series = []
    for ser in root.iter("{*}ser"):
        series.append({"name": next((f.text for f in ser.iterfind("{*}tx//{*}f")), ""), "categories": next((f.text for f in ser.iterfind("{*}cat//{*}f")), ""),
                       "values": next((f.text for f in ser.iterfind("{*}val//{*}f")), "")})
    return {"types": types, "title": title_text.strip(), "series": series}


# ------------------------------------------------------------------ per sheet
def read_sheet_objects(pkg: Package, data: SheetData, part: str, rich: RichIndex, media: MediaRegistry) -> None:
    sh = data.model
    geo = Geometry(sh)
    rels = pkg.rels(part)

    # 1) cells with a rich value or an IMAGE() formula (one streaming pass over the sheet XML)
    ctx_n = 0
    for _, c in pkg.iterparse(part, "c"):
        vm = c.get("vm")
        f = next(c.iterfind("{*}f"), None)
        ftxt = f.text if f is not None and f.text else ""
        m = IMAGE_FORMULA.search(ftxt)
        if vm or m:
            col, row = coordinate_from_string(c.get("r"))
            r, cc = row, column_index_from_string(col)
            merge = data.merge_at.get((r, cc))
            r0, c0, r1, c1 = (merge.r0, merge.c0, merge.r1, merge.c1) if merge else (r, cc, r, cc)
            ctx_n += 1
            pic = Picture(id=f"{sh.index}-i{ctx_n}", kind="cell", source="richvalue", anchor=Anchor("cell", r0, c0, r1, c1), url=m.group(1) if m else "")
            image = rich.image(int(vm)) if vm else None
            info = media.get(image.part) if image is not None and image.part else None
            if info is not None:
                pic.media, pic.ext, pic.sha256, pic.width, pic.height, pic.bytes = info.name, info.ext, info.sha256, info.width, info.height, info.bytes
                pic.alt = image.alt
                pic.flags += info.flags
            elif m:
                pic.kind, pic.source = "linked", "image_formula"
                pic.flags.append("linked_not_embedded")
            else:
                pic.flags.append(image.problem if image is not None and image.problem else "rich_value_unresolved")
            sh.pictures.append(pic)
            cell = data.cells.get((r, cc))
            if cell is not None:
                cell.flags = [x for x in cell.flags if not x.startswith("error:")] + ["picture", f"pic:{pic.id}"]
                cell.t, cell.v = "p", None
            else:
                from .model import Cell

                data.cells[(r, cc)] = Cell(r=r, c=cc, t="p", flags=["picture", f"pic:{pic.id}"])
        c.clear()
        while c.getprevious() is not None:
            del c.getparent()[0]

    # 2) embedded OLE objects
    root = pkg.xml(part) if pkg.size(part) < 25_000_000 else None
    for n, ole in enumerate(root.iter("{*}oleObject") if root is not None else [], start=1):
        rel = rels.get(ole.get(f"{{{NS_REL}}}id", ""))
        a = ole.find(".//{*}anchor")
        frm, to = (a.find("{*}from"), a.find("{*}to")) if a is not None else (None, None)
        if frm is not None and to is not None:
            c0, dc0, r0, dr0 = _marker(frm)
            c1, dc1, r1, dr1 = _marker(to)
            anchor = Anchor("twoCell", r0, c0, r1, c1, dr0, dc0, dr1, dc1)
        else:
            anchor = Anchor("absolute", 1, 1, 1, 1)
            sh.warnings.append(f"embedded object {n} has no anchor")
        sh.shapes.append(Shape(id=f"{sh.index}-o{n}", kind="ole", anchor=anchor, name=ole.get("progId", ""),
                               detail={"progId": ole.get("progId", ""), "target": rel.target if rel else ""}, flags=["embedded_object"]))

    # 3) the drawing: pictures, text boxes, groups, charts ...
    for rel in rels.values():
        if rel.type != "drawing" or rel.external:
            continue
        droot = pkg.xml(rel.target)
        if droot is None:
            sh.warnings.append(f"drawing {rel.target} could not be read")
            continue
        ctx = _Ctx(pkg, data, geo, media, pkg.rels(rel.target), rel.target)
        ctx.n = len(sh.pictures) + len(sh.shapes)
        for a in droot:
            if local(a) not in ("twoCellAnchor", "oneCellAnchor", "absoluteAnchor"):
                continue
            anchor = read_anchor(a, geo)
            if anchor is None:
                sh.warnings.append(f"a drawing object has an anchor we cannot read ({local(a)})")
                continue
            for child in a:
                if local(child) in ("pic", "sp", "grpSp", "cxnSp", "graphicFrame", "AlternateContent", "contentPart"):
                    _walk(child, ctx, anchor)
        sh.pictures.extend(ctx.pictures)
        sh.shapes.extend(ctx.shapes)

    # 4) legacy form controls (counted) and threaded comments
    for rel in rels.values():
        if rel.type == "vmlDrawing" and not rel.external and pkg.has(rel.target):
            controls = len(re.findall(rb'ObjectType="(?!Note)[A-Za-z]+"', pkg.read(rel.target)))
            if controls:
                sh.shapes.append(Shape(id=f"{sh.index}-f", kind="form_control", anchor=Anchor("absolute", 1, 1, 1, 1), name=f"{controls} form control(s)",
                                       flags=["not_readable"], detail={"count": controls}))
        if rel.type == "threadedComment" and not rel.external:
            _threaded(pkg, rel.target, sh)
    _count_repeats(sh)


def _threaded(pkg: Package, part: str, sh) -> None:
    root = pkg.xml(part)
    if root is None:
        return
    people = {}
    persons = pkg.xml("xl/persons/person.xml")
    for p in persons if persons is not None else []:
        people[p.get("id", "")] = p.get("displayName", "")
    replies: dict[str, int] = {}
    tops = []
    for t in root.iterfind("{*}threadedComment"):
        if t.get("parentId"):
            replies[t.get("parentId")] = replies.get(t.get("parentId"), 0) + 1
        else:
            tops.append(t)
    # the old-style placeholder text of the same comment would be a duplicate
    refs = {t.get("ref") for t in tops}
    sh.comments[:] = [c for c in sh.comments if not (c.ref in refs and c.text.startswith("[Threaded comment]"))]
    for t in tops:
        sh.comments.append(Comment(ref=t.get("ref", ""), author=people.get(t.get("personId", ""), ""), text=(t.findtext("{*}text") or "").strip(),
                                   kind="threaded", replies=replies.get(t.get("id", ""), 0)))


def _count_repeats(sh) -> None:
    counts: dict[str, int] = {}
    for p in sh.pictures:
        if p.sha256:
            counts[p.sha256] = counts.get(p.sha256, 0) + 1
    for p in sh.pictures:
        if p.sha256 and counts[p.sha256] > 1:
            p.flags.append(f"repeated:{counts[p.sha256]}")
