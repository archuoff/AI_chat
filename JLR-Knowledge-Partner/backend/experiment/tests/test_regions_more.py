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


def test_two_data_rows_is_still_a_table(ex_cache):
    g = region(sheet(ex_cache("two_rows")), "table")
    assert g.data_rows == [3, 4] and not g.needs_llm


def test_borderless_fill_only_table(ex_cache):
    """Only the dark header fill tells the header apart; the body has no lines at all."""
    g = region(sheet(ex_cache("fill_only")), "table")
    assert g.header_rows == [2] and g.data_rows == [3, 4, 5, 6] and g.confidence >= 0.8


def test_spacer_column_inside_a_titled_table_stays_one_table(ex_cache):
    """A merged title runs across the empty spacer column E: one table, not two."""
    sh = sheet(ex_cache("spacer"))
    tables = [g for g in sh.regions if g.kind == "table"]
    assert [g.range for g in tables] == ["B2:F6"], [(g.kind, g.range) for g in sh.regions]
    assert tables[0].data_rows == [4, 5, 6]


def test_picture_covering_two_boxes_is_flagged_and_reviewed(ex_cache):
    sh = sheet(ex_cache("overlap"))
    pics = [p for p in sh.pictures if p.kind == "floating"]
    assert pics and any(f.startswith("straddles:") for f in pics[0].flags), pics[0].flags
    flagged = [g for g in sh.regions if g.id in pics[0].flags[0].split(":")[1].split(",")]
    assert flagged and all(g.needs_llm for g in flagged)


def test_straddling_picture_alone_is_its_own_box(ex_cache):
    sh = sheet(ex_cache("straddle"))
    pic = next(p for p in sh.pictures if p.kind == "floating")
    assert pic.region is not None
    assert not any(f.startswith("straddles:") for f in pic.flags)


def test_untitled_spacer_is_two_tables_by_design(ex_cache):
    sh = sheet(ex_cache("untitled"))
    assert [g.range for g in sh.regions if g.kind == "table"] == ["B2:C4", "E2:F4"]
