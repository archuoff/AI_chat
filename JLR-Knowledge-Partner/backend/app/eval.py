"""Retrieval + answer evaluation against eval/questions.json.

    python -m app.eval [--show-misses]

expect = {"file", "sheet", "row", "page", "slide", "text"} (all given keys must match one evidence unit)
expect = null -> the question is NOT answerable from the documents; the chat must say so.
answer = ["fact", ["alt1", "alt2"], ...] -> every fact (or one of the alternatives) must appear in the answer.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import time
import uuid
from pathlib import Path

from .graphs.chat_graph import config_for, delete_session, get_chat_graph, run_chat
from .llm import get_chat_model

QUESTIONS = Path(__file__).resolve().parent.parent / "eval" / "questions.json"
_NOT_FOUND = re.compile(r"couldn.t find|not (found|contain|available)|no (relevant )?information", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("‑", "-").replace("–", "-").replace("—", "-")).lower()


def _matches(e: dict, exp: dict) -> bool:
    loc = e.get("location") or {}
    if "file" in exp and exp["file"].lower() not in e["file_name"].lower():
        return False
    for k in ("sheet", "row", "page", "slide"):
        if k in exp and loc.get(k) != exp[k]:
            return False
    if "text" in exp and exp["text"].lower() not in e["text"].lower():
        return False
    return True


def _answer_ok(answer: str, facts: list) -> bool:
    a = _norm(answer)
    return all(any(_norm(alt) in a for alt in (f if isinstance(f, list) else [f])) for f in facts)


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p * (len(values) - 1))))]


def main() -> int:
    logging.basicConfig(level=logging.ERROR)
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-misses", action="store_true")
    a = ap.parse_args()
    items = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    hits = {1: 0, 3: 0, 8: 0}
    answerable = negatives_ok = negatives = answer_checks = answers_ok = 0
    misses: list[tuple] = []
    totals: list[float] = []
    steps: dict[str, list[int]] = {}
    for it in items:
        t = time.perf_counter()
        sid = f"eval-{uuid.uuid4()}"
        r = run_chat(sid, it["q"])
        totals.append(time.perf_counter() - t)
        for k, v in (r.get("timings") or {}).items():
            steps.setdefault(k, []).append(v)
        evidence = get_chat_graph().get_state(config_for(sid)).values.get("evidence", [])
        delete_session(sid)
        if it["expect"] is None:
            negatives += 1
            ok = bool(_NOT_FOUND.search(r["answer"]))
            negatives_ok += ok
            if not ok:
                misses.append((it["q"], "should be NOT FOUND", r["answer"][:200]))
            continue
        answerable += 1
        rank = next((e["n"] for e in evidence if _matches(e, it["expect"])), None)
        for k in hits:
            hits[k] += rank is not None and rank <= k
        if rank is None or rank > 3:
            misses.append((it["q"], f"retrieval rank={rank}", [e["context"] for e in evidence[:3]]))
        if "answer" in it:
            answer_checks += 1
            ok = _answer_ok(r["answer"], it["answer"])
            answers_ok += ok
            if not ok:
                misses.append((it["q"], f"answer missing {it['answer']}", r["answer"][:300]))

    mode = "azure-openai" if get_chat_model() is not None else "offline"
    print(f"mode                 : {mode}")
    print(f"answerable questions : {answerable}")
    for k, v in hits.items():
        print(f"  source hit@{k:<2}       : {v}/{answerable} = {v / answerable:.0%}")
    print(f"answer contains fact : {answers_ok}/{answer_checks} = {answers_ok / max(answer_checks, 1):.0%}")
    print(f"not-found questions  : {negatives_ok}/{negatives} correctly refused")
    print(f"latency total        : p50 {statistics.median(totals):.1f}s · p95 {_pct(totals, 0.95):.1f}s")
    for k in sorted(steps):
        if k == "retrieve.candidates":
            continue
        print(f"  {k:<19}: p50 {statistics.median(steps[k]):>6.0f} ms · p95 {_pct(steps[k], 0.95):>6.0f} ms")
    if a.show_misses:
        for q, why, detail in misses:
            print(f"\nMISS [{why}] {q}\n   got: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
