import random

from app.ingestion.models import Element, ParsedDocument
from app.ingestion import similarity as sim


def doc(name, records=(), lines=(), file_type="xlsx", stats=None):
    els = [Element("record", " ".join(f"{k}: {v}" for k, v in r.items()), ["S"], {"row": i}, r, str(next(iter(r.values()))))
           for i, r in enumerate(records, 1)]
    els += [Element("text", line, [], {"page": 1}) for line in lines]
    return ParsedDocument(name, file_type, els, stats or {})


def rows(n, start=0, **extra):
    return [{"Vehicle": f"Car {i}", "Max range": f"{i % 7 + 1}.50 m", "Maker": "BOSCH", **extra} for i in range(start, start + n)]


def test_clean_name_removes_versions_dates_copies():
    assert sim.clean_name("Radar_spec Rev C (2).xlsx") == "radar spec"
    assert sim.clean_name("Radar spec v2.xlsx") == sim.clean_name("Radar spec v10.xlsx") == "radar spec"
    assert sim.clean_name("FMEA 2024-03-01 copy.xlsx") == "fmea"
    assert sim.clean_name("Report_20240301_final.pdf") == "report"


def test_clean_name_keeps_product_numbers():
    assert sim.clean_name("Radar Gen 2.xlsx") != sim.clean_name("Radar Gen 3.xlsx")
    assert sim.name_score("Radar spec Rev B.xlsx", "Radar spec Rev C.xlsx") == 1.0
    assert sim.name_score("Front PDC spec.xlsx", "Rear PDC spec.xlsx") < 0.9


def test_normalize_numbers_and_spacing():
    assert sim.normalize("5.50  m") == sim.normalize("5,5 M") == sim.normalize("5.5 m")
    assert sim.normalize("100.0") == "100"


def test_codes_survive_a_few_changed_cells():
    a, b = rows(200), rows(200)
    b[3]["Max range"] = "9.9 m"
    b[10]["Maker"] = "VALEO"
    ca, cb = set(sim.content_codes(doc("a.xlsx", a))), set(sim.content_codes(doc("b.xlsx", b)))
    assert sim.jaccard(ca, cb) > 0.9
    assert sim.jaccard(ca, set(sim.content_codes(doc("c.xlsx", rows(200, start=5000, Maker="X"))))) < 0.1


def test_sketch_estimates_overlap_of_large_documents():
    rnd = random.Random(1)
    base = [{"id": f"item-{rnd.random()}", "v": str(i)} for i in range(5000)]
    half = base[:2500] + [{"id": f"new-{rnd.random()}", "v": str(i)} for i in range(2500)]
    est = sim.jaccard(set(sim.content_codes(doc("a", base))), set(sim.content_codes(doc("b", half))))
    assert 0.2 < est < 0.5  # true Jaccard of the two cell sets is ~0.33


def entry(name, parsed, domain="adas", **kw):
    return {"doc_id": name, "file_name": name, "domain": domain, "content_hash": f"h-{name}",
            "signature": sim.build_signature(parsed, kw.pop("topic", None)), **kw}


def test_suggest_finds_update_and_ignores_template_siblings():
    template = [f"Template line number {i} shared by every sheet" for i in range(40)]
    old = entry("Radar spec Rev B.xlsx", doc("o", rows(120), template))
    front = entry("Front PDC spec.xlsx", doc("f", rows(120, start=1000, Maker="F"), template))
    rear = entry("Rear PDC spec.xlsx", doc("r", rows(120, start=2000, Maker="R"), template))
    other = entry("Materials.xlsx", doc("m", rows(50, start=3000, Maker="M"), template))
    new = doc("Radar spec Rev C.xlsx", rows(130), template)  # old rows + 10 new vehicles
    out = sim.suggest(new.file_name, "h-new", sim.build_signature(new, None), [old, front, rear, other], "adas")
    assert out["exact"] == []
    top = out["suggestions"][0]
    assert top["doc_id"] == old["doc_id"] and top["label"] == "likely"
    assert all(s["label"] != "likely" for s in out["suggestions"][1:])  # shared template alone is not an update


def test_suggest_exact_copy_under_another_name_and_superseded_flag():
    old = entry("a.xlsx", doc("a", rows(10)), superseded=True, replaced_by="b.xlsx")
    out = sim.suggest("copy of a.xlsx", "h-a.xlsx", sim.build_signature(doc("n", rows(10)), None), [old])
    assert out["exact"] and out["exact"][0]["superseded"] is True
    assert out["suggestions"] == []  # a hidden document is not suggested again


def test_suggest_without_signature_still_uses_the_name():
    plain = {"doc_id": "x", "file_name": "Radar spec Rev B.xlsx", "domain": "adas", "content_hash": "hx"}
    out = sim.suggest("Radar spec Rev C.xlsx", "h", sim.build_signature(doc("n", rows(5)), None), [plain])
    assert out["unchecked"] == 1 and out["suggestions"][0]["label"] == "related"


def test_size_of_sheets_and_slides():
    x = doc("a.xlsx", rows(3), stats={"sheets": {"A": {"skipped": False}, "B": {"skipped": True}}})
    assert sim.size_of(x) == {"unit": "sheets", "units": 1, "records": 3, "text_blocks": 0}
    p = doc("a.pptx", lines=["x" * 20], file_type="pptx", stats={"slides": 12})
    assert sim.size_of(p)["units"] == 12
