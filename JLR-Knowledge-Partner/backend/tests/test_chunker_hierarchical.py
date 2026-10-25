"""Hierarchical chunking: sections, semantic split inside long sections, small-to-big expansion."""
from app.ingestion.chunker import build_chunks, split_semantic
from app.ingestion.models import Element, ParsedDocument
from app.rag import retriever

RADAR = "The radar sensor measures the distance to objects ahead of the vehicle. "
BENCH = "The bench test applies vibration to the bracket for many hours at room temperature. "


def fake_embed(texts):
    """radar sentences -> one direction, bench sentences -> another (no model needed)."""
    return [[1.0, 0.0] if "radar" in t.lower() else [0.0, 1.0] for t in texts]


def pdf(*elements, file_type="pdf"):
    return ParsedDocument("spec.pdf", file_type, list(elements))


def section(path, text, page=1):
    return Element("text", text, path, {"page": page})


def test_short_section_is_one_chunk_with_section_key():
    doc = pdf(section(["1 Scope"], "Short text."), section(["1 Scope"], "More text."))
    chunks = build_chunks("d", doc, 1200, 150)
    assert len(chunks) == 1 and chunks[0].text == "Short text.\nMore text."
    assert chunks[0].extra["section_key"] == "d:s1" and chunks[0].context.startswith("spec.pdf › 1 Scope")


def test_long_section_splits_at_the_topic_change():
    text = "\n".join([RADAR + f"Item {i}." for i in range(8)] + [BENCH + f"Step {i}." for i in range(8)])
    parts = split_semantic(text, fake_embed, None, 300, 1200, 25)
    assert len(parts) == 2
    assert "radar" in parts[0].lower() and "bench" not in parts[0].lower()
    assert "bench" in parts[1].lower() and "radar" not in parts[1].lower()


def test_chunks_of_one_section_share_a_key_and_each_section_has_its_own():
    long = "\n".join([RADAR + f"Item {i}." for i in range(12)] + [BENCH + f"Step {i}." for i in range(12)])
    doc = pdf(section(["A"], long), section(["B"], "Other short section."))
    chunks = build_chunks("d", doc, 1200, 150, fake_embed)
    keys = {c.section[0]: {x.extra["section_key"] for x in chunks if x.section == c.section} for c in chunks}
    assert len(keys["A"]) == 1 and len(keys["B"]) == 1 and keys["A"] != keys["B"]
    assert sum(c.section == ["A"] for c in chunks) >= 2 and all(c.extra["section_chars"] == len(long) for c in chunks if c.section == ["A"])


def test_without_embeddings_or_when_they_fail_the_size_splitter_is_used():
    long = "\n".join(RADAR + f"Item {i}." for i in range(60))
    doc = pdf(section(["A"], long))
    no_embed = build_chunks("d", doc, 500, 50)
    assert len(no_embed) > 1 and all(len(c.text) <= 500 for c in no_embed)

    def broken(_):
        raise RuntimeError("embedding service down")
    assert len(build_chunks("d", doc, 500, 50, broken)) == len(no_embed)


def test_unaffected_inputs_keep_the_old_behaviour():
    pages = pdf(Element("text", "page text", [], {"page": 1}))  # pypdf style: no heading path
    assert "section_key" not in build_chunks("d", pages, 1200, 150)[0].extra
    xl = pdf(section(["Sheet"], "Note"), Element("record", "A: 1", ["Sheet"], {"row": 2}, {"A": 1}, "1"), file_type="xlsx")
    assert all("section_key" not in c.extra for c in build_chunks("d", xl, 1200, 150))
    rec = pdf(section(["1"], "Intro"), Element("record", "Vehicle: Audi", ["1"], {"page": 1, "row": 1}, {"Vehicle": "Audi"}, "Audi"))
    kinds = [c.kind for c in build_chunks("d", rec, 1200, 150)]
    assert kinds == ["text", "record"]


def test_matching_piece_brings_back_the_whole_short_section(monkeypatch):
    stored = [{"id": f"c{i}", "doc_id": "d", "chunk_index": i, "section_key": "d:s1", "section_chars": 3000, "kind": "text",
               "location": {"page": 1}, "text": f"piece {i}"} for i in range(3)]

    class FakeStore:
        def scroll_chunks(self, flt, limit=500, fields=True):
            assert flt == {"doc_id": "d", "section_key": "d:s1"}
            return stored
    monkeypatch.setattr(retriever, "get_store", lambda: FakeStore())
    unit = {"chunks": [stored[1]]}
    retriever._expand(unit)
    assert [c["id"] for c in unit["chunks"]] == ["c0", "c1", "c2"]

    huge = dict(stored[1], section_chars=50000, parts=3)  # too long to return whole: old neighbour logic, here a no-op fetch
    monkeypatch.setattr(retriever, "get_store", lambda: type("S", (), {"scroll_chunks": lambda self, f, limit=0: []})())
    unit = {"chunks": [huge]}
    retriever._expand(unit)
    assert len(unit["chunks"]) == 1
