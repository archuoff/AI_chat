import io
import json
import re

import pytest
from openpyxl import Workbook

from conftest import H


def xlsx_bytes(rows, sheet="Parts"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(client, who, name, content, domain="", ctype="application/octet-stream"):
    return client.post("/engismart/documents/check", headers=H(who), files={"file": (name, content, ctype)}, data={"domain": domain})


def commit(client, who, check_id, domain, **kw):
    return client.post("/engismart/documents/commit", headers=H(who), json={"check_id": check_id, "domain": domain, **kw})


# ---------------------------------------------------------------- access
def test_no_token_is_refused(client):
    r = client.get("/engismart/me")  # answered by the platform's track_module_usage dependency (its own error shape)
    assert r.status_code == 401
    r = client.get("/engismart/images/x/file")  # the file router has no tracking: our own check answers, in the platform's envelope
    assert r.status_code == 401 and r.json()["status"] is False


def test_user_with_domain(client):
    r = client.get("/engismart/me", headers=H("anil"))
    assert r.status_code == 200
    d = r.json()
    assert d["status"] is True and d["data"]["role"] == "user" and d["data"]["domains"] == ["adas"]


def test_user_with_two_domains(client):
    assert client.get("/engismart/me", headers=H("priya")).json()["data"]["domains"] == ["adas", "eds"]


def test_user_without_domain_is_refused(client):
    r = client.get("/engismart/me", headers=H("nodomain"))
    assert r.status_code == 403 and "domain" in r.json()["message"].lower() and r.json()["status"] is False


def test_user_without_application_is_refused(client):
    r = client.get("/engismart/me", headers=H("noapp"))
    assert r.status_code == 403 and "access to Engismart" in r.json()["message"]


def test_roles(client):
    assert client.get("/engismart/me", headers=H("sue")).json()["data"]["role"] == "superuser"
    assert client.get("/engismart/me", headers=H("dev")).json()["data"]["role"] == "developer"
    assert client.get("/engismart/me", headers=H("root")).json()["data"]["role"] == "developer"  # platform admin


def test_superuser_sees_all_domains_without_domain_rows(client):
    d = client.get("/engismart/me", headers=H("sue")).json()["data"]
    assert len(d["domains"]) == 6


def test_manage_knowledge_is_not_for_normal_users(client):
    for path in ("/engismart/documents", "/engismart/images/summary", "/engismart/images/job"):
        assert client.get(path, headers=H("anil")).status_code == 403, path
        assert client.get(path, headers=H("sue")).status_code == 200, path


def test_domains_list_by_role(client):
    user = client.get("/engismart/domains", headers=H("anil")).json()["data"]
    assert [d["id"] for d in user] == ["adas"]
    mgr = client.get("/engismart/domains", headers=H("sue")).json()["data"]
    assert len(mgr) == 7 and "documents" in mgr[0]  # six domains + unassigned, with counts


def test_health_details_are_for_developers(client):
    assert "qdrant" not in client.get("/engismart/health", headers=H("anil")).json()["data"]
    assert "qdrant" in client.get("/engismart/health", headers=H("dev")).json()["data"]


def test_removed_endpoints_are_gone(client):
    for method, path in (("get", "/engismart/users"), ("get", "/engismart/usage/summary"), ("put", "/engismart/users/1/domains")):
        assert getattr(client, method)(path, headers=H("dev")).status_code in (404, 405), path


# ---------------------------------------------------------------- uploads
def test_unsupported_extension(client):
    r = upload(client, "sue", "tool.exe", b"MZ....")
    assert r.status_code == 415 and r.json()["status"] is False


def test_empty_file(client):
    assert upload(client, "sue", "a.xlsx", b"").status_code == 422


def test_content_must_match_extension(client):
    assert upload(client, "sue", "fake.xlsx", b"just some text, not a zip").status_code == 422
    assert upload(client, "sue", "fake.pdf", b"not a pdf at all").status_code == 422
    assert upload(client, "sue", "bin.csv", b"a,b\x00\x01\n").status_code == 422
    assert upload(client, "sue", "fake.docx", b"%PDF-1.4 hi").status_code == 422


def test_normal_user_cannot_upload(client):
    assert upload(client, "anil", "a.xlsx", xlsx_bytes([["a"]])).status_code == 403


def test_upload_needs_a_file(client):
    r = client.post("/engismart/documents/check", headers=H("sue"), data={"domain": "adas"})
    assert r.status_code == 422 and r.json()["status"] is False


def test_virus_scanner_unreachable_refuses(client, monkeypatch):
    from controller.engismart import file_upload
    monkeypatch.setattr(file_upload.get_settings(), "virus_scan", "on")
    monkeypatch.setattr(file_upload, "scan_file_content_for_virus", lambda b: (_ for _ in ()).throw(RuntimeError("Virus scan failed: down")))
    r = upload(client, "sue", "ok.xlsx", xlsx_bytes([["a"]]))
    assert r.status_code == 503 and "scanned" in r.json()["message"]


def test_virus_found_is_rejected_and_logged(client, monkeypatch):
    from controller.engismart import file_upload
    monkeypatch.setattr(file_upload.get_settings(), "virus_scan", "on")
    monkeypatch.setattr(file_upload, "scan_file_content_for_virus", lambda b: False)
    r = upload(client, "sue", "bad.xlsx", xlsx_bytes([["a"]]))
    assert r.status_code == 422 and "Security threat" in r.json()["message"]
    from models.model import models
    from models.orm_models import ChromosomeUserLog
    with models() as db:
        logs = db.select_records(ChromosomeUserLog)
    assert any("Virus detected in bad.xlsx" in (l.activity_logs or "") for l in logs)


EDS_ROWS = [["Part", "Material", "Note"], ["Bonnet", "Carbon fiber", "frunk hinge torque 12 Nm"], ["Grille", "ABS", "heating element radome"]]
EDS_BYTES = xlsx_bytes(EDS_ROWS)  # built once: openpyxl stamps the creation second into the file, so two builds can differ
ADAS_ROWS = [["Sensor", "Position", "Note"], ["USS Front S1", "front bumper", "ultrasonic parking sensor field of view 120 degrees"]]


@pytest.fixture(scope="module")
def library(client):
    out = {}
    for name, data, domain in (("eds_guide.xlsx", EDS_BYTES, "eds"), ("adas_sensors.xlsx", xlsx_bytes(ADAS_ROWS), "adas")):
        c = upload(client, "sue", name, data, domain)
        assert c.status_code == 200, c.text
        d = c.json()["data"]
        r = commit(client, "sue", d["check_id"], domain)
        assert r.status_code == 200 and r.json()["data"]["results"][0]["status"] == "indexed", r.text
        out[name] = domain
    return out


def test_commit_records_file_and_audit_row(client, library):
    from models.model import models
    from models.orm_models import ChromosomeUserLog, File
    with models() as db:
        files = db.select_records(File, {"module": "engismart"})
        logs = db.select_records(ChromosomeUserLog)
    assert {f.original_filename for f in files} >= {"eds_guide.xlsx", "adas_sensors.xlsx"}
    assert all(f.file_type == "file" and f.file_type_display_name == "Document" for f in files)
    assert any("Successfully uploaded a .xlsx file: eds_guide.xlsx" in (l.activity_logs or "") for l in logs)


def test_document_library_and_domain(client, library):
    docs = client.get("/engismart/documents", headers=H("sue")).json()["data"]
    assert {d["file_name"]: d["domain"] for d in docs} == {"eds_guide.xlsx": "eds", "adas_sensors.xlsx": "adas"}


def test_second_upload_of_same_file_is_a_duplicate(client, library):
    d = upload(client, "sue", "copy.xlsx", EDS_BYTES, "eds").json()["data"]
    r = commit(client, "sue", d["check_id"], "eds")
    assert r.status_code == 409 and "already in the library" in r.json()["message"]


def test_multi_upload_endpoint_reports_each_file(client):
    r = client.post("/engismart/documents", headers=H("sue"),
                    files=[("files", ("bad.exe", b"MZ", "application/octet-stream")),
                           ("files", ("mats.xlsx", xlsx_bytes([["Material", "Grade"], ["Aluminium", "6061"]]), "application/octet-stream"))],
                    data={"domain": "materials-net"})
    assert r.status_code == 200, r.text
    res = r.json()["data"]["results"]
    assert res[0]["status"] == "failed" and res[1]["status"] == "indexed"


# ---------------------------------------------------------------- chat + access limits
def ask(client, who, text, session="s1"):
    r = client.post("/engismart/chat", headers=H(who), json={"session_id": session, "message": text})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_chat_finds_answer_in_own_domain(client, library):
    d = ask(client, "anil", "ultrasonic parking sensor field of view")
    assert d["sources"] and all(s["file_name"] == "adas_sensors.xlsx" for s in d["sources"]), d
    assert "plan" not in d and "usage" not in d  # developer only


def test_chat_cannot_reach_other_domain(client, library):
    d = ask(client, "anil", "frunk hinge torque carbon fiber bonnet", session="s2")
    assert not any(s["file_name"] == "eds_guide.xlsx" for s in d["sources"]), d


def test_priya_has_both_domains(client, library):
    d = ask(client, "priya", "frunk hinge torque carbon fiber bonnet", session="s3")
    assert any(s["file_name"] == "eds_guide.xlsx" for s in d["sources"]), d


def test_confidential_document_is_hidden_from_users(client, library):
    docs = {d["file_name"]: d["doc_id"] for d in client.get("/engismart/documents", headers=H("sue")).json()["data"]}
    r = client.patch(f"/engismart/documents/{docs['adas_sensors.xlsx']}/access", headers=H("sue"), json={"confidential": True})
    assert r.status_code == 200, r.text
    assert not ask(client, "anil", "ultrasonic parking sensor field of view", session="s4")["sources"]
    assert ask(client, "sue", "ultrasonic parking sensor field of view", session="s5")["sources"]
    client.patch(f"/engismart/documents/{docs['adas_sensors.xlsx']}/access", headers=H("sue"), json={"confidential": False})


def test_developer_sees_plan_and_usage(client, library):
    d = ask(client, "dev", "ultrasonic parking sensor field of view", session="s6")
    assert "usage" in d and "plan" in d


def test_usage_rows_go_to_the_platform_table(client, library):
    from models.model import models
    from models.orm_models import LangfuseUsageLogs, User
    ask(client, "anil", "ultrasonic parking sensor field of view", session="usage-1")
    with models() as db:
        rows = db.select_records(LangfuseUsageLogs, {"trace_id": "usage-1"})
        uid = db.select_records(User, {"username": "anil"})[0].id
    assert rows and rows[0].user_id == uid and rows[0].application_name == "engismart" and rows[0].latency is not None
    assert rows[0].model_name == "offline"


def test_bad_bodies_use_the_envelope(client):
    r = client.post("/engismart/chat", headers=H("anil"), content=b"{not json", )
    assert r.status_code == 422 and r.json()["status"] is False
    r = client.post("/engismart/chat", headers=H("anil"), json={"message": "hi"})
    assert r.status_code == 422 and "session_id" in r.json()["message"]


def test_chat_history_rewind_delete(client, library):
    ask(client, "anil", "ultrasonic parking sensor field of view", session="h1")
    ask(client, "anil", "and the position of the sensor", session="h1")
    msgs = client.get("/engismart/chat/h1/messages", headers=H("anil")).json()["data"]
    assert len(msgs) >= 4
    kept = client.post("/engismart/chat/h1/rewind", headers=H("anil"), json={"turns": 1}).json()["data"]["kept_messages"]
    assert kept == 2
    # another user cannot read it
    assert client.get("/engismart/chat/h1/messages", headers=H("priya")).json()["data"] == []
    assert client.delete("/engismart/chat/h1", headers=H("anil")).json()["data"] == {"deleted": "h1"}
    assert client.get("/engismart/chat/h1/messages", headers=H("anil")).json()["data"] == []


def test_chat_stream(client, library):
    with client.stream("POST", "/engismart/chat/stream", headers=H("anil"), json={"session_id": "st1", "message": "ultrasonic parking sensor field of view"}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert events[-1]["type"] == "final" and events[-1]["sources"]


def test_stream_needs_login(client):
    r = client.post("/engismart/chat/stream", json={"session_id": "x", "message": "hi"})
    assert r.status_code == 401


def test_picture_file_endpoint_needs_login_and_hides_unknown(client):
    assert client.get("/engismart/images/nope/file").status_code == 401
    r = client.get("/engismart/images/nope/file", headers=H("anil"))
    assert r.status_code == 404 and r.json()["status"] is False


def test_pictures_summary_and_catalog_table(client, library):
    r = client.get("/engismart/images/summary", headers=H("sue"))
    assert r.status_code == 200 and "counts" in r.json()["data"]


def test_delete_document(client, library):
    d = upload(client, "sue", "tmp.xlsx", xlsx_bytes([["Zebra", "Quagga"], ["stripe", "unique-word-xyz"]]), "eds").json()["data"]
    assert commit(client, "sue", d["check_id"], "eds").status_code == 200
    doc_id = next(x["doc_id"] for x in client.get("/engismart/documents", headers=H("sue")).json()["data"] if x["file_name"] == "tmp.xlsx")
    assert client.delete(f"/engismart/documents/{doc_id}", headers=H("sue")).json()["data"] == {"deleted": doc_id}
    assert client.delete(f"/engismart/documents/{doc_id}", headers=H("sue")).status_code == 404


def test_error_returns_platform_500_envelope_and_audit(client, monkeypatch):
    from controller.engismart import admin

    def boom():
        raise RuntimeError("store exploded")
    monkeypatch.setattr(admin, "get_store", boom)
    r = client.get("/engismart/domains", headers=H("sue"))
    assert r.status_code == 500 and r.json()["message"] == "Something went wrong!" and "store exploded" in r.json()["error"]
    from models.model import models
    from models.orm_models import ChromosomeUserLog
    with models() as db:
        logs = db.select_records(ChromosomeUserLog)
    assert any("Exception in /domains" in (l.activity_logs or "") for l in logs)


def test_ingest_folder_is_for_developers_only(client, tmp_path):
    empty = str(tmp_path)  # an empty folder: even a wrongly allowed call could not ingest anything
    assert client.post("/engismart/documents/ingest-folder", headers=H("sue"), json={"path": empty}).status_code == 403
    assert client.post("/engismart/documents/ingest-folder", headers=H("dev"), json={"path": empty}).json()["data"]["results"] == []
    r = client.post("/engismart/documents/ingest-folder", headers=H("dev"), json={"path": "/definitely/not/here"})
    assert r.status_code == 404 and r.json()["status"] is False
