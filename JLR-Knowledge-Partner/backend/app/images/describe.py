"""Describe waiting pictures with the vision deployment (background job), then index the descriptions.

Nothing here runs until AZURE_OPENAI_VISION_DEPLOYMENT is set: company documents are described with
the company Azure resource only. Before a run the UI shows the picture count and a token / cost estimate.
"""
from __future__ import annotations

import base64
import logging
import math
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import get_settings
from ..llm import add_usage, describe_llm_error, get_vision_model
from . import catalog

log = logging.getLogger(__name__)

PROMPT = """You describe pictures from automotive engineering documents (JLR / Tata Technologies) so engineers can
find them with a text search. The picture comes from: {where}
Context around it in the document (it only says WHERE the picture sits: a hint, never a source of facts about what it shows):
{context}

Answer with these labelled lines (leave out a line that does not apply):
Kind: photo / CAD / section view / diagram / chart / table / drawing
Summary: 2-4 short factual lines: what it shows (part, assembly, view, test setup ...)
Visible text: every readable label, part number, code, callout and note, transcribed exactly
Values: dimensions, tolerances, units and materials that are visible
Findings: defects, failure signs or highlighted areas, if any
Context match: yes / no / unsure (does the picture fit the context above?)
Do not guess what is not visible. If the picture is only a logo, icon, decoration or empty frame, answer exactly: DECORATIVE"""

# Pictures inside Excel sheets: mostly photos of vehicles / parts, the row data is already searchable -> short, low detail
PROMPT_BRIEF = """You describe a picture from an automotive engineering workbook (JLR / Tata Technologies) so engineers can
find it with a text search. It sits at: {where}
Context from the sheet (it only says WHERE the picture sits: a hint, never a source of facts about what it shows):
{context}

Answer with at most these three lines:
Summary: what is visible, in one or two short sentences (vehicle / part / assembly / view)
Visible text: any readable label or number, verbatim (or "none")
Context match: yes / no / unsure
Do not repeat the row data and do not guess. If it is only a logo, icon, decoration or empty frame, answer exactly: DECORATIVE"""

PROMPT_TOKENS = 330  # instructions + typical context (full)
BRIEF_PROMPT_TOKENS = 240
OUTPUT_TOKENS = 220
BRIEF_OUTPUT_TOKENS = 70

_lock = threading.Lock()
_job: dict[str, Any] = {"state": "idle"}


def _image_tokens(w: int, h: int, detail: str) -> int:
    """OpenAI vision token formula (GPT-4o / 4.1 class): 85 base + 170 per 512 px tile after scaling."""
    if detail == "low" or not w or not h:
        return 85
    scale = min(1.0, 2048 / max(w, h))
    w, h = w * scale, h * scale
    scale = min(1.0, 768 / min(w, h))
    w, h = w * scale, h * scale
    return 85 + 170 * math.ceil(w / 512) * math.ceil(h / 512)


def _mode(img: catalog.DocImage) -> str:
    """brief for pictures inside Excel sheets (unless switched off), full for everything else."""
    in_sheet = "sheet" in (img.location or {})
    return "brief" if in_sheet and get_settings().vision_excel_mode == "brief" else "full"


def _detail(mode: str) -> str:
    s = get_settings()
    return s.vision_detail_brief if mode == "brief" else s.vision_detail


def estimate(images: list[catalog.DocImage]) -> dict[str, Any]:
    s = get_settings()
    tin = tout = brief = 0
    for i in images:
        mode = _mode(i)
        w = min(i.width, catalog.FULL_PX) if i.width >= i.height else round(i.width * catalog.FULL_PX / max(i.height, 1))
        h = min(i.height, catalog.FULL_PX) if i.height >= i.width else round(i.height * catalog.FULL_PX / max(i.width, 1))
        tin += _image_tokens(w, h, _detail(mode)) + (BRIEF_PROMPT_TOKENS if mode == "brief" else PROMPT_TOKENS)
        tout += BRIEF_OUTPUT_TOKENS if mode == "brief" else OUTPUT_TOKENS
        brief += mode == "brief"
    priced = s.vision_price_input_per_1m > 0 or s.vision_price_output_per_1m > 0
    cost = (tin * s.vision_price_input_per_1m + tout * s.vision_price_output_per_1m) / 1e6 if priced else None
    return {"images": len(images), "brief": brief, "input_tokens": tin, "output_tokens": tout,
            "cost": round(cost, 2) if cost is not None else None}


def config() -> dict[str, Any]:
    s = get_settings()
    return {"enabled": s.vision_enabled, "deployment": s.azure_openai_vision_deployment or None, "detail": s.vision_detail,
            "priced": s.vision_price_input_per_1m > 0 or s.vision_price_output_per_1m > 0}


def status() -> dict[str, Any]:
    with _lock:
        return dict(_job)


def cancel() -> None:
    with _lock:
        if _job.get("state") == "running":
            _job["cancel"] = True


_LABEL = re.compile(r"^\s*(?:[-*]\s*)?context match\s*:\s*(.*)$", re.IGNORECASE)


