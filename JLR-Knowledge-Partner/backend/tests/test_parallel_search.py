"""The searches of one question run side by side (LangGraph fan-out); every part of a multi-part question keeps its places."""
import threading
import time

from app.rag import retriever


def hit(i, doc="d", **extra):
    return {"id": f"{doc}{i}", "doc_id": doc, "kind": "record", "chunk_index": i, "text": f"row {i}", "context": "", "score": 0.5, "location": {"row": i}, **extra}


# ------------------------------------------------------------------ what is searched
def test_search_specs_cover_every_phrasing_sub_question_id_and_named_sheet():
    plan = {"standalone_question": "compare weight and torque", "search_queries": ["weight", "torque"], "sub_questions": ["weight", "torque"],
            "sheets": ["CCB"], "ids": ["SSA-12"], "intent": "comparison"}
    specs = retriever.search_specs(plan, {"domain": ["adas"]}, ["CCB"])
    kinds = [s["kind"] for s in specs]
    assert kinds.count("query") == 4  # two phrasings, each also restricted to the named sheet
    assert kinds.count("sub") == 2 and {s["sub"] for s in specs if s["kind"] == "sub"} == {0, 1}
    assert kinds.count("id") == 1 and kinds.count("structured") == 1
    assert all(s["filters"]["domain"] == ["adas"] for s in specs)


def test_a_single_question_has_no_sub_searches():
    specs = retriever.search_specs({"standalone_question": "q", "search_queries": ["q"], "sub_questions": ["q"], "intent": "lookup"}, None, [])
    assert [s["kind"] for s in specs] == ["query"]


def test_merge_keeps_the_flags_and_parts_of_every_search_that_found_a_chunk():
    a = hit(1, subs=[0])
    b = hit(1, subs=[1], exact=True)
    merged = retriever.merge_hits([[a], [b, hit(2)]])
    assert set(merged) == {"d1", "d2"} and merged["d1"]["subs"] == [0, 1] and merged["d1"]["exact"] is True


# ------------------------------------------------------------------ side by side
class SlowStore:
    """Every search takes 0.2 s and notes how many ran at the same moment."""

    def __init__(self):
        self.now = self.peak = 0
        self.lock = threading.Lock()

    def search(self, query, top_k=8, filters=None, mode="hybrid"):
        with self.lock:
            self.now += 1
            self.peak = max(self.peak, self.now)
        time.sleep(0.2)
        with self.lock:
            self.now -= 1
        return [hit(len(query))]


def test_searches_run_in_parallel_not_one_after_another(monkeypatch):
    store = SlowStore()
    monkeypatch.setattr(retriever, "get_store", lambda: store)
    specs = [{"kind": "query", "q": "x" * n, "limit": 5, "filters": None} for n in range(1, 7)]
    t0 = time.perf_counter()
    batches = retriever.run_specs(specs)
    took = time.perf_counter() - t0
    assert len(batches) == 6 and store.peak >= 3 and took < 0.8  # six searches of 0.2 s: ~1.2 s one by one


def test_parallel_search_can_be_switched_off(monkeypatch):
    from app import config
    monkeypatch.setenv("PARALLEL_SEARCH", "false")
    config.get_settings.cache_clear()
    store = SlowStore()
    monkeypatch.setattr(retriever, "get_store", lambda: store)
    retriever.run_specs([{"kind": "query", "q": "x" * n, "limit": 5, "filters": None} for n in range(1, 4)])
    assert store.peak == 1
    config.get_settings.cache_clear()


# ------------------------------------------------------------------ every part keeps its places
def unit(i, subs, grade=2):
    return {"chunks": [{"id": f"u{i}", "doc_id": "d", "kind": "record", "chunk_index": i, "subs": subs}], "score": 1 - i / 100, "sim": 0.5, "grade": grade}


