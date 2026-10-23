import io

from openpyxl import Workbook


def xlsx(n_rows, start=0, extra_sheet=False):
    wb = Workbook()
    ws = wb.active
    ws.title = "Radar"
    ws.append(["Vehicle", "Max range", "Maker"])
    for i in range(start, start + n_rows):
        ws.append([f"Car {i}", f"{i % 7 + 1}.5 m", "BOSCH"])
    if extra_sheet:
        wb.create_sheet("Other").append(["Part", "Weight"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def check(api, name, data, domain="adas"):
    r = api.post("/api/documents/check", files={"file": (name, data)}, data={"domain": domain})
    assert r.status_code == 200, r.text
    return r.json()


def commit(api, chk, **kw):
    return api.post("/api/documents/commit", json={"check_id": chk["check_id"], "domain": "adas", **kw})


def test_new_then_update_hides_old_and_restore(api):
    from app.auth import Principal, access_filters
    from app.store import get_store

    b = xlsx(60)
    c1 = check(api, "Radar spec Rev B.xlsx", b)
    assert c1["exact"] == [] and c1["suggestions"] == [] and c1["same_name"] is None
    r = commit(api, c1, intent="new")
    assert r.status_code == 200 and r.json()["results"][0]["status"] == "indexed"
    old_id = r.json()["results"][0]["doc_id"]
    doc = api.get(f"/api/documents/{old_id}").json()
    assert "signature" not in doc and doc["sig_size"]["units"] == 1
    assert api.get("/api/documents").json()[0]["compared"] is True

    # Rev C = the 60 old rows + 10 new ones
    c2 = check(api, "Radar spec Rev C.xlsx", xlsx(70))
    top = c2["suggestions"][0]
    assert top["doc_id"] == old_id and top["label"] == "likely" and "same content" in " ".join(top["reasons"])
    assert [o["doc_id"] for o in c2["others"]] == [old_id]
    r = commit(api, c2, intent="update", replaces=old_id)
    res = r.json()["results"][0]
    assert res["status"] == "indexed" and res["replaced"]["doc_id"] == old_id
    new_id = res["doc_id"]

    docs = {d["doc_id"]: d for d in api.get("/api/documents").json()}
    assert docs[old_id]["superseded"] and docs[old_id]["replaced_by"] == new_id and docs[new_id]["replaces"] == old_id
    store = get_store()
    p = Principal(1, "dev", "Dev", "developer")
    hits = store.search("Car 5", 50, access_filters(p, None))
    assert hits and all(h["doc_id"] == new_id for h in hits)  # chat never sees the replaced version
    assert any(h["doc_id"] == old_id for h in store.search("Car 5", 50))  # still stored

    # the replaced file is an exact copy of what was uploaded first, and says so
    c3 = check(api, "Radar spec Rev B copy.xlsx", b)
    assert c3["exact"][0]["doc_id"] == old_id and c3["exact"][0]["superseded"] is True
    assert commit(api, c3, intent="new").status_code == 409  # duplicate needs a deliberate choice
    assert commit(api, check(api, "Radar spec Rev B copy.xlsx", b), intent="new", allow_duplicate=True).status_code == 200

    # undo
    assert api.post(f"/api/documents/{old_id}/restore").status_code == 200
    docs = {d["doc_id"]: d for d in api.get("/api/documents").json()}
    assert not docs[old_id]["superseded"] and not docs[new_id].get("replaces")
    assert any(h["doc_id"] == old_id for h in store.search("Car 5", 50, access_filters(p, None)))
    assert api.post(f"/api/documents/{old_id}/restore").status_code == 409


def test_same_name_guards(api):
    r = commit(api, check(api, "Spec.xlsx", xlsx(10)), intent="new")
    doc_id = r.json()["results"][0]["doc_id"]
    r = commit(api, check(api, "Spec.xlsx", xlsx(12)), intent="new")
    assert r.status_code == 409 and "already exists" in r.json()["detail"]
    other = commit(api, check(api, "Other.xlsx", xlsx(10, start=900)), intent="new").json()["results"][0]["doc_id"]
    # a file named like document A must not overwrite A when it claims to update B
    r = commit(api, check(api, "Spec.xlsx", xlsx(12)), intent="update", replaces=other)
    assert r.status_code == 409
    # updating the same-named document is the in-place path; the old original is archived
    r = commit(api, check(api, "Spec.xlsx", xlsx(12)), intent="update", replaces=doc_id)
    assert r.status_code == 200 and r.json()["results"][0]["status"] == "indexed" and "replaced" not in r.json()["results"][0]
    from app.graphs.ingest_graph import source_dir
    assert list((source_dir(doc_id) / "versions").glob("*/Spec.xlsx"))
    assert api.post("/api/documents/check", files={"file": ("x.exe", b"1")}).status_code == 415
    assert commit(api, {"check_id": "nope"}, intent="new").status_code == 404


def test_update_of_confidential_stays_confidential_and_delete_restores(api):
    old = commit(api, check(api, "Secret v1.xlsx", xlsx(20)), intent="new").json()["results"][0]["doc_id"]
    assert api.patch(f"/api/documents/{old}/access", json={"confidential": True}).status_code == 200
    res = commit(api, check(api, "Secret v2.xlsx", xlsx(25)), intent="update", replaces=old).json()["results"][0]
    new = res["doc_id"]
    docs = {d["doc_id"]: d for d in api.get("/api/documents").json()}
    assert docs[new]["confidential"] is True and docs[old]["superseded"]
    assert api.delete(f"/api/documents/{new}").status_code == 200
    assert not {d["doc_id"]: d for d in api.get("/api/documents").json()}[old]["superseded"]


def test_decisions_are_logged_and_signatures_backfill(api):
    from app.auth.db import SessionLocal, UploadDecision

    commit(api, check(api, "A.xlsx", xlsx(10)), intent="new")
    with SessionLocal() as db:
        rows = db.query(UploadDecision).all()
    assert len(rows) == 1 and rows[0].intent == "new" and rows[0].result_status == "indexed"
    from app.store import get_store
    doc_id = api.get("/api/documents").json()[0]["doc_id"]
    get_store().client.delete_payload(get_store().settings.documents_collection, keys=["signature", "sig_size"], points=[doc_id])
    assert api.get("/api/documents").json()[0]["compared"] is False
    assert api.post("/api/documents/signatures").json() == {"built": 1, "failed": []}
    assert api.get("/api/documents").json()[0]["compared"] is True
