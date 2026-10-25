"""Deterministic cleaning: text noise and noise pictures for PDF / Word / PowerPoint."""
import io

from PIL import Image

from app.ingestion.cleaning import clean_document
from app.ingestion.models import Element, ParsedDocument, RawImage


def png(w, h, color=(200, 30, 30), noise=True):
    """noise=False: one flat colour (blank). noise=True: a second colour fills 40 % of the picture (has content)."""
    im = Image.new("RGB", (w, h), color)
    if noise:
        im.paste((250 - color[0], 240 - color[1], 40), (w // 5, h // 5, w * 3 // 5, h * 3 // 5))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def pages(texts, key="page", ftype="pdf", images=None):
    els = [Element("text", t, [], {key: i}) for i, t in enumerate(texts, start=1)]
    return ParsedDocument("x", ftype, els, {}, [], images or [])


def test_page_numbers_separators_toc_and_boilerplate_are_removed():
    doc = pages(["Intro text about the sensor.\n1\n__________\nJLR Confidential\nPage 1 of 9",
                 "1.1 Range ........ 5\nThe range is 5.5 m.\n- 2 -"])
    clean_document(doc)
    assert [e.text for e in doc.elements] == ["Intro text about the sensor.", "The range is 5.5 m."]
    lines = doc.stats["cleaning"]["lines_removed"]
    assert lines["page_number"] == 3 and lines["separator"] == 1 and lines["toc_leader"] == 1 and lines["boilerplate"] == 1
    assert doc.stats["cleaning"]["examples"]


def test_lines_repeated_on_many_pages_are_headers_and_removed():
    texts = [f"Doc 123 Radar Spec - Page {i} of 8\nReal content number {i} is here." for i in range(1, 9)]
    doc = pages(texts)
    clean_document(doc)
    assert all("Radar Spec" not in e.text for e in doc.elements)
    assert doc.elements[3].text == "Real content number 4 is here."
    assert doc.stats["cleaning"]["lines_removed"]["repeated"] == 8 and doc.stats["cleaning"]["lines_removed"].get("page_number", 0) == 0


def test_few_pages_keep_repeating_lines_and_numbers_in_decks_are_content():
    doc = pages(["Overview\nBody one.", "Overview\nBody two."])  # only 2 pages: repetition proves nothing
    clean_document(doc)
    assert doc.elements[0].text.startswith("Overview")
    deck = pages(["Torque\n42", "Other"], key="slide", ftype="pptx")
    clean_document(deck)
    assert deck.elements[0].text == "Torque\n42"  # a lone number on a slide is data unless it is the slide number
    deck2 = pages(["Title\n1", "Next\n2"], key="slide", ftype="pptx")
    clean_document(deck2)
    assert [e.text for e in deck2.elements] == ["Title", "Next"]


def test_records_and_excel_are_never_touched():
    rec = Element("record", "A: 1", ["S"], {"row": 1}, {"A": 1}, "1")
    doc = ParsedDocument("x", "pdf", [rec, Element("text", "Page 1", [], {"page": 1})])
    clean_document(doc)
    assert doc.elements == [rec]
    xl = ParsedDocument("x", "xlsx", [Element("text", "Page 1", [], {"page": 1})])
    assert clean_document(xl).elements[0].text == "Page 1" and "cleaning" not in xl.stats


def test_noise_pictures_are_dropped_and_counted():
    logo = png(300, 80)
    imgs = [RawImage(logo, "png", {"slide": i}, "") for i in range(1, 7)]  # logo on every slide
    imgs += [RawImage(png(20, 20), "png", {"slide": 1}, ""),  # icon
             RawImage(png(900, 30), "png", {"slide": 2}, ""),  # divider line
             RawImage(png(300, 300, noise=False), "png", {"slide": 3}, ""),  # empty
             RawImage(png(400, 300, (10, 120, 200)), "png", {"slide": 4}, "diagram")]  # the real picture
    doc = pages([f"Slide text {i}" for i in range(1, 7)], key="slide", ftype="pptx", images=imgs)
    clean_document(doc)
    assert [i.context for i in doc.images] == ["diagram"]
    assert doc.stats["cleaning"]["images_dropped"] == {"repeated": 6, "too_small": 1, "extreme_aspect": 1, "blank": 1}


def test_picture_on_four_pages_is_noise_but_on_three_is_kept():
    logo = png(300, 80)
    def run(n):
        doc = pages([f"text {i}" for i in range(1, 8)], images=[RawImage(logo, "png", {"page": i}, "") for i in range(1, n + 1)])
        return len(clean_document(doc).images)
    assert run(3) == 3 and run(4) == 0


def test_header_or_footer_table_repeated_on_pages_is_removed_but_a_data_table_stays():
    footer = lambda page: Element("record", "Doc no: 123\nOwner: Radar team", [], {"page": page, "table": 1}, {"Doc no": "123"}, "123")  # noqa: E731
    data = Element("record", "Vehicle: Audi\nRange: 5.5", [], {"page": 2, "table": 2}, {"Vehicle": "Audi"}, "Audi")
    doc = ParsedDocument("x", "pdf", [footer(i) for i in range(1, 6)] + [data])
    clean_document(doc)
    assert doc.elements == [data] and doc.stats["cleaning"]["lines_removed"]["repeated_table_row"] == 5
    three = ParsedDocument("x", "pdf", [footer(i) for i in range(1, 4)])
    assert len(clean_document(three).elements) == 3


def test_exact_duplicate_in_the_same_place_is_kept_once_and_unknown_formats_are_kept():
    p = png(300, 200, (1, 2, 3))
    doc = pages(["a", "b"], images=[RawImage(p, "png", {"page": 1}, "one"), RawImage(p, "png", {"page": 1}, "two"),
                                   RawImage(b"not an image", "emf", {"page": 2}, "vector")])
    clean_document(doc)
    assert [i.context for i in doc.images] == ["one", "vector"] and doc.stats["cleaning"]["images_dropped"] == {"duplicate": 1}
