"""LangGraph RAG chat pipeline.

    plan ──(chitchat)──────────────────────────────► smalltalk ──► END
      │
      ▼
    prepare ══► search ×N (parallel branches: one per phrasing / sub-question / id) ══► merge
                                                                                          │
                              rewrite ◄──(weak & first try)── check ◄─────────────────────┘
                                 │                               │
                                 └──► prepare                    ▼ (good, or already retried)
                                                              generate ──► END

prepare embeds the phrasings once and lists the searches; every search is its own LangGraph branch (the Send API), so they run
side by side; merge joins the hits, reranks, judges and builds the evidence.

State is checkpointed per session (thread_id) in the platform's database (MySQL, or PostgreSQL; a SQLite file only when the
platform itself runs on SQLite), so follow-up questions work across restarts.
Custom stream events (via get_stream_writer): {"type": "status" | "token" | "reset", ...}
"""
from __future__ import annotations

import logging
import operator
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from controller.engismart.chat import searchjob, vision
from controller.engismart.chat.answer import NOT_FOUND, answer, cited_sources
from controller.engismart.chat.planner import plan_llm
from controller.engismart.chat.retriever import assemble, prepare, run_search
from controller.engismart.core.config import get_settings
from controller.engismart.core.llm import add_usage, describe_llm_error, get_chat_model
from controller.engismart.core.vocab import content_tokens

log = logging.getLogger(__name__)


class ChatState(TypedDict, total=False):
    messages: Annotated[list[dict], operator.add]  # persisted conversation [{role, content}]
    question: str
    filters: dict[str, Any] | None
    plan: dict
    last_plan: dict  # plan of the previous turn (for follow-ups)
    evidence: list[dict]
    retried: bool
    search_ref: str | None  # in-memory reference of the searches of this question (rag.searchjob)
    answer: str
    sources: list[dict]
    mode: str
    notices: list[str]  # reset every turn (no reducer)
    timings: dict[str, int]  # ms per step, reset every turn
    usage: dict[str, int]  # LLM tokens / calls this turn (input_tokens, output_tokens, llm_calls), reset every turn
    image_ref: str | None  # attached images (held in memory by rag.vision, never checkpointed), reset every turn
    image_context: str  # vision-model description of the attached images, reset every turn


def _usage(state: ChatState) -> dict:
    return dict(state.get("usage") or {})


def _timed(name: str, fn):
    """Wrap a node so its duration is added to state['timings'][name] (ms)."""

    def node(state: ChatState) -> ChatState:
        t0 = time.perf_counter()
        out = fn(state)
        timings = dict(out.get("timings") or state.get("timings") or {})
        timings[name] = timings.get(name, 0) + round((time.perf_counter() - t0) * 1000)
        return {**out, "timings": timings}

    return node


def _emit(event: dict) -> None:
    try:
        get_stream_writer()(event)
    except Exception:  # noqa: BLE001 - not running in stream mode
        pass


def _history(state: ChatState) -> list[dict]:
    return [m for m in state.get("messages", []) if m["role"] in ("user", "assistant")]


# ------------------------------------------------------------------ nodes
def plan_node(state: ChatState) -> ChatState:
    _emit({"type": "status", "step": "plan", "message": "Understanding the question"})
    usage = _usage(state)
    notices = list(state.get("notices") or [])
    question = state["question"]
    images = vision.get(state.get("image_ref"))
    image_context = ""
    if images:  # read the image(s) first, so their content drives the search
        _emit({"type": "status", "step": "plan", "message": "Reading the attached image"})
        image_context, notice = vision.describe(images, question, usage)
        if notice:
            notices.append(notice)
    to_plan = f"{question}\n\n[Attached image shows: {image_context}]" if image_context else question
    plan, notice = plan_llm(to_plan, _history(state), state.get("last_plan"), usage)
    if notice:
        notices.append(notice)
    plan_d = plan.model_dump()
    if images and plan_d["intent"] == "chitchat":  # "hi" + a photo is still a question about the photo
        plan_d["intent"] = "explanation"
        plan_d["search_queries"] = plan_d["sub_questions"] = [plan_d["standalone_question"]]
    # the conversation keeps a text note of the image (not the image) so follow-ups understand it
    shown = question + (f"\n\n[Attached image: {image_context[:600]}]" if image_context else ("\n\n[Attached image]" if images else ""))
    return {"plan": plan_d, "messages": [{"role": "user", "content": shown}], "usage": usage,
            "image_context": image_context, "notices": notices}


