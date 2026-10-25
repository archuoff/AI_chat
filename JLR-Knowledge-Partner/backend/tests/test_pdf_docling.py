"""The Docling export is tested on a hand-built DoclingDocument (needs docling-core, not the PDF models)."""
import pytest

pytest.importorskip("docling_core")
from docling_core.types.doc import BoundingBox, DocItemLabel, DoclingDocument, ProvenanceItem, Size, TableCell, TableData
from docling_core.types.doc.base import CoordOrigin

from app.ingestion.chunker import build_chunks
from app.ingestion.pdf_docling import export_chunk_ready, to_parsed_document


def _prov(page, top=100.0, bottom=140.0):
    return ProvenanceItem(page_no=page, bbox=BoundingBox(l=50, t=top, r=500, b=bottom, coord_origin=CoordOrigin.TOPLEFT), charspan=(0, 1))


def _table(rows, header_rows=1):
    cells = [TableCell(text=t, start_row_offset_idx=r, end_row_offset_idx=r + 1, start_col_offset_idx=c, end_col_offset_idx=c + 1,
                       column_header=r < header_rows) for r, row in enumerate(rows) for c, t in enumerate(row)]
    return TableData(table_cells=cells, num_rows=len(rows), num_cols=len(rows[0]))


@pytest.fixture
def doc():
    d = DoclingDocument(name="spec")
    for n in (1, 2, 3):
        d.add_page(page_no=n, size=Size(width=600, height=800))
    d.add_text(DocItemLabel.PAGE_HEADER, "JLR Confidential", prov=_prov(1, 5, 20))
    d.add_heading("1 Scope", level=1, prov=_prov(1))
    d.add_text(DocItemLabel.PARAGRAPH, "This document covers radar sensors.", prov=_prov(1, 150, 180))
    d.add_heading("1.1 Range", level=1, prov=_prov(1, 200, 220))  # Docling reports every heading as level 1
    d.add_text(DocItemLabel.PARAGRAPH, "Maximum range is 5.5 m.", prov=_prov(1, 230, 250))
    d.add_table(_table([["Vehicle", "Range", "IP"], ["Audi", "5.5 m", "IP67"], ["BMW", "0", "IP6K9K"]]), prov=_prov(2, 100, 300))
    d.add_heading("2 Test", level=1, prov=_prov(3))
    d.add_heading("2.1 Method", level=1, prov=_prov(3, 150, 170))
    d.add_text(DocItemLabel.PARAGRAPH, "Run the bench test.", prov=_prov(3, 180, 200))
    d.add_picture(prov=_prov(3, 300, 500))
    return d


def test_sections_use_numbering_when_levels_are_flat(doc):
    ex = export_chunk_ready(doc, "spec.pdf")
    by_title = {s["title"]: s for s in ex["sections"]}
    assert [s["level"] for s in ex["sections"][1:]] == [1, 2, 1, 2]
    assert by_title["1.1 Range"]["parent"] == by_title["1 Scope"]["id"]
    assert ex["checks"]["heading_levels_from_numbering"] and not ex["checks"]["heading_levels_flat"]
    para = next(b for b in ex["blocks"] if b["text"].startswith("Maximum"))
    assert para["heading_path"] == ["1 Scope", "1.1 Range"]
    assert 0 <= para["bbox"][0] < para["bbox"][2] <= 1


def test_tables_keep_headers_zeros_and_records(doc):
    t = export_chunk_ready(doc, "spec.pdf")["tables"][0]
    assert t["headers"] == ["Vehicle", "Range", "IP"] and t["header_rows"] == 1
    assert t["records"][1] == {"Vehicle": "BMW", "Range": "0", "IP": "IP6K9K"}
    assert t["heading_path"] == ["1 Scope", "1.1 Range"] and t["page"] == 2


def test_running_header_removed_and_counted(doc):
    ex = export_chunk_ready(doc, "spec.pdf")
    assert not any("Confidential" in b["text"] for b in ex["blocks"] if b.get("text"))
    assert ex["checks"]["furniture_removed"] == 1


def test_picture_has_context_and_checks_flag_problems(doc):
    ex = export_chunk_ready(doc, "spec.pdf")
    pic = ex["pictures"][0]
    assert pic["page"] == 3 and "Run the bench test." in pic["context"] and pic["heading_path"] == ["2 Test", "2.1 Method"]
    assert ex["checks"]["pages_without_text"] == []
    empty = DoclingDocument(name="scan")
    empty.add_page(page_no=1, size=Size(width=600, height=800))
    ex2 = export_chunk_ready(empty, "scan.pdf")
    assert ex2["checks"]["pages_without_text"] == [1] and ex2["checks"]["problems"]


def test_adapter_feeds_the_existing_chunker(doc):
    parsed = to_parsed_document(export_chunk_ready(doc, "spec.pdf"))
    assert parsed.stats["tables"] == 1 and parsed.stats["engine"] == "docling"
    records = [e for e in parsed.elements if e.kind == "record"]
    assert len(records) == 2 and records[0].section == ["1 Scope", "1.1 Range"] and records[1].fields["Range"] == "0"
    text = next(e for e in parsed.elements if e.kind == "text" and "radar" in e.text)
    assert text.section == ["1 Scope"] and text.location["page"] == 1
    chunks = build_chunks("doc1", parsed, 1200, 150)
    assert chunks and all(c.context.startswith("spec.pdf") for c in chunks)
