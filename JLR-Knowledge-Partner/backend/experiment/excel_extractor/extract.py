"""Orchestration: workbook in, sheet model out."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .grid import SheetData, read_workbook
from .inventory import build_inventory
from .layout import build_layout
from .media import MediaRegistry
from .model import Workbook, to_json
from .ooxml import read_richvalues, read_sheet_objects, sheet_parts
from .package import Package
from .regions import find_regions


@dataclass
class Extraction:
    book: Workbook
    data: dict[str, SheetData]
    media: MediaRegistry
    pkg: Package

    def close(self) -> None:
        self.pkg.close()

    def save(self, out: Path, layout_chars: int = 12000, report: bool = True) -> Path:
        """model.json, cells/<sheet>.jsonl, layout.json, media/, report.html"""
        out.mkdir(parents=True, exist_ok=True)
        (out / "model.json").write_text(json.dumps(to_json(self.book), indent=1, ensure_ascii=False), encoding="utf-8")
        (out / "cells").mkdir(exist_ok=True)
        for i, (name, sd) in enumerate(self.data.items()):
            with (out / "cells" / f"{i:02d}_{_safe(name)}.jsonl").open("w", encoding="utf-8") as fh:
                for key in sorted(sd.cells):
                    fh.write(json.dumps(to_json(sd.cells[key]), ensure_ascii=False) + "\n")
        (out / "layout.json").write_text(json.dumps(build_layout(self, layout_chars), indent=1, ensure_ascii=False), encoding="utf-8")
        self.media.export(out / "media")
        if report:
            from .report import write_report

            write_report(self, out)
        return out


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:40]


def extract(path: str | Path, with_formulas: bool | None = None) -> Extraction:
    book, data = read_workbook(path, with_formulas)
    pkg = Package(path)
    media = MediaRegistry(pkg)
    book.parts = pkg.part_groups()
    rich = read_richvalues(pkg)
    book.warnings.extend(rich.warnings)
    parts = sheet_parts(pkg)
    for name, sd in data.items():
        if name in parts:
            read_sheet_objects(pkg, sd, parts[name], rich, media)
        else:
            sd.model.warnings.append("sheet part not found: pictures and drawings were not read")
        find_regions(sd)
        sd.model.inventory = build_inventory(sd)
    return Extraction(book, data, media, pkg)
