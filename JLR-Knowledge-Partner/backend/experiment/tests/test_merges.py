from conftest import region, sheet


def test_merged_areas_are_recorded(ex_cache):
    sh = sheet(ex_cache("fill"))
    assert {"B3:B5", "B6:B7", "F3:G4"} <= {m.range for m in sh.merges}


def test_vertical_merge_label_is_not_a_header(ex_cache):
    g = region(sheet(ex_cache("fill")), "table")
    assert g.header_rows == [2], "the merged group label must not extend the header"
    assert 3 in g.data_rows


def test_merged_value_outside_table_is_kept_not_merged_in(ex_cache):
    """The 'merged block value' sits beside the table, not inside it: it is its own small region, never dropped."""
    sh = sheet(ex_cache("fill"))
    assert any(g.range == "F3:G4" for g in sh.regions)
    assert sh.inventory["uncovered_cells"] == []