def parse_answer(text: str) -> tuple[str, bool, str]:
    """-> (description without the 'Context match' line, is it decorative, note when the context may not fit the picture)"""
    text = text.strip()
    if text.upper().rstrip(".") == "DECORATIVE":
        return "", True, ""
    lines, note = [], ""
    for line in text.splitlines():
        m = _LABEL.match(line)
        if m:
            verdict = m.group(1).strip().lower()
            if verdict.startswith(("no", "unsure")):
                note = "Context may not match the picture" if verdict.startswith("no") else "Context match unsure"
        elif line.strip():
            lines.append(line.rstrip())
    return "\n".join(lines), False, note


def _describe_one(llm, img: catalog.DocImage, file_name: str) -> tuple[str, dict]:
    s = get_settings()
    mode = _mode(img)
    where = f"{file_name}, {catalog._where(img.location) or 'document'}"
    data = base64.b64encode(catalog.file_path(img).read_bytes()).decode()
    usage: dict = {}
    if mode == "brief" and not s.vision_reasoning_model:
        # a copy with its own length limit: bind(max_tokens=...) would send max_tokens AND max_completion_tokens (Azure: 400)
        llm = llm.model_copy(update={"max_tokens": s.vision_brief_max_tokens})
    msg = llm.invoke([("user", [
        {"type": "text", "text": (PROMPT_BRIEF if mode == "brief" else PROMPT).format(where=where, context=img.context.strip()[:1000] or "(none)")},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}", "detail": _detail(mode)}},
    ])])
    add_usage(usage, msg)
    return str(msg.content).strip(), usage


def start_job(user_id: int, doc_ids: list[str] | None = None, image_ids: list[str] | None = None) -> dict[str, Any]:
    """Start describing the selected waiting pictures in the background. Raises if disabled or already running."""
    llm = get_vision_model()
    if llm is None:
        raise RuntimeError("No vision deployment configured (AZURE_OPENAI_VISION_DEPLOYMENT)")
    todo = catalog.waiting(doc_ids, image_ids)
    cap = get_settings().vision_max_images_per_run
    limited_from = len(todo) if cap and len(todo) > cap else 0
    if limited_from:
        todo = todo[:cap]  # a safety cap on cost: the rest stays waiting for the next run
    with _lock:
        if _job.get("state") == "running":
            raise RuntimeError("A describe run is already in progress")
        if not todo:
            raise ValueError("No pictures are waiting")
        _job.clear()
        _job.update(state="running", total=len(todo), done=0, described=0, decorative=0, failed=0, input_tokens=0,
                    output_tokens=0, started_at=time.time(), user_id=user_id, cancel=False, estimate=estimate(todo),
                    limited_from=limited_from)
    threading.Thread(target=_run, args=(llm, todo, user_id), daemon=True, name="describe-pictures").start()
    return status()


def _run(llm, todo: list[catalog.DocImage], user_id: int) -> None:
    from ..auth import usage as usage_log
    from ..store import get_store

    names = {d["doc_id"]: d["file_name"] for d in get_store().list_documents()}
    by_doc: dict[str, list[catalog.DocImage]] = defaultdict(list)
    for img in todo:
        by_doc[img.doc_id].append(img)
    total_usage: dict = {}

    def work(img: catalog.DocImage) -> None:
        if status().get("cancel"):
            return
        try:
            text, u = _describe_one(llm, img, names.get(img.doc_id, ""))
            description, decorative, note = parse_answer(text)
            catalog.record_result(img.id, description=description, decorative=decorative, usage=u, note=note)
            if not decorative:
                catalog.share_with_duplicates(img.id)  # the same picture elsewhere in the document: no second call
            key = "decorative" if decorative else "described"
        except Exception as e:  # noqa: BLE001 - one bad picture must not stop the run
            u = {}
            catalog.record_result(img.id, error=describe_llm_error(e))
            key = "failed"
            log.warning("describing picture %s failed: %s", img.id, describe_llm_error(e))
        with _lock:
            _job["done"] += 1
            _job[key] += 1
            _job["input_tokens"] += int(u.get("input_tokens", 0))
            _job["output_tokens"] += int(u.get("output_tokens", 0))
            for k in ("input_tokens", "output_tokens"):
                total_usage[k] = total_usage.get(k, 0) + int(u.get(k, 0))
            total_usage["llm_calls"] = total_usage.get("llm_calls", 0) + 1

    state = "failed"
    try:
        with ThreadPoolExecutor(max_workers=max(1, get_settings().vision_concurrency)) as pool:
            for doc_id, imgs in by_doc.items():
                list(pool.map(work, imgs))
                catalog.index_described(doc_id)  # searchable as soon as each document is finished
                if status().get("cancel"):
                    break
        state = "cancelled" if status().get("cancel") else "finished"
    except Exception as e:  # noqa: BLE001
        log.exception("describe run failed")
        with _lock:
            _job["error"] = f"{type(e).__name__}: {e}"
    finally:
        started = status().get("started_at", time.time())
        usage_log.record(user_id, kind="vision", usage=total_usage, latency_ms=int((time.time() - started) * 1000))
        with _lock:
            _job.update(state=state, finished_at=time.time())
