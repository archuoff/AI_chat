import json

from conftest import sheet
from experiment.excel_extractor.layout import build_layout


def test_complete_sheet_has_verdict_complete(ex_cache):
    assert sheet(ex_cache("stacked")).inventory["verdict"] == "complete"


def test_unreadable_object_makes_inventory_need_attention(fx):
    """A SmartArt / form control is not readable: the inventory must say so, not claim 'complete'."""
    from experiment.excel_extractor.extract import extract
    from experiment.excel_extractor.model import Anchor, Shape
    ex = extract(fx["empty"])
    try:
        sh = ex.book.sheets[0]
        sh.shapes.append(Shape(id="x1", kind="smartart", anchor=Anchor("absolute", 1, 1, 1, 1), flags=["not_readable"]))
        from experiment.excel_extractor.inventory import build_inventory
        inv = build_inventory(ex.data[sh.name])
        assert inv["verdict"] == "needs_attention"
        assert any("cannot read" in p for p in inv["problems"])
    finally:
        ex.close()


def test_layout_is_bounded_and_says_when_trimmed(ex_cache):
    ex = ex_cache("radar")
    small = build_layout(ex, max_chars=800)
    for s in small["sheets"]:
        size = len(json.dumps(s, ensure_ascii=False))
        assert size <= 800 or s.get("omitted_regions", 0) > 0, size
    big = build_layout(ex, max_chars=12000)
    for s in big["sheets"]:
        assert len(json.dumps(s, ensure_ascii=False)) <= 12000


def test_layout_samples_are_capped(ex_cache):
    lay = build_layout(ex_cache("radar"), max_chars=12000)
    for s in lay["sheets"]:
        for r in s["regions"]:
            assert len(r.get("sample_rows", [])) <= 4
