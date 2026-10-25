"""Command line: `python -m experiment.excel_extractor <extract|inspect|compare> FILE [...]` (run from backend/)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def _cmd_extract(a) -> int:
    from .extract import extract

    ex = extract(a.file, with_formulas=a.formulas)
    try:
        out = ex.save(Path(a.out), layout_chars=a.layout_chars)
    finally:
        ex.close()
    for sh in ex.book.sheets:
        inv = sh.inventory
        print(f"{sh.name}: {len(sh.regions)} region(s), {len(sh.pictures)} picture(s), verdict {inv.get('verdict')}")
        for p in inv.get("problems", []):
            print(f"  ! {p}")
    print(f"written to {out}")
    return 0


def _cmd_inspect(a) -> int:
    """Counts only: no cell text, no sheet content, no media names. Safe to run on confidential files."""
    from .extract import extract

    ex = extract(a.file, with_formulas=False)
    try:
        report = {"parts": ex.book.parts, "sheets": []}
        for sd in ex.data.values():
            sh = sd.model
            kinds = Counter(p.kind for p in sh.pictures)
            shape_kinds = Counter(s.kind for s in sh.shapes)
            report["sheets"].append({
                "state": sh.state,
                "used_range": sh.dims,
                "cells_with_values": sh.non_empty,
                "merged_areas": len(sh.merges),
                "hidden_rows": len(sh.hidden_rows),
                "hidden_columns": len(sh.hidden_cols),
                "pictures": {"in_cell": kinds.get("cell", 0), "floating": kinds.get("floating", 0),
                             "linked_formula": kinds.get("linked", 0),
                             "unresolved": sum(1 for p in sh.pictures if "linked_not_embedded" not in p.flags and not p.media)},
                "shapes": dict(shape_kinds),
                "comments": {"legacy": sum(c.kind == "legacy" for c in sh.comments), "threaded": sum(c.kind == "threaded" for c in sh.comments)},
                "hyperlinks": len(sh.links),
                "excel_tables": len(sh.tables),
                "validations": len(sh.validations),
                "regions_by_kind": dict(Counter(g.kind for g in sh.regions)),
                "regions_uncertain": sum(g.needs_llm for g in sh.regions),
                "verdict": sh.inventory.get("verdict"),
                "problem_count": len(sh.inventory.get("problems", [])),
            })
    finally:
        ex.close()
    if a.json:
        print(json.dumps(report, indent=1, ensure_ascii=False))
    else:
        print(f"parts: {report['parts']}")
        for i, s in enumerate(report["sheets"]):
            print(f"sheet {i + 1} [{s['state']}] {s['used_range']}: {s}")
    return 0


def _cmd_compare(a) -> int:
    """Old reader (app.ingestion.excel, read only) against the new extractor on the same workbook."""
    from .extract import extract

    try:
        from app.ingestion.excel import parse_excel
    except ImportError:
        print("compare needs the app package on the path: run from backend/ (PYTHONPATH=.)")
        return 2
    old = parse_excel(a.file)
    ex = extract(a.file)
    try:
        for name, rep in old.stats.get("sheets", {}).items():
            new = next((s for s in ex.book.sheets if s.name == name), None)
            if new is None:
                print(f"{name}: not in the new model")
                continue
            cov = rep["coverage"]
            old_ignored = [m for m in cov["ignored"]]
            print(f"{name}")
            print(f"  old: {len(rep['tables'])} table(s), {rep['records']} record(s), coverage {cov['percent']}%, "
                  f"{cov['ignored_count']} ignored cell(s)")
            print(f"  new: {len(new.regions)} region(s) {dict(Counter(g.kind for g in new.regions))}, "
                  f"{len(new.pictures)} picture(s), verdict {new.inventory.get('verdict')}")
            pic_cells = {p.anchor.a1 if hasattr(p.anchor, 'a1') else f"{chr(64 + p.anchor.c0)}{p.anchor.r0}" for p in new.pictures if p.kind == "cell"}
            ignored_pics = [m["cell"] for m in old_ignored if m["cell"] in pic_cells]
            if ignored_pics:
                print(f"  in-cell pictures the old reader ignored and the new one reads: {', '.join(ignored_pics[:12])}")
    finally:
        ex.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m experiment.excel_extractor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="write model.json, cells, layout.json, media, report.html")
    p.add_argument("file")
    p.add_argument("--out", required=True)
    p.add_argument("--formulas", dest="formulas", action="store_true", default=None)
    p.add_argument("--no-formulas", dest="formulas", action="store_false")
    p.add_argument("--layout-chars", type=int, default=12000)
    p.set_defaults(fn=_cmd_extract)
    p = sub.add_parser("inspect", help="counts only (safe for confidential files)")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_inspect)
    p = sub.add_parser("compare", help="old reader vs new extractor")
    p.add_argument("file")
    p.set_defaults(fn=_cmd_compare)
    p.add_argument("--debug", action="store_true")
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except Exception as e:  # one readable line, traceback only with --debug
        if getattr(a, "debug", False):
            raise
        print(f"error: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
