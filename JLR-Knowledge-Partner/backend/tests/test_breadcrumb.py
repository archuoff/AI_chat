"""Every chunk carries a breadcrumb (path) and relations (group, neighbours, link key) for retrieval."""
import pytest

from app.images import catalog
from app.ingestion.chunker import build_chunks
from app.ingestion.models import Element, ParsedDocument
from app.rag.retriever import _finalise


def build(file_type, *els, name="spec"):
    return build_chunks("d", ParsedDocument(f"{name}.{file_type}", file_type, list(els)), 1200, 150)


def test_excel_row_breadcrumb_has_sheet_box_section_and_row_title():
    rec = Element("record", "Vehicle: Audi\nRange: 5.5", ["Radar", "Market Study", "Front"], {"sheet": "Radar", "row": 5, "range": "B5:F5"},
                  {"Vehicle": "Audi"}, "Audi")
    [c] = build("xlsx", rec, name="radar")
    assert c.breadcrumb == ["radar.xlsx", "Radar", "Market Study", "Front", "Audi"]
    assert c.context == "radar.xlsx › Radar › Market Study › Front › Audi (row 5)"
    assert c.relations["row_key"] == "Radar!5" and c.relations["group"] == "table:Radar!B:F" and c.relations["parent"] == "Front"


def test_pdf_and_powerpoint_breadcrumbs_include_page_or_slide():
    [p] = build("pdf", Element("text", "Range is 5.5 m.", ["1 Scope", "1.1 Range"], {"page": 2}))
    assert p.breadcrumb == ["spec.pdf", "1 Scope", "1.1 Range", "Page 2"] and p.relations["group"] == p.extra["section_key"]
    [s] = build("pptx", Element("text", "Bracket details", ["Radar bracket"], {"slide": 4}))
    assert s.breadcrumb == ["spec.pptx", "Radar bracket", "Slide 4"] and s.relations["row_key"] == "slide:4"
    [d] = build("pptx", Element("text", "x", ["Slide 4"], {"slide": 4}))
    assert d.breadcrumb == ["spec.pptx", "Slide 4"]  # no repeat when the title is the default "Slide 4"


def test_neighbours_are_chained_inside_their_group_only():
    a = Element("record", "A: 1", ["S"], {"sheet": "S", "row": 2, "range": "A2:B2"}, {"A": 1}, "1")
    b = Element("record", "A: 2", ["S"], {"sheet": "S", "row": 3, "range": "A3:B3"}, {"A": 2}, "2")
    other = Element("record", "X: 1", ["T"], {"sheet": "S", "row": 9, "range": "D9:E9"}, {"X": 1}, "1")  # another table (columns D:E)
    c1, c2, c3 = build("xlsx", a, b, other)
    assert c1.relations["next"] == c2.id and c2.relations["prev"] == c1.id and c1.relations["prev"] is None
    assert c3.relations["prev"] is None and c3.relations["next"] is None


def test_every_other_format_gets_a_breadcrumb_too():
    [w] = build("docx", Element("text", "Para", ["Chapter 1", "Scope"], {}), name="spec")
    assert w.breadcrumb == ["spec.docx", "Chapter 1", "Scope"]
    [m] = build("md", Element("text", "Para", ["Intro"], {}), name="notes")
    assert m.breadcrumb == ["notes.md", "Intro"]
    [c] = build("csv", Element("record", "A: 1", ["data"], {"row": 2}, {"A": 1}, "1"), name="data")
    assert c.breadcrumb == ["data.csv", "data", "1"]


def test_evidence_and_picture_chunks_expose_breadcrumb_and_relations(api):
    from app.ingestion.models import RawImage
    import io
    from PIL import Image
    im = Image.new("RGB", (400, 300), (200, 30, 30)); im.paste((10, 200, 10), (50, 50, 250, 200))
    buf = io.BytesIO(); im.save(buf, "PNG")
    catalog.sync("doc1", [RawImage(buf.getvalue(), "png", {"sheet": "Radar", "row": 5, "cell": "D5"}, "Sheet: Radar\nBox title: Market Study\nColumn: Audi")])
    [img] = catalog.list_images("doc1")
    catalog.record_result(img.id, description="Summary: red car")
    [pc] = catalog.image_chunks("doc1", "radar.xlsx", 0)
    assert pc.breadcrumb == ["radar.xlsx", "Radar", "Market Study", "Picture", "Radar D5"] and pc.relations["row_key"] == "Radar!5"
    ev = _finalise({"chunks": [{"id": "x", "doc_id": "d", "kind": "image", "text": "t", "context": "c", "location": {}, "file_name": "f",
                                "file_type": "xlsx", "breadcrumb": pc.breadcrumb, "relations": pc.relations, "chunk_index": 0}],
                    "score": 0.5, "sim": 0.1})
    assert ev["breadcrumb"] == pc.breadcrumb and ev["relations"]["row_key"] == "Radar!5"
