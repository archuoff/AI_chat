"""Excel "Place in Cell" pictures (rich values), which openpyxl cannot read.

Excel stores such a picture as a cell with `vm="N"` and the cached value #VALUE!. The picture itself sits in
    cell vm -> xl/metadata.xml -> xl/richData/rdrichvalue.xml -> richValueRel.xml (+ .rels) -> xl/media/imageN.*
`=IMAGE("url")` cells are linked pictures (they carry a rich value too): nothing is stored, only the address is kept.

`read_incell_pictures(path)` -> {sheet name: {(row, col): InCellPicture}}. A file without rich data costs only one
look into the zip directory.
"""
from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PARSER = dict(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=True)
_IMAGE_FORMULA = re.compile(r"IMAGE\(\s*\"([^\"]*)\"", re.IGNORECASE)
MAX_PICTURE_BYTES = 25_000_000


@dataclass
class InCellPicture:
    row: int
    col: int
    data: bytes | None = None
    ext: str = "png"
    alt: str = ""
    url: str = ""  # =IMAGE("url"): linked, not stored in the file
    problem: str = ""  # why the bytes are missing


@dataclass
class _Rich:
    vm_to_rv: dict[int, int] = field(default_factory=dict)
    rvs: list[tuple[str | None, str, str]] = field(default_factory=list)  # (media part, alt text, problem)


def _xml(z: zipfile.ZipFile, name: str):
    try:
        return etree.fromstring(z.read(name), etree.XMLParser(recover=True, **_PARSER))
    except (KeyError, etree.XMLSyntaxError):
        return None


def _rels(z: zipfile.ZipFile, part: str) -> dict[str, str]:
    root = _xml(z, posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels"))
    out: dict[str, str] = {}
    for r in root if root is not None else []:
        if isinstance(r.tag, str) and r.tag.endswith("Relationship") and r.get("TargetMode") != "External":
            target = r.get("Target", "")
            out[r.get("Id", "")] = target.lstrip("/") if target.startswith("/") else posixpath.normpath(
                posixpath.join(posixpath.dirname(part), target))
    return out


def _rich_index(z: zipfile.ZipFile, names: set[str]) -> _Rich:
    rich = _Rich()
    meta = _xml(z, "xl/metadata.xml") if "xl/metadata.xml" in names else None
    if meta is None:
        return rich
    types = [t.get("name", "") for t in meta.iterfind("{*}metadataTypes/{*}metadataType")]
    if "XLRICHVALUE" not in types:
        return rich
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
            v = rc.get("v")
            if rc.get("t") == str(rich_t) and v is not None and int(v) < len(future) and future[int(v)] is not None:
                rich.vm_to_rv[n] = future[int(v)]
    structs: list[tuple[str, list[str]]] = []
    root = _xml(z, "xl/richData/rdrichvaluestructure.xml") if "xl/richData/rdrichvaluestructure.xml" in names else None
    for s in root.iterfind("{*}s") if root is not None else []:
        structs.append((s.get("t", ""), [k.get("n", "") for k in s.iterfind("{*}k")]))
    rel_part = next((n for n in sorted(names) if n.startswith("xl/richData/richValueRel") and n.endswith(".xml") and "/_rels/" not in n), None)
    rel_ids: list[str] = []
    rels: dict[str, str] = {}
    if rel_part:
        rr = _xml(z, rel_part)
        rel_ids = [e.get(f"{{{NS_REL}}}id", "") for e in (rr if rr is not None else []) if isinstance(e.tag, str) and e.tag.endswith("rel")]
        rels = _rels(z, rel_part)
    values = _xml(z, "xl/richData/rdrichvalue.xml") if "xl/richData/rdrichvalue.xml" in names else None
    for rv in values.iterfind("{*}rv") if values is not None else []:
        s_idx = int(rv.get("s", "0"))
        stype, keys = structs[s_idx] if s_idx < len(structs) else ("", [])
        vals = [(v.text or "") for v in rv.iterfind("{*}v")]
        get = lambda name: vals[keys.index(name)] if name in keys and keys.index(name) < len(vals) else None  # noqa: E731
        ident = get("_rvRel:LocalImageIdentifier")
        if ident is None:
            rich.rvs.append((None, "", f"rich value of type {stype or '?'} is not a local picture"))
            continue
        try:
            rich.rvs.append((rels[rel_ids[int(ident)]], (get("Text") or "").strip(), ""))
        except (IndexError, KeyError, ValueError):
            rich.rvs.append((None, "", "picture relation not found"))
    return rich


def _sheet_parts(z: zipfile.ZipFile) -> dict[str, str]:
    root = _xml(z, "xl/workbook.xml")
    rels = _rels(z, "xl/workbook.xml")
    out: dict[str, str] = {}
    for sh in root.iter("{*}sheet") if root is not None else []:
        target = rels.get(sh.get(f"{{{NS_REL}}}id", ""))
        if target:
            out[sh.get("name", "")] = target
    return out


def read_incell_pictures(path: str | Path) -> dict[str, dict[tuple[int, int], InCellPicture]]:
    """Never raises: a damaged part only means fewer pictures (the caller still reads every cell)."""
    out: dict[str, dict[tuple[int, int], InCellPicture]] = {}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            rich = _rich_index(z, names)
            if not rich.vm_to_rv:  # no cell refers to a rich value: skip streaming the (possibly huge) sheet XML
                return out
            for sheet, part in _sheet_parts(z).items():
                if part not in names:
                    continue
                found: dict[tuple[int, int], InCellPicture] = {}
                with z.open(part) as fh:
                    for _, c in etree.iterparse(fh, events=("end",), tag="{*}c", **_PARSER):
                        vm = c.get("vm")
                        f = next(c.iterfind("{*}f"), None)
                        m = _IMAGE_FORMULA.search(f.text) if f is not None and f.text else None
                        if (vm and rich.vm_to_rv) or m:
                            col, row = coordinate_from_string(c.get("r"))
                            pic = InCellPicture(row, column_index_from_string(col), url=m.group(1) if m else "")
                            rv = rich.rvs[rich.vm_to_rv[int(vm)]] if vm and int(vm) in rich.vm_to_rv and rich.vm_to_rv[int(vm)] < len(rich.rvs) else None
                            if rv and rv[0] and rv[0] in names and z.getinfo(rv[0]).file_size <= MAX_PICTURE_BYTES:
                                pic.data = z.read(rv[0])
                                pic.ext = rv[0].rsplit(".", 1)[-1].lower() if "." in rv[0] else "png"
                                pic.alt = rv[1]
                            elif m:
                                pic.problem = "linked picture (address only, not stored in the file)"
                            else:
                                pic.problem = (rv[2] if rv and rv[2] else "picture could not be resolved")
                            found[(pic.row, pic.col)] = pic
                        c.clear()
                        while c.getprevious() is not None:
                            del c.getparent()[0]
                if found:
                    out[sheet] = found
    except (zipfile.BadZipFile, OSError, KeyError, ValueError, etree.XMLSyntaxError):
        return out
    return out
