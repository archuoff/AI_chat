"""Fixture builders: small workbooks with the layouts we must handle. Built with XlsxWriter (its embed_image writes real Place-in-Cell pictures)."""
from __future__ import annotations

import struct
import zlib
import zipfile
from pathlib import Path

import xlsxwriter


def png_bytes(w: int = 40, h: int = 30, color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def write_png(folder: Path, name: str, color: tuple[int, int, int] = (200, 30, 30), w: int = 40, h: int = 30) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_bytes(png_bytes(w, h, color))
    return p


class Book:
    """Thin wrapper: one workbook, formats created once."""

    def __init__(self, path: Path):
        self.path = path
        self.wb = xlsxwriter.Workbook(str(path))
        self.img_dir = path.parent / "img"
        self._f: dict[str, object] = {}

    def fmt(self, key: str, **kw):
        if key not in self._f:
            base = {"border": 1, "text_wrap": True, "valign": "vcenter"}
            base.update(kw)
            self._f[key] = self.wb.add_format(base)
        return self._f[key]

    def title(self):
        return self.fmt("title", bold=True, font_color="#FFFFFF", bg_color="#7F7F7F", align="center")

    def dark(self):
        return self.fmt("dark", bold=True, font_color="#FFFFFF", bg_color="#1F2D5A", align="center")

    def body(self):
        return self.fmt("body")

    def close(self) -> Path:
        self.wb.close()
        return self.path


def radar_like(path: Path) -> Path:
    """The Radar sheet of the owner's screenshots, rebuilt: title bar, transposed market table with a picture row, framed overview,
    spec card, picture strip, requirement list, and a stray note far to the right."""
    b = Book(path)
    ws = b.wb.add_worksheet("Radar Sensor")
    ws.set_column("A:A", 3)
    ws.set_column("B:B", 28)
    ws.set_column("C:F", 26)
    ws.set_column("G:G", 3)
    ws.set_column("N:N", 14)
    ws.merge_range("B3:F3", "Radar Market Study", b.title())
    ws.merge_range("B4:B5", "Radar Sensor Specifications", b.dark())
    for col, name in zip("CDEF", ["Mercedes-Benz GLC 300", "AUDI SQ6 e-tron", "Range Rover Evoque P300e", "BMW iX xDrive 50"]):
        ws.write(f"{col}4", name, b.dark())
    ws.set_row(4, 80)
    colors = [(200, 30, 30), (30, 160, 60), (30, 60, 200), (220, 180, 30)]
    vehicles = ["Mercedes-Benz GLC 300", "AUDI SQ6 e-tron", "Range Rover Evoque P300e", "BMW iX xDrive 50"]
    for i, col in enumerate("CDEF"):
        # Place-in-Cell picture: the cell itself holds the picture (what Excel 365 writes), with alt text
        ws.embed_image(f"{col}5", write_png(b.img_dir, f"pic{i}.png", colors[i]), {"description": vehicles[i]})
    labels = ["Radar Sensor Manufacturer", "Object Detection Min. Range", "Object Detection Max. Range", "IP - Protection Class", "Operating Temp. Range"]
    values = [["BOSCH", "BOSCH", "BOSCH", "VALEO"], ["0.15 m"] * 4, ["5.5 m", "5.5 m", "5.5 m", "5.0 m (Valeo typical)"],
              ["IP6KX / IP9K", "IP6KX / IP9K", "IP6KX / IP9K", "IP6KX (typical Valeo)"], ["-40°C to +95°C"] * 4]
    for r, (lab, vals) in enumerate(zip(labels, values), start=6):
        ws.write(f"B{r}", lab, b.body())
        for col, v in zip("CDEF", vals):
            ws.write(f"{col}{r}", v, b.body())
    # framed overview: two bordered blocks side by side inside one frame, each with a title and a picture
    ws.merge_range("B13:C28", "Level 2+ Positional Overview: the positional overview of the level 2+ exterior radars is shown below", b.body())
    ws.merge_range("D13:E28", "Level 3 Positional Overview: the positional overview of the level 3 exterior radars is shown below", b.body())
    ws.merge_range("F13:F28", "", b.body())
    ws.insert_image("B15", write_png(b.img_dir, "overview2.png", (120, 120, 120)), {"x_offset": 6, "y_offset": 30})
    ws.insert_image("D15", write_png(b.img_dir, "overview3.png", (90, 90, 90)), {"x_offset": 6, "y_offset": 30})
    ws.insert_image("F15", write_png(b.img_dir, "bumper.png", (60, 110, 200)), {"x_offset": 6, "y_offset": 30})
    # spec card
    ws.merge_range("B31:C31", "Front Radar", b.title())
    ws.write("B32", "Radar Specifications", b.dark())
    ws.write("C32", "AUDI SQ6 e-tron", b.dark())
    ws.write("B33", "Radar Specifications", b.body())
    ws.set_row(32, 80)
    ws.embed_image("C33", write_png(b.img_dir, "front.png", (40, 40, 40)), {"description": "front radar"})
    for r, (lab, val) in enumerate([("Width x Height x Depth (in mm)", "146 x 111 x 50"), ("Unit weight", "0.491 Kg"),
                                    ("Material", "PBT-GF; Electronic component")], start=34):
        ws.write(f"B{r}", lab, b.body())
        ws.write(f"C{r}", val, b.body())
    # picture strip
    ws.merge_range("B39:C39", "Bracket fixation", b.title())
    ws.write("B40", "AUDI SQ6 e-tron", b.dark())
    ws.write("C40", "AUDI SQ6 e-tron", b.dark())
    ws.write("B41", "Front view (radar packaging assembly)", b.body())
    ws.embed_image("B42", write_png(b.img_dir, "bracket1.png", (50, 80, 50)), {"description": "front view"})
    ws.write("B43", "Rear view (radar bracket fixed with snap fit)", b.body())
    ws.embed_image("B44", write_png(b.img_dir, "bracket2.png", (80, 50, 50)), {"description": "rear view"})
    ws.set_row(41, 40)
    ws.set_row(43, 40)
    # requirement list: IDs + text, merged DVA labels in the middle column, pictures on the right
    ws.merge_range("B47:D47", "Design Guidelines for the RADAR", b.title())
    reqs = ["SSA Requirement 00165101: The Mid Radar Front pitch shall be maintained within +/-3 deg relative to the nominal ground plane.",
            "SSA Requirement 00165103: The Mid Radar Front roll shall be maintained within +/-2 deg relative to the nominal ground plane.",
            "SSA Requirement 00165102: The Mid Radar Front yaw shall be maintained within +/-2 deg relative to the nominal ground plane.",
            "SSA Requirement 00165105: The Mid Radar Front shall be nominally positioned at 0 deg Pitch, Roll and Yaw.",
            "SSA Requirement 00165099: The Mid Radar Front Y position in the vehicle axis system shall be +/-300 mm from the Y=0 centre line.",
            "SSA Requirement 00165100: The Mid Radar Front Z position in the vehicle axis system shall be >400 mm and <900 mm."]
    for i, text in enumerate(reqs):
        ws.set_row(47 + i, 40)
        ws.write(f"B{48 + i}", text, b.body())
    ws.merge_range("C48:C50", "DVA Requirement for Mid Radar", b.dark())
    ws.merge_range("C51:C53", "DVA Requirement for Corner Radar", b.dark())
    ws.embed_image("D51", write_png(b.img_dir, "req1.png", (30, 60, 120)), {"description": "requirement picture 1"})
    ws.embed_image("D52", write_png(b.img_dir, "req2.png", (30, 120, 60)), {"description": "requirement picture 2"})
    ws.embed_image("D53", write_png(b.img_dir, "req3.png", (120, 60, 30)), {"description": "requirement picture 3"})
    ws.write("N5", "stray note", b.body())
    return b.close()


def stacked_tables(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Stacked")
    ws.merge_range("B2:E2", "Table one", b.title())
    for c, h in zip("BCDE", ["Vehicle", "Weight", "Material", "Mass"]):
        ws.write(f"{c}3", h, b.dark())
    for r, row in enumerate([["Golf", 3.1, "PP", 2.0], ["Polo", 2.8, "PA", 1.9], ["Up", 2.2, "PP", 1.5]], start=4):
        for c, v in zip("BCDE", row):
            ws.write(f"{c}{r}", v, b.body())
    ws.merge_range("B8:E8", "Table two", b.title())
    for c, h in zip("BCDE", ["Part", "Thickness", "Unit", "Note"]):
        ws.write(f"{c}9", h, b.dark())
    for r, row in enumerate([["Bumper", 2.5, "mm", "ok"], ["Grille", 2.0, "mm", "ok"], ["Frunk", 3.0, "mm", "check"]], start=10):
        for c, v in zip("BCDE", row):
            ws.write(f"{c}{r}", v, b.body())
    return b.close()


def multi_level_header(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Multi")
    ws.merge_range("B2:C2", "Dimensions", b.dark())
    ws.merge_range("D2:E2", "Material", b.dark())
    for c, h in zip("BCDEF", ["Width (mm)", "Height (mm)", "Type", "Grade", "Note"]):
        ws.write(f"{c}3", h, b.dark())
    for r, row in enumerate([[100, 40, "PP", "GF20", "a"], [120, 42, "PA", "GF30", "b"], [90, 35, "PP", "T20", "c"],
                             [110, 44, "PA", "GF30", "d"], [95, 38, "PP", "T10", "e"]], start=4):
        for c, v in zip("BCDEF", row):
            ws.write(f"{c}{r}", v, b.body())
    return b.close()


def section_rows(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Sections")
    for c, h in zip("BCD", ["Item", "Value", "Unit"]):
        ws.write(f"{c}2", h, b.dark())
    rows = [("Group A", None, None), ("Alpha", 1, "mm"), ("Beta", 2, "mm"), ("Group B", None, None), ("Gamma", 3, "mm"), ("Delta", 4, "mm")]
    r = 3
    for item, v, u in rows:
        if v is None:
            ws.merge_range(f"B{r}:D{r}", item, b.fmt("sect", bold=True, bg_color="#E9EDF3", border=1))
        else:
            ws.write(f"B{r}", item, b.body())
            ws.write(f"C{r}", v, b.body())
            ws.write(f"D{r}", u, b.body())
        r += 1
    return b.close()


def side_by_side(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Side")
    for c, h in zip("BCD", ["Name", "Score", "Rank"]):
        ws.write(f"{c}2", h, b.dark())
    for c, h in zip("F G H".split(), ["Code", "Level", "Owner"]):
        ws.write(f"{c}2", h, b.dark())
    for r in range(3, 6):
        ws.write(f"B{r}", f"n{r}", b.body())
        ws.write(f"C{r}", r * 10, b.body())
        ws.write(f"D{r}", r, b.body())
        ws.write(f"F{r}", f"C{r}", b.body())
        ws.write(f"G{r}", r + 1, b.body())
        ws.write(f"H{r}", f"o{r}", b.body())
    ws.write("B8", "Second", b.dark())
    ws.write("C8", "Third", b.dark())
    ws.write("B9", "x", b.body())
    ws.write("C9", "y", b.body())
    return b.close()


def key_value(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Cards")
    for r, (k, v) in enumerate([("Width (mm)", 146), ("Height (mm)", 111), ("Depth (mm)", 50), ("Weight (kg)", 0.491),
                                ("Material", "PBT-GF")], start=2):
        ws.write(f"B{r}", k, b.body())
        ws.write(f"C{r}", v, b.body())
    for c, (k, v) in zip("EFGH", [("Supplier", "Bosch"), ("Part no", "A-100"), ("Status", "Released"), ("Rev", "C")]):
        ws.write(f"{c}2", k, b.body())
        ws.write(f"{c}3", v, b.body())
    return b.close()


def merges_fill_down(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Fill")
    for c, h in zip("BCD", ["Group", "Failure", "Severity"]):
        ws.write(f"{c}2", h, b.dark())
    ws.merge_range("B3:B5", "Hood", b.body())
    ws.merge_range("B6:B7", "Bumper", b.body())
    for r, (f, s) in enumerate([("Crack", 7), ("Dent", 5), ("Rust", 3), ("Gap", 6), ("Paint", 2)], start=3):
        ws.write(f"C{r}", f, b.body())
        ws.write(f"D{r}", s, b.body())
    ws.merge_range("F3:G4", "merged block value", b.body())
    return b.close()


def objects_all(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Objects")
    for c, h in zip("BCD", ["Item", "Value", "Link"]):
        ws.write(f"{c}2", h, b.dark())
    for r, (i, v) in enumerate([("a", 1), ("b", 2), ("c", 3)], start=3):
        ws.write(f"B{r}", i, b.body())
        ws.write(f"C{r}", v, b.body())
    ws.write_url("D3", "https://example.com/spec", string="spec link")
    ws.write_url("D4", "internal:Objects!B3", string="go to a")
    ws.data_validation("C3:C5", {"validate": "list", "source": ["1", "2", "3"]})
    ws.write_comment("C3", "check this value")
    ws.insert_textbox("G2", "Important text box", {"width": 240, "height": 120})
    chart = b.wb.add_chart({"type": "column"})
    chart.add_series({"name": "Values", "categories": "=Objects!$B$3:$B$5", "values": "=Objects!$C$3:$C$5"})
    ws.insert_chart("G10", chart)
    ws.add_table("B2:C5", {"name": "ItemTable", "columns": [{"header": "Item"}, {"header": "Value"}]})
    ws.merge_range("B9:C10", "", b.body())
    ws.insert_image("B9", write_png(b.img_dir, "merged.png", (10, 10, 200)), {"x_offset": 2, "y_offset": 2})
    return b.close()


def visibility(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Visible")
    ws.write("B2", "Name", b.dark())
    ws.write("C2", "Hidden col", b.dark())
    ws.write("D2", "Shown", b.dark())
    for r in range(3, 9):
        ws.write(f"B{r}", f"row{r}", b.body())
        ws.write(f"C{r}", r, b.body())
        ws.write(f"D{r}", r * 2, b.body())
    ws.set_row(4, None, None, {"hidden": True})
    ws.set_column("C:C", None, None, {"hidden": True})
    ws.set_row(6, None, None, {"level": 1})
    ws.set_row(7, None, None, {"level": 1})
    ws.autofilter("B2:D8")
    ws.freeze_panes(2, 0)
    hidden = b.wb.add_worksheet("Hidden sheet")
    hidden.write("A1", "secret-hidden-sheet-text", b.body())
    hidden.hide()
    very = b.wb.add_worksheet("Very hidden")
    very.write("A1", "very-hidden-text", b.body())
    very.hide()
    return b.close()


def values_formats(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Values")
    ws.write("B2", "int", b.body()); ws.write("C2", 0, b.body())
    ws.write("B3", "float", b.body()); ws.write("C3", 2.345, b.body())
    ws.write("B4", "percent", b.body()); ws.write("C4", 0.125, b.fmt("pct", num_format="0.0%"))
    ws.write("B5", "thousands", b.body()); ws.write("C5", 1200, b.fmt("th", num_format="#,##0.00"))
    ws.write("B6", "date", b.body()); ws.write_datetime("C6", __import__("datetime").datetime(2026, 3, 1), b.fmt("dt", num_format="yyyy-mm-dd"))
    ws.write("B7", "bool", b.body()); ws.write_boolean("C7", False, b.body())
    ws.write("B8", "text number", b.body()); ws.write_string("C8", "0012", b.body())
    ws.write("B9", "line breaks", b.body()); ws.write("C9", "first line\nsecond line", b.body())
    ws.write("B10", "long", b.body()); ws.write("C10", "x" * 400, b.body())
    ws.write("B11", "unicode", b.body()); ws.write("C11", "Dév Üser 日本 ✓", b.body())
    ws.write("B12", "error", b.body()); ws.write_formula("C12", "=1/0", b.body(), "#DIV/0!")
    ws.write("B13", "formula", b.body()); ws.write_formula("C13", "=C3*2", b.body(), 4.69)
    ws.write("B14", "sci", b.body()); ws.write("C14", 0.00012, b.fmt("sci", num_format="0.00E+00"))
    return b.close()


def formula_no_cache(path: Path) -> Path:
    """A formula whose result is not saved in the file (the cached value is removed from the XML)."""
    tmp = path.with_suffix(".tmp.xlsx")
    b = Book(tmp)
    ws = b.wb.add_worksheet("Calc")
    ws.write("B2", 5, b.body())
    ws.write_formula("C2", "=B2*3", b.body(), 15)
    b.close()
    import re as _re

    with zipfile.ZipFile(tmp) as zin, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = _re.sub(rb"(<f>[^<]*</f>)<v>[^<]*</v>", rb"\1", data)
            zout.writestr(item, data)
    tmp.unlink()
    return path


def group_shape(path: Path) -> Path:
    """One picture inside a group whose child coordinate space is half the group's size (so the child must be scaled)."""
    b = Book(path)
    ws = b.wb.add_worksheet("Group")
    ws.write("B2", "anchor text", b.body())
    ws.insert_image("C4", write_png(b.img_dir, "grp.png", (90, 20, 20)))
    b.close()
    import re as _re

    tmp = path.with_suffix(".tmp.xlsx")
    path.replace(tmp)
    with zipfile.ZipFile(tmp) as zin:
        drawing = zin.read("xl/drawings/drawing1.xml").decode()
    pic = _re.search(r"<xdr:pic>.*?</xdr:pic>", drawing, _re.S).group(0)
    off = _re.search(r'<a:off x="(\d+)" y="(\d+)"/>', pic)
    ext = _re.search(r'<a:ext cx="(\d+)" cy="(\d+)"/>', pic)
    ox, oy, cx, cy = int(off.group(1)), int(off.group(2)), int(ext.group(1)), int(ext.group(2))
    grp = (f'<xdr:grpSp><xdr:nvGrpSpPr><xdr:cNvPr id="50" name="Group 1"/><xdr:cNvGrpSpPr/></xdr:nvGrpSpPr>'
           f'<xdr:grpSpPr><a:xfrm><a:off x="{ox}" y="{oy}"/><a:ext cx="{cx * 2}" cy="{cy * 2}"/>'
           f'<a:chOff x="{ox}" y="{oy}"/><a:chExt cx="{cx}" cy="{cy}"/></a:xfrm></xdr:grpSpPr>{pic}</xdr:grpSp>')
    drawing = drawing.replace(pic, grp)
    with zipfile.ZipFile(tmp) as zin, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = drawing.encode() if item.filename == "xl/drawings/drawing1.xml" else zin.read(item.filename)
            zout.writestr(item, data)
    tmp.unlink()
    return path


def big_sheet(path: Path, rows: int = 20000) -> Path:
    wb = xlsxwriter.Workbook(str(path), {"constant_memory": True})
    ws = wb.add_worksheet("Big")
    for c in range(12):
        ws.write(0, c, f"col{c}")
    for r in range(1, rows + 1):
        ws.write_string(r, 0, f"row {r} text")
        for c in range(1, 12):
            ws.write_number(r, c, (r * (c + 1)) % 997 + 0.5)
    wb.close()
    return path


def empty_sheet(path: Path) -> Path:
    b = Book(path)
    b.wb.add_worksheet("Empty")
    return b.close()


def merged_only_sheet(path: Path) -> Path:
    b = Book(path)
    ws = b.wb.add_worksheet("Merged only")
    ws.merge_range("B2:D2", "", b.body())
    ws.merge_range("B4:B6", "", b.body())
    return b.close()