def prepare_node(state: ChatState) -> ChatState:
    _emit({"type": "status", "step": "retrieve", "message": "Searching documents"})
    plan = state["plan"]
    timings = dict(state.get("timings") or {})
    detail: dict = {}
    prepared = prepare(plan["standalone_question"], plan, state.get("filters"), detail)
    for k, v in detail.items():
        timings[f"retrieve.{k}"] = timings.get(f"retrieve.{k}", 0) + v
    ref = searchjob.start(plan["standalone_question"], plan, state.get("filters"), prepared["specs"], prepared["named_sheets"])
    return {"search_ref": ref, "timings": timings}


def fan_out(state: ChatState) -> list[Send]:
    """One LangGraph branch per search: they run at the same time."""
    ref = state["search_ref"]
    n = searchjob.count(ref)
    if not get_settings().parallel_search:
        return [Send("search", {"ref": ref, "indexes": list(range(n))})]  # one branch runs them one after another
    return [Send("search", {"ref": ref, "indexes": [i]}) for i in range(n)]


def search_node(payload: dict) -> dict:
    """One branch: run its search(es) and park the hits in memory (the graph state stays small)."""
    for i in payload["indexes"]:
        t0 = time.perf_counter()
        hits = run_search(searchjob.spec(payload["ref"], i))
        searchjob.add(payload["ref"], i, hits, round((time.perf_counter() - t0) * 1000))
    return {}


def merge_node(state: ChatState) -> ChatState:
    """All searches are done: merge the hits, rerank, judge and expand them into evidence."""
    job = searchjob.finish(state["search_ref"])
    usage = _usage(state)
    timings = dict(state.get("timings") or {})
    if job is None:  # entry expired: nothing to merge
        return {"evidence": [], "timings": timings, "usage": usage, "search_ref": None}
    batches = [job["hits"].get(i, []) for i in range(len(job["specs"]))]
    detail: dict = {"search_wall": round((time.time() - job["t0"]) * 1000), "search_busiest": max(job["ms"].values(), default=0)}
    evidence = assemble(job["question"], job["plan"], job["filters"], job["named_sheets"], batches, detail, usage)
    for k, v in detail.items():
        timings[f"retrieve.{k}"] = timings.get(f"retrieve.{k}", 0) + v
    return {"evidence": evidence, "timings": timings, "usage": usage, "search_ref": None}


def rewrite_node(state: ChatState) -> ChatState:
    """Weak evidence: try once more with different queries."""
    _emit({"type": "status", "step": "rewrite", "message": "Rephrasing the search"})
    plan = dict(state["plan"])
    q = plan["standalone_question"]
    queries = [" ".join(content_tokens(q))]
    usage = _usage(state)
    llm = get_chat_model(fast=True)
    if llm is not None:
        try:
            msg = llm.invoke([("system", "The first search found nothing relevant. Rewrite the question into 2 alternative short "
                                         "keyword search queries for an automotive engineering document search engine, using "
                                         "DIFFERENT vocabulary: synonyms, expanded abbreviations, part / standard names, and how a "
                                         "specification, FMEA or benchmarking table would phrase it. One per line, no numbering."),
                              ("user", q)])
            add_usage(usage, msg)
            queries = [ln.strip("-• ").strip() for ln in str(msg.content).splitlines() if ln.strip()][:2] or queries
        except Exception as e:  # noqa: BLE001
            log.warning("query rewrite failed: %s", describe_llm_error(e))
    plan["search_queries"] = queries
    return {"plan": plan, "retried": True, "usage": usage}


