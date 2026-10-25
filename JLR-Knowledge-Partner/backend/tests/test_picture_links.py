"""Retrieval link: a picture and the row / slide it sits with are returned together."""
from app.rag import retriever


class FakeStore:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def scroll_chunks(self, flt, limit=500, fields=True):
        self.calls.append(flt)
        out = []
        for c in self.chunks:
            if all((c.get("location") or {}).get(k.split(".", 1)[1]) == v if k.startswith("location.") else c.get(k) == v for k, v in flt.items()):
                out.append(c)
        return out[:limit]


def chunk(cid, kind, loc, doc="d", text=""):
    return {"id": cid, "doc_id": doc, "kind": kind, "location": loc, "text": text or cid, "chunk_index": int(cid[1:]) if cid[1:].isdigit() else 0}


def unit(c, grade=2):
    return {"chunks": [c], "score": 0.8, "sim": 0.5, "grade": grade}


def test_row_record_brings_the_pictures_of_its_row(monkeypatch):
    row5, row6 = chunk("r5", "record", {"sheet": "S", "row": 5, "range": "B5:F5"}), chunk("r6", "record", {"sheet": "S", "row": 6, "range": "B6:F6"})
    pic5 = chunk("p5", "image", {"sheet": "S", "row": 5, "cell": "D5", "image": "i1"})
    pic6 = chunk("p6", "image", {"sheet": "S", "row": 6, "cell": "D6", "image": "i2"})
    other_doc = chunk("p9", "image", {"sheet": "S", "row": 5, "image": "i9"}, doc="other")
    monkeypatch.setattr(retriever, "get_store", lambda: FakeStore([row5, row6, pic5, pic6, other_doc]))
    final = [unit(row5)]
    assert retriever._link_pictures(final, 8) == 1
    assert [u["chunks"][0]["id"] for u in final] == ["r5", "p5"] and final[1]["linked"] and final[1]["grade"] == 2


def test_picture_brings_its_row_record_before_it_and_nothing_twice(monkeypatch):
    row5 = chunk("r5", "record", {"sheet": "S", "row": 5, "range": "B5:F5"})
    pic5 = chunk("p5", "image", {"sheet": "S", "row": 5, "cell": "D5", "image": "i1"})
    monkeypatch.setattr(retriever, "get_store", lambda: FakeStore([row5, pic5]))
    final = [unit(pic5)]
    assert retriever._link_pictures(final, 8) == 1 and [u["chunks"][0]["id"] for u in final] == ["r5", "p5"]
    both = [unit(row5), unit(pic5)]  # both already selected: nothing is added or repeated
    assert retriever._link_pictures(both, 8) == 0 and len(both) == 2


def test_slide_text_and_pictures_link_and_cap_is_respected(monkeypatch):
    text = chunk("t1", "text", {"slide": 4})
    pics = [chunk(f"p{i}", "image", {"slide": 4, "image": f"i{i}"}) for i in range(1, 6)]
    store = FakeStore([text, *pics])
    monkeypatch.setattr(retriever, "get_store", lambda: store)
    final = [unit(text)]
    assert retriever._link_pictures(final, 3) == 3 and len(final) == 4
    only_pic = [unit(pics[0])]
    assert retriever._link_pictures(only_pic, 8) == 1 and only_pic[0]["chunks"][0]["id"] == "t1"


def test_pdf_pages_and_free_sheet_text_are_not_linked(monkeypatch):
    store = FakeStore([chunk("t1", "text", {"page": 2}), chunk("n1", "text", {"sheet": "S", "rows": "3-3"})])
    monkeypatch.setattr(retriever, "get_store", lambda: store)
    final = [unit(store.chunks[0]), unit(store.chunks[1])]
    assert retriever._link_pictures(final, 8) == 0 and store.calls == []
