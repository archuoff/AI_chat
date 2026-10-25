"""Nothing disappears silently: every item of the sheet is either inside a region or listed as not covered.

The verdict is "complete" only when the lists of problems are empty.
"""
from __future__ import annotations

from .grid import SheetData
from .model import Sheet


def build_inventory(data: SheetData) -> dict:
    sh: Sheet = data.model
    regions = sh.regions

    def region_of(r: int, c: int) -> str | None:
        best = None
        for g in regions:
            if g.r0 <= r <= g.r1 and g.c0 <= c <= g.c1 and (best is None or (g.r1 - g.r0) * (g.c1 - g.c0) <= (best.r1 - best.r0) * (best.c1 - best.c0)):
                best = g
        return best.id if best else None

    uncovered = [c.a1 for c in data.cells.values() if (c.v is not None or c.t == "p") and region_of(c.r, c.c) is None]
    pics = {"total": len(sh.pictures), "in_cell": sum(p.kind == "cell" for p in sh.pictures), "floating": sum(p.kind == "floating" for p in sh.pictures),
            "linked_not_embedded": sum("linked_not_embedded" in p.flags for p in sh.pictures)}
    problems: list[str] = []
    if uncovered:
        problems.append(f"{len(uncovered)} cell(s) are outside every region: {', '.join(uncovered[:8])}{' ...' if len(uncovered) > 8 else ''}")
    lost_pics = [p.id for p in sh.pictures if p.region is None]
    if lost_pics:
        problems.append(f"{len(lost_pics)} picture(s) are outside every region")
    unreadable_pics = [p.id for p in sh.pictures if any(f in p.flags for f in ("missing_media", "rich_value_unresolved", "unreadable_image")) or
                       any(f.startswith("rich value") or f == "picture relation not found" for f in p.flags)]
    if unreadable_pics:
        problems.append(f"{len(unreadable_pics)} picture(s) could not be read from the file")
    if pics["linked_not_embedded"]:
        problems.append(f"{pics['linked_not_embedded']} picture(s) are web links (=IMAGE) that are not stored in the file")
    unread_objects = [s.id for s in sh.shapes if "not_readable" in s.flags]
    if unread_objects:
        problems.append(f"{len(unread_objects)} object(s) hold content we cannot read (SmartArt, ink, controls...)")
    errors = [c.a1 for c in data.cells.values() if c.t == "e"]
    if errors:
        problems.append(f"{len(errors)} cell(s) show a real Excel error: {', '.join(errors[:6])}")
    no_cache = [c.a1 for c in data.cells.values() if "formula_no_cache" in c.flags]
    if no_cache:
        problems.append(f"{len(no_cache)} formula cell(s) have no saved result (open and save the file in Excel)")
    hidden = sum(1 for c in data.cells.values() if "hidden" in c.flags)
    uncertain = [g.id for g in regions if g.needs_llm]
    return {
        "cells_with_content": sum(1 for c in data.cells.values() if c.v is not None or c.t == "p"),
        "cells_in_regions": sum(1 for c in data.cells.values() if (c.v is not None or c.t == "p") and region_of(c.r, c.c)),
        "uncovered_cells": uncovered[:50],
        "pictures": pics,
        "shapes": {k: sum(s.kind == k for s in sh.shapes) for k in sorted({s.kind for s in sh.shapes})},
        "comments": len(sh.comments), "links": len(sh.links), "hidden_cells": hidden,
        "regions": {"total": len(regions), "leaf": sum(1 for g in regions if not g.children), "uncertain": uncertain},
        "problems": problems,
        "verdict": "complete" if not problems else "needs_attention",
    }
