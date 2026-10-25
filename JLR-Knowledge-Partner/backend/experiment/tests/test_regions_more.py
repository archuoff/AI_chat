from conftest import region, sheet


def test_stacked_tables_split_on_title_bars(ex_cache):
    sh = sheet(ex_cache("stacked"))
    kinds = [g.range for g in sh.regions if g.kind in ("table", "transposed_table")]
    assert any(g.range in ("B2:E6", "B3:E6") for g in sh.regions if g.kind == "table"), [(g.kind, g.range) for g in sh.regions]
    assert any(g.range == "B8:E12" and g.kind == "table" for g in sh.regions), [(g.kind, g.range) for g in sh.regions]


def test_multi_level_header_is_joined(ex_cache):
    sh = sheet(ex_cache("multi"))
    g = region(sh, "table")
    assert g.header_rows == [2, 3]
    assert "Dimensions > Width (mm)" in g.headers
    assert "Material > Grade" in g.headers
    assert len(g.data_rows) == 5


def test_section_rows_do_not_split_the_table(ex_cache):
    sh = sheet(ex_cache("sections"))
    tables = [g for g in sh.regions if g.kind == "table"]
    assert len(tables) == 1, [(g.kind, g.range) for g in sh.regions]
    assert tables[0].section_rows == [3, 6]
    assert tables[0].data_rows == [4, 5, 7, 8]


def test_side_by_side_tables_are_separate(ex_cache):
    """Two tables share rows 2-5 and are split by blank column E: they must be two regions (known weak spot, see PENDING_WORK T4)."""
    sh = sheet(ex_cache("side"))
    ranges = [g.range for g in sh.regions]
    assert any(r.startswith("B2") and ":D" in r for r in ranges) and any(r.startswith("F2") for r in ranges), ranges


def test_key_value_cards(ex_cache):
    sh = sheet(ex_cache("kv"))
    assert any(g.kind == "key_value" and g.range.startswith("B2") for g in sh.regions), [(g.kind, g.range) for g in sh.regions]


def test_normal_table_has_rows_orientation(ex_cache):
    sh = sheet(ex_cache("multi"))
    assert region(sh, "table").orientation == "rows"
