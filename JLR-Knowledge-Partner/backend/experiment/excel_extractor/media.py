"""Pictures: read from the package once, identified by content (sha256), written to media/ on export."""
from __future__ import annotations

import hashlib
import io
import posixpath
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .package import Package

RASTER = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
VECTOR = {".emf", ".wmf", ".svg", ".wdp"}  # kept as they are; not rendered to a bitmap here


@dataclass
class MediaInfo:
    name: str  # file name used in media/ (sha based, so identical pictures share one file)
    part: str  # path inside the zip
    ext: str
    sha256: str
    width: int = 0
    height: int = 0
    bytes: int = 0
    flags: list[str] = field(default_factory=list)


@dataclass
class MediaRegistry:
    pkg: Package
    items: dict[str, MediaInfo] = field(default_factory=dict)  # by zip part

    def get(self, part: str) -> MediaInfo | None:
        if part in self.items:
            return self.items[part]
        if not self.pkg.has(part):
            return None
        data = self.pkg.read(part)
        ext = posixpath.splitext(part)[1].lower() or ".bin"
        sha = hashlib.sha256(data).hexdigest()
        info = MediaInfo(name=f"{sha[:16]}{ext}", part=part, ext=ext, sha256=sha, bytes=len(data))
        if ext in RASTER:
            try:
                with Image.open(io.BytesIO(data)) as im:
                    info.width, info.height = im.size
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                info.flags.append("unreadable_image")
        elif ext in VECTOR:
            info.flags.append("vector_not_rendered")
        self.items[part] = info
        return info

    def export(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        for info in self.items.values():
            target = out / info.name
            if not target.exists():
                target.write_bytes(self.pkg.read(info.part))