def test_every_sub_question_keeps_at_least_its_minimum_places():
    pool = [unit(i, [0]) for i in range(10)] + [unit(10, [1]), unit(11, [1]), unit(12, [1])]  # the second part ranks lower
    selected = pool[:8]  # the top 8 are all about the first part
    out = retriever._reserve_per_sub(selected, pool, 2, 8, 2, lambda u: bool(u["grade"]))
    ids = [u["chunks"][0]["id"] for u in out]
    assert len(out) == 8 and {"u10", "u11"} <= set(ids)  # two places for part two, the room comes from part one's tail
    assert ids == sorted(ids, key=lambda x: int(x[1:]))  # rank order is kept


def test_places_are_not_given_to_evidence_that_failed_the_relevance_check():
    pool = [unit(i, [0]) for i in range(6)] + [unit(6, [1], grade=0)]
    out = retriever._reserve_per_sub(pool[:4], pool, 2, 4, 2, lambda u: bool(u["grade"]))
    assert all(u["chunks"][0]["id"] != "u6" for u in out)


def test_single_part_questions_are_untouched():
    pool = [unit(i, []) for i in range(5)]
    assert retriever._reserve_per_sub(pool[:3], pool, 0, 3, 2, lambda u: True) == pool[:3]


# ------------------------------------------------------------------ inside the chat graph
def test_the_chat_graph_fans_out_one_branch_per_search(api, monkeypatch):
    from app.graphs import chat_graph
    from app.rag import searchjob

    seen = []
    real = retriever.run_search

    def spy(spec):
        seen.append((spec["kind"], spec["q"] if "q" in spec else None, threading.current_thread().name))
        time.sleep(0.15)
        return real(spec)

    monkeypatch.setattr(chat_graph, "run_search", spy)
    from fastapi.testclient import TestClient  # noqa: F401 - the api fixture already built the app and the store
    r = api.post("/api/documents/check", files={"file": ("a.xlsx", _xlsx())}, data={"domain": "adas"}).json()
    api.post("/api/documents/commit", json={"check_id": r["check_id"], "domain": "adas", "intent": "new"})
    from app.rag.planner import QueryPlan
    plan = QueryPlan(standalone_question="weight of Audi", intent="lookup", search_queries=["weight audi", "audi mass", "Audi SQ6 kerb"],
                     sub_questions=["weight", "range"], ids=[], sheets=[], entities=[])
    monkeypatch.setattr(chat_graph, "plan_llm", lambda *a, **k: (plan, None))
    from conftest import FakeEmbedder  # the offline answer ranks headers with an embedder: no model download in tests
    from app.rag import answer as answer_mod
    monkeypatch.setattr(answer_mod, "get_embedder", lambda: FakeEmbedder())
    t0 = time.perf_counter()
    res = chat_graph.run_chat("par1", "weight of Audi")
    took = time.perf_counter() - t0
    assert len(seen) == 5 and res["answer"]  # 3 phrasings + 2 sub-questions, one graph branch each
    assert len({s[2] for s in seen}) > 1  # not all on the same thread
    assert took < 5 * 0.15 + 2.0  # not five searches one after another plus overhead
    assert searchjob._jobs == {}  # the in-memory entry was released


def _xlsx():
    import io

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Vehicle", "Weight"])
    for v, w in [("Audi SQ6", "2.3 kg"), ("BMW X5", "2.9 kg")]:
        ws.append([v, w])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_the_streaming_endpoint_works_through_the_fan_out(api, monkeypatch):
    from conftest import FakeEmbedder

    from app.rag import answer as answer_mod
    monkeypatch.setattr(answer_mod, "get_embedder", lambda: FakeEmbedder())
    r = api.post("/api/documents/check", files={"file": ("a.xlsx", _xlsx())}, data={"domain": "adas"}).json()
    api.post("/api/documents/commit", json={"check_id": r["check_id"], "domain": "adas", "intent": "new"})
    res = api.post("/api/chat/stream", json={"session_id": "par2", "message": "weight of Audi SQ6"})
    assert res.status_code == 200 and '"type": "final"' in res.text and "Audi SQ6" in res.text
    assert '"step": "retrieve"' in res.text  # the status step still shows up once