def _route_after_check(state: ChatState) -> str:
    """merge only returns evidence judged relevant; nothing returned -> rephrase once, then answer."""
    weak = not state.get("evidence")
    return "rewrite" if weak and not state.get("retried") else "generate"


def generate_node(state: ChatState) -> ChatState:
    _emit({"type": "status", "step": "generate", "message": "Writing the answer"})
    plan, evidence = state["plan"], state.get("evidence", [])
    usage = _usage(state)
    text, mode, notice = answer(plan["standalone_question"], plan, _history(state)[:-1], evidence,
                                lambda ev: _emit(ev), usage, vision.get(state.get("image_ref")),
                                state.get("image_context") or "")
    if not text.strip():
        text = NOT_FOUND
    out: ChatState = {"answer": text, "mode": mode, "sources": cited_sources(text, evidence), "last_plan": plan,
                      "messages": [{"role": "assistant", "content": text}], "usage": usage}
    if notice:
        out["notices"] = state.get("notices", []) + [notice]
    return out


def smalltalk_node(state: ChatState) -> ChatState:
    text = ("Hello! Ask me about the ingested documents — e.g. *compare CCB weight across vehicles*, "
            "*what causes decoupling ring failures*, or *frunk volume of the BMW i3*.")
    _emit({"type": "token", "text": text})
    return {"answer": text, "mode": "offline", "sources": [], "messages": [{"role": "assistant", "content": text}]}


# ------------------------------------------------------------------ graph
def build_chat_graph(checkpointer=None):
    g = StateGraph(ChatState)
    g.add_node("plan", _timed("plan", plan_node))
    g.add_node("prepare", _timed("retrieve", prepare_node))
    g.add_node("search", search_node)
    g.add_node("merge", _timed("retrieve", merge_node))
    g.add_node("rewrite", _timed("rewrite", rewrite_node))
    g.add_node("generate", _timed("generate", generate_node))
    g.add_node("smalltalk", smalltalk_node)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", lambda s: "smalltalk" if s["plan"]["intent"] == "chitchat" else "prepare",
                            ["smalltalk", "prepare"])
    g.add_conditional_edges("prepare", fan_out, ["search"])
    g.add_edge("search", "merge")
    g.add_conditional_edges("merge", _route_after_check, ["rewrite", "generate"])
    g.add_edge("rewrite", "prepare")
    g.add_edge("generate", END)
    g.add_edge("smalltalk", END)
    return g.compile(checkpointer=checkpointer)


_graph = None
_checkpointer: Any = None  # PyMySQLSaver | PostgresSaver | SqliteSaver
_pool: Any = None  # PostgreSQL connection pool of the checkpointer
_conn: Any = None  # the MySQL connection of the checkpointer
_graph_lock = threading.Lock()


