from conftest import region, sheet


def _flags(ex, r, c):
    """Flags of a cell in the sheet model (cells live in the JSON cell files; the picture's own cell is flagged 'picture')."""
    sh = sheet(ex)
    return next((x for x in sh.pictures if x.anchor.r0 == r and x.anchor.c0 == c and x.kind == "cell"), None) and ["picture"]


def test_transposed_market_table(ex_cache):
    sh = sheet(ex_cache("radar"))
    g = region(sh, "transposed_table", "B3:F10")
    assert g.orientation == "columns"
    assert g.header_rows == [4]
    assert g.title == "Radar Market Study"
    assert g.corner_label == "Radar Sensor Specifications"
    assert 5 in g.data_rows, "the picture row must be a data row, not a header"
    assert "AUDI SQ6 e-tron" in " | ".join(g.headers)


def test_four_in_cell_pictures_with_context(ex_cache):
    sh = sheet(ex_cache("radar"))
    cells = [p for p in sh.pictures if p.kind == "cell" and p.anchor.r0 == 5]
    assert [p.anchor.a1 if hasattr(p.anchor, "a1") else p.anchor.range for p in cells] == ["C5", "D5", "E5", "F5"]
    assert all(p.media and p.width == 40 for p in cells)
    assert [p.alt for p in cells] == ["Mercedes-Benz GLC 300", "AUDI SQ6 e-tron", "Range Rover Evoque P300e", "BMW iX xDrive 50"]
    for p in cells:
        assert p.neighbours["column_header"] == p.alt
        assert p.neighbours["row_label"] == "Radar Sensor Specifications"
        assert p.neighbours["box_title"] == "Radar Market Study"


def test_in_cell_cells_are_pictures_not_errors(ex_cache):
    data = ex_cache("radar")
    sh = sheet(data)
    for p in (p for p in sh.pictures if p.kind == "cell"):
        a = p.anchor
        assert not any(f.startswith("error:") for f in _flags(data, a.r0, a.c0))
    assert "#VALUE!" not in str(sh.inventory)


def test_spec_card_is_key_value(ex_cache):
    sh = sheet(ex_cache("radar"))
    g = region(sh, "key_value", "B31:C36")
    assert g.title == "Front Radar"
    assert g.data_rows == [33, 34, 35, 36]


def test_requirement_list_and_its_pictures(ex_cache):
    sh = sheet(ex_cache("radar"))
    g = region(sh, "requirement_list")
    assert g.range == "B47:D53"
    assert len(g.data_rows) == 5
    assert len(g.pictures) == 3


def test_picture_strip_with_captions(ex_cache):
    sh = sheet(ex_cache("radar"))
    strips = [x for x in sh.regions if x.kind == "picture_strip"]
    assert strips, "the framed overview pictures must be found as a picture strip for now"
    assert sum(len(x.pictures) for x in strips) >= 3


def test_stray_note_is_a_title_or_stray_not_lost(ex_cache):
    sh = sheet(ex_cache("radar"))
    assert any(g.range == "N5" for g in sh.regions)
    assert sh.inventory["uncovered_cells"] == []


def test_inventory_complete(ex_cache):
    assert sheet(ex_cache("radar")).inventory["verdict"] == "complete"


# Known gap, documented rather than hidden: the framed positional overview (B13:F28, two merged blocks with
# pictures) is currently read as one picture strip, not as a frame with children. Fixing it is task T4.
import pytest  # noqa: E402


@pytest.mark.xfail(strict=True, reason="framed overview is not split into a frame with children yet (T4)")
def test_framed_overview_is_a_frame_with_children(ex_cache):
    sh = sheet(ex_cache("radar"))
    frame = region(sh, "frame")
    assert len(frame.children) >= 2
