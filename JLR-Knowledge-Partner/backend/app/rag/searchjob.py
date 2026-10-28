"""Searches of one question that run side by side (LangGraph fan-out).

The graph state stays small: it only carries a reference. The search specs and the hits live here, in memory, for the
few seconds one question takes, and are released by the merge step (stale entries are dropped after 10 minutes)."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
TTL_S = 600


def start(question: str, plan: dict, filters: dict | None, specs: list[dict], named_sheets: list[str]) -> str:
    ref = uuid.uuid4().hex
    now = time.time()
    with _lock:
        for k in [k for k, v in _jobs.items() if now - v["t0"] > TTL_S]:
            del _jobs[k]
        _jobs[ref] = {"t0": now, "question": question, "plan": plan, "filters": filters, "specs": specs,
                      "named_sheets": named_sheets, "hits": {}, "ms": {}}
    return ref


def spec(ref: str, i: int) -> dict:
    with _lock:
        return _jobs[ref]["specs"][i]


def count(ref: str) -> int:
    with _lock:
        return len(_jobs[ref]["specs"])


def add(ref: str, i: int, hits: list[dict], ms: int) -> None:
    with _lock:
        job = _jobs.get(ref)
        if job is not None:
            job["hits"][i] = hits
            job["ms"][i] = ms


def finish(ref: str) -> dict[str, Any] | None:
    """Everything the merge step needs; the entry is removed."""
    with _lock:
        return _jobs.pop(ref, None)
