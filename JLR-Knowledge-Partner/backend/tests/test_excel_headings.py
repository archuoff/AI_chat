"""Excel: Place-in-Cell pictures and heading handling in the live parser."""
import pytest

xlsxwriter = pytest.importorskip("xlsxwriter")
testkit = pytest.importorskip("experiment.excel_extractor.testkit")

from app.ingestion import parse_file


def book(tmp_path, build):
    path = tmp_path / "t.xlsx"
    wb = xlsxwriter.Workbook(str(path))
    ws = wb.add_worksheet("S")
    build(wb, ws, {"bold": wb.add_format({"bold": True, "bg_color": "#DDDDDD"}), "plain": wb.add_format({})})
    wb.close()
    return parse_file(path)


def tables(doc):
    return doc.stats["sheets"]["S"]["tables"]


def test_in_cell_pictures_are_data_not_header_and_not_ignored(tmp_path):
    doc = parse_file(testkit.radar_like(tmp_path / "radar.xlsx"))
    rep = doc.stats["sheets"]["Radar Sensor"]
    table = next(t for t in rep["tables"] if t["range"] == "B3:F10")
    assert table["header_rows"] == [4] and 5 in table["data_rows"] and table["title"] == "Radar Market Study"
    assert rep["in_cell_pictures"] >= 4 and rep["coverage"]["ignored_count"] == 0 and rep["coverage"]["percent"] == 100.0
    picture_row = next(e for e in doc.elements if e.kind == "record" and e.location.get("row") == 5)
    assert "[picture" in picture_row.text
    assert not any(h >= 13 for t in rep["tables"] if t["range"].startswith("B13") for h in t["header_rows"][1:])  # tall merged label is not a header


def test_picture_context_has_box_column_row_label_and_alt_text(tmp_path):
    doc = parse_file(testkit.radar_like(tmp_path / "radar.xlsx"))
    pics = [i for i in doc.images if i.location.get("placement") == "in_cell"]
    assert len(pics) >= 4
    p = next(i for i in pics if i.location["cell"] == "D5")
    assert "Box title: Radar Market Study" in p.context and "Column: AUDI SQ6 e-tron" in p.context
    assert "Row label: Radar Sensor Specifications" in p.context and "Alt text: AUDI SQ6 e-tron" in p.context


def test_stacked_tables_without_blank_row_are_two_tables(tmp_path):
    def build(wb, ws, f):
        ws.merge_range("A1:C1", "Table one", f["bold"])
        for c, h in enumerate(["Vehicle", "Weight", "Material"]):
            ws.write(1, c, h, f["bold"])
        ws.write_row(2, 0, ["Golf", 3.1, "PP"]); ws.write_row(3, 0, ["Polo", 2.8, "PA"])
        ws.merge_range("A5:C5", "Table two", f["bold"])  # no blank row before it
        for c, h in enumerate(["Part", "Thickness", "Unit"]):
            ws.write(5, c, h, f["bold"])
        ws.write_row(6, 0, ["Bumper", 2.5, "mm"]); ws.write_row(7, 0, ["Grille", 2, "mm"])
    doc = book(tmp_path, build)
    assert [t["title"] for t in tables(doc)] == ["Table one", "Table two"]
    assert [t["header_rows"] for t in tables(doc)] == [[2], [6]]
    assert doc.elements[-1].fields == {"Part": "Grille", "Thickness": 2, "Unit": "mm"}


def test_plain_section_row_before_text_rows_is_not_a_new_table(tmp_path):
    def build(wb, ws, f):
        for c, h in enumerate(["Item", "Supplier", "Note"]):
            ws.write(0, c, h, f["bold"])
        ws.write_row(1, 0, ["Alpha", "Bosch", "ok"])
        ws.write(2, 0, "Group B")  # plain label, then rows of text
        ws.write_row(3, 0, ["Beta", "Valeo", "late"]); ws.write_row(4, 0, ["Gamma", "Denso", "ok"])
    doc = book(tmp_path, build)
    assert len(tables(doc)) == 1 and tables(doc)[0]["section_rows"] == [3] and tables(doc)[0]["records"] == 3
    recs = [e for e in doc.elements if e.kind == "record"]
    assert [r.fields["Item"] for r in recs] == ["Alpha", "Beta", "Gamma"] and recs[-1].section == ["S", "Group B"]


def test_nested_section_rows_keep_both_levels(tmp_path):
    def build(wb, ws, f):
        for c, h in enumerate(["Item", "Value", "Unit"]):
            ws.write(0, c, h, f["bold"])
        ws.merge_range("A2:C2", "Front sensors", f["bold"])
        ws.write(2, 0, "Left"); ws.write_row(3, 0, ["S1", 1, "mm"])
        ws.write(4, 0, "Right"); ws.write_row(5, 0, ["S2", 2, "mm"])
        ws.merge_range("A7:C7", "Rear sensors", f["bold"])
        ws.write_row(7, 0, ["S3", 3, "mm"])
    doc = book(tmp_path, build)
    paths = {e.fields["Item"]: e.section for e in doc.elements if e.kind == "record"}
    assert paths["S1"] == ["S", "Front sensors", "Left"] and paths["S2"] == ["S", "Front sensors", "Right"]
    assert paths["S3"] == ["S", "Rear sensors"]


def test_multi_level_header_with_a_plain_column(tmp_path):
    doc = parse_file(testkit.multi_level_header(tmp_path / "m.xlsx"))
    first = next(e for e in doc.elements if e.kind == "record")
    assert list(first.fields)[:2] == ["Dimensions > Width (mm)", "Dimensions > Height (mm)"] and first.fields["Dimensions > Width (mm)"] == 100


def test_header_line_breaks_are_cleaned(tmp_path):
    def build(wb, ws, f):
        ws.write_row(0, 0, ["Part", "Width\n(mm)", "Height\n  (mm)"], f["bold"])
        ws.write_row(1, 0, ["A", 1, 2]); ws.write_row(2, 0, ["B", 3, 4])
    doc = book(tmp_path, build)
    assert list(doc.elements[-1].fields) == ["Part", "Width (mm)", "Height (mm)"]
