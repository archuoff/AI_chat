"""The Sheet preview returns every picture with the cell it sits in."""
import pytest

testkit = pytest.importorskip("experiment.excel_extractor.testkit")


def test_preview_lists_pictures_at_their_cells(api, tmp_path):
    data = testkit.radar_like(tmp_path / "radar.xlsx").read_bytes()
    chk = api.post("/api/documents/check", files={"file": ("radar.xlsx", data)}, data={"domain": "adas"}).json()
    done = api.post("/api/documents/commit", json={"check_id": chk["check_id"], "domain": "adas", "intent": "new"})
    assert done.status_code == 200, done.text
    doc_id = done.json()["results"][0]["doc_id"]
    sheet = api.get(f"/api/documents/{doc_id}/excel-preview").json()["sheet"]
    in_cell = [p for p in sheet["pictures"] if p["placement"] == "in_cell"]
    assert len(in_cell) >= 4 and {(p["r"], p["c"]) for p in in_cell} >= {(5, 3), (5, 4), (5, 5), (5, 6)}  # C5:F5, the picture row
    audi = next(p for p in in_cell if (p["r"], p["c"]) == (5, 4))
    assert audi["status"] in ("waiting", "skipped") and audi["reason"] != "unsupported" and "Column: AUDI SQ6 e-tron" in audi["context"] and audi["width"] > 0
    assert sheet["coverage"]["ignored_count"] == 0
    row5 = next(r for r in sheet["rows"] if r["r"] == 5)
    assert any(c["v"].startswith("[picture") for c in row5["cells"])
    assert api.get(f"/api/images/{audi['id']}/file?thumb=true").status_code == 200
    # a picture anchored inside a merged area is shown in the area's top-left cell, never in a covered cell
    for p in sheet["pictures"]:
        for m in sheet["merges"]:
            inside = m["r0"] <= p["r"] <= m["r1"] and m["c0"] <= p["c"] <= m["c1"]
            assert not inside or (p["r"], p["c"]) == (m["r0"], m["c0"])
    assert len(sheet["pictures"]) == 13
