import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/ on the path

from experiment.excel_extractor import testkit  # noqa: E402
from experiment.excel_extractor.extract import extract  # noqa: E402


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    """All fixture workbooks, built once per session."""
    d = tmp_path_factory.mktemp("fx")
    return {
        "radar": testkit.radar_like(d / "radar.xlsx"),
        "stacked": testkit.stacked_tables(d / "stacked.xlsx"),
        "multi": testkit.multi_level_header(d / "multi.xlsx"),
        "sections": testkit.section_rows(d / "sections.xlsx"),
        "side": testkit.side_by_side(d / "side.xlsx"),
        "kv": testkit.key_value(d / "kv.xlsx"),
        "fill": testkit.merges_fill_down(d / "fill.xlsx"),
        "objects": testkit.objects_all(d / "objects.xlsx"),
        "visible": testkit.visibility(d / "visible.xlsx"),
        "values": testkit.values_formats(d / "values.xlsx"),
        "nocache": testkit.formula_no_cache(d / "nocache.xlsx"),
        "group": testkit.group_shape(d / "group.xlsx"),
        "big": testkit.big_sheet(d / "big.xlsx", rows=20000),
        "empty": testkit.empty_sheet(d / "empty.xlsx"),
        "merged_only": testkit.merged_only_sheet(d / "merged.xlsx"),
    }


@pytest.fixture(scope="session")
def ex_cache(fx):
    cache = {}

    def get(key):
        if key not in cache:
            cache[key] = extract(fx[key])
        return cache[key]

    return get


def sheet(ex, name=None):
    return ex.book.sheets[0] if name is None else next(s for s in ex.book.sheets if s.name == name)


def region(sh, kind=None, range_=None):
    for g in sh.regions:
        if (kind is None or g.kind == kind) and (range_ is None or g.range == range_):
            return g
    raise AssertionError(f"no region kind={kind} range={range_}: {[(g.kind, g.range) for g in sh.regions]}")
