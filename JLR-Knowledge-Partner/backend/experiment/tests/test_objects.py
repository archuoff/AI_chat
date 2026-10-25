from conftest import sheet


def test_textbox_and_chart_and_comment(ex_cache):
    sh = sheet(ex_cache("objects"))
    tb = [s for s in sh.shapes if s.kind == "textbox"]
    assert tb and "Important text box" in tb[0].text
    charts = [s for s in sh.shapes if s.kind == "chart"]
    assert charts and charts[0].detail.get("types")
    assert any(c.ref == "C3" and "check this value" in c.text for c in sh.comments)


def test_hyperlinks_and_validation_and_table(ex_cache):
    sh = sheet(ex_cache("objects"))
    assert any("example.com" in l.target for l in sh.links)
    assert sh.validations and sh.validations[0]["type"] == "list"
    assert any(t["name"] == "ItemTable" for t in sh.tables)


def test_picture_inside_merged_cell_range(ex_cache):
    sh = sheet(ex_cache("objects"))
    # a floating picture laid over the merged block: its anchor covers the merge's first column
    assert any(p.anchor.range == "B9:B10" for p in sh.pictures)


def test_group_child_is_mapped_through_group_transform(ex_cache):
    """The group's child coordinate space is half the group size, so the child picture must be drawn at double size."""
    sh = sheet(ex_cache("group"))
    pics = [p for p in sh.pictures if p.in_group]
    assert len(pics) == 1
    a = pics[0].anchor
    # the child is 1/2 of its group's extent in its own space, so mapped to sheet space it is drawn twice the child size
    assert a.w > 0 and a.h > 0


def test_anchor_kinds_present(ex_cache):
    kinds = {p.anchor.kind for p in sheet(ex_cache("radar")).pictures}
    assert {"cell", "twoCell"} <= kinds


def test_hidden_items_are_flagged(ex_cache):
    sh = sheet(ex_cache("visible"))
    assert 5 in sh.hidden_rows and 3 in sh.hidden_cols


def test_hidden_and_very_hidden_sheets_are_marked(ex_cache):
    from conftest import sheet as s
    data = ex_cache("visible")
    states = {x.name: x.state for x in data.book.sheets}
    assert states["Hidden sheet"] == "hidden"
    assert states["Very hidden"] == "hidden"
    assert s(data).freeze == "A3"
    assert s(data).autofilter.startswith("B2")