def _postgres_checkpointer():
    """LangGraph's PostgresSaver on its own small pool. It creates and owns its checkpoint tables."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    global _pool
    conninfo = re.sub(r"^postgres(?:ql)?(?:\+\w+)?://", "postgresql://", get_settings().db_url)
    _pool = ConnectionPool(conninfo=conninfo, min_size=1, max_size=5, open=True,
                           kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row,
                                   "options": "-c timezone=UTC"})
    saver = PostgresSaver(_pool)
    saver.setup()
    return saver


def _mysql_checkpointer():
    """langgraph-checkpoint-mysql's PyMySQLSaver (MySQL >= 8.0.19) on the platform's database. It creates and owns its tables
    (checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations). One connection, used one call at a time (the saver's
    own lock); a dropped connection is re-opened before the next call."""
    import pymysql
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
    from sqlalchemy.engine import make_url

    global _conn
    url = make_url(get_settings().db_url)
    _conn = pymysql.connect(host=url.host or "localhost", port=url.port or 3306, user=url.username, password=url.password or "",
                            database=url.database, autocommit=True, charset="utf8mb4")

    class _ReconnectingSaver(PyMySQLSaver):
        @contextmanager
        def _cursor(self, *, pipeline: bool = False):
            with self.lock:
                self.conn.ping(reconnect=True)
            with super()._cursor(pipeline=pipeline) as cur:
                yield cur

    saver = _ReconnectingSaver(_conn)
    saver.setup()
    return saver


def get_chat_graph():
    global _graph, _checkpointer
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                s = get_settings()
                if s.db_backend == "mysql":
                    _checkpointer = _mysql_checkpointer()
                elif s.db_backend == "postgresql":
                    _checkpointer = _postgres_checkpointer()
                else:
                    path = Path(s.chat_memory_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    _checkpointer = SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))
                _graph = build_chat_graph(_checkpointer)
    return _graph


def close_chat_memory() -> None:
    global _graph, _checkpointer, _pool, _conn
    if _pool is not None:
        _pool.close()
    if _conn is not None:
        _conn.close()
    _graph = _checkpointer = _pool = _conn = None


def turn_input(question: str, filters: dict | None, image_ref: str | None = None) -> ChatState:
    """Fields reset at the start of every turn (messages / last_plan persist via the checkpointer)."""
    return {"question": question, "filters": filters, "retried": False, "search_ref": None, "evidence": [], "notices": [],
            "answer": "", "sources": [], "timings": {}, "usage": {}, "image_ref": image_ref, "image_context": ""}


def config_for(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def run_chat(session_id: str, question: str, filters: dict | None = None, images: list[str] | None = None) -> dict:
    graph = get_chat_graph()
    ref = vision.hold(images or [])
    try:
        graph.invoke(turn_input(question, filters, ref), config_for(session_id))
    finally:
        vision.release(ref)  # images are used for this question only
    return result_of(session_id)


def result_of(session_id: str) -> dict:
    v = get_chat_graph().get_state(config_for(session_id)).values
    plan = v.get("plan") or {}
    return {"session_id": session_id, "answer": v.get("answer", ""), "sources": v.get("sources", []),
            "mode": v.get("mode"), "intent": plan.get("intent"), "plan": plan, "notices": v.get("notices", []),
            "timings": v.get("timings", {}), "usage": v.get("usage", {})}


def history_of(session_id: str) -> list[dict]:
    return get_chat_graph().get_state(config_for(session_id)).values.get("messages", [])


def rewind_session(session_id: str, turns: int) -> int:
    """Edit and send: forget every question after the first `turns` finished ones (each turn = a question and its answer), so the
    edited question is answered with the memory it would have had. Returns the number of messages kept.

    The conversation is forked from the checkpoint taken right after turn `turns` (LangGraph time travel): the later turns stay in the
    database history but are no longer part of the conversation."""
    graph = get_chat_graph()
    keep = max(0, turns) * 2
    cfg = config_for(session_id)
    msgs = graph.get_state(cfg).values.get("messages", [])
    if len(msgs) <= keep and (not msgs or msgs[-1]["role"] == "assistant"):
        return len(msgs)  # nothing after that point
    if keep == 0:
        delete_session(session_id)
        return 0
    for snap in graph.get_state_history(cfg):  # newest first
        m = snap.values.get("messages", [])
        if not snap.next and len(m) == keep and m[-1]["role"] == "assistant":
            graph.update_state(snap.config, {"retried": False}, as_node="generate")  # a new checkpoint on top: the fork
            return keep
    delete_session(session_id)  # that point is no longer in the history: start clean rather than answer with the wrong memory
    return 0


def delete_session(session_id: str) -> None:
    get_chat_graph()
    _checkpointer.delete_thread(session_id)
