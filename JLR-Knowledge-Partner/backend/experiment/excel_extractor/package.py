"""A read-only view of the .xlsx zip: parts, relationships, safe XML parsing."""
from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_PARSER = dict(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=True)


@dataclass
class Rel:
    id: str
    type: str  # last path segment of the relationship type, e.g. "drawing", "image", "threadedComment"
    target: str  # resolved part name inside the zip ("xl/media/image1.png") or the external URL
    external: bool = False


def local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


class Package:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.z = zipfile.ZipFile(self.path)
        self.names = set(self.z.namelist())

    def close(self) -> None:
        self.z.close()

    def has(self, name: str) -> bool:
        return name in self.names

    def read(self, name: str) -> bytes:
        return self.z.read(name)

    def size(self, name: str) -> int:
        return self.z.getinfo(name).file_size

    def xml(self, name: str):
        """Parsed root element, or None when the part is missing or not XML."""
        if name not in self.names:
            return None
        try:
            return etree.fromstring(self.z.read(name), etree.XMLParser(recover=True, **_PARSER))
        except etree.XMLSyntaxError:
            return None

    def iterparse(self, name: str, tag: str):
        """Stream the elements named `tag` (any namespace) of a big part; the caller must clear what it has used."""
        with self.z.open(name) as fh:
            yield from etree.iterparse(fh, events=("end",), tag=f"{{*}}{tag}", **_PARSER)

    def rels(self, part: str) -> dict[str, Rel]:
        rel_part = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
        root = self.xml(rel_part)
        out: dict[str, Rel] = {}
        if root is None:
            return out
        for r in root:
            if local(r) != "Relationship":
                continue
            external = r.get("TargetMode") == "External"
            target = r.get("Target", "")
            if not external:
                target = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
            out[r.get("Id", "")] = Rel(r.get("Id", ""), (r.get("Type") or "").rsplit("/", 1)[-1], target, external)
        return out

    def part_groups(self) -> dict[str, int]:
        """How many parts of each kind the package holds (richData, media, embeddings ...), for the diagnostic."""
        groups: dict[str, int] = {}
        for n in self.names:
            key = next((k for k in ("richData", "media", "embeddings", "drawings", "charts", "diagrams", "threadedComments", "comments",
                                    "tables", "externalLinks", "ctrlProps", "activeX", "customXml") if f"/{k}/" in f"/{n}" or n.startswith(f"xl/{k}")), None)
            if key is None and n.endswith("vbaProject.bin"):
                key = "vbaProject"
            if key:
                groups[key] = groups.get(key, 0) + 1
        return groups
