"""Describe waiting pictures with the vision deployment (background job), then index the descriptions.

Nothing here runs until AZURE_OPENAI_VISION_DEPLOYMENT is set: company documents are described with
the company Azure resource only. Before a run the UI shows the picture count and a token / cost estimate.
"""
from __future__ import annotations

import base64
import logging
import math
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
Text around it in the document:
{context}

Write 3-8 short factual lines:
- what it shows (part, assembly, section view, CAD screenshot, test photo, chart, diagram, table image ...)
- every readable label, part number, code, callout and note - transcribe exactly
- dimensions, values, tolerances, units and materials that are visible
- defects, failure signs or highlighted areas, if any
Do not guess what is not visible. If the picture is only a logo, icon, decoration or empty frame, answer exactly: DECORATIVE"""

PROMPT_TOKENS = 260  # instructions + typical context
OUTPUT_TOKENS = 220

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


def estimate(images: list[catalog.DocImage]) -> dict[str, Any]:
    s = get_settings()
    stored = [(min(i.width, catalog.FULL_PX) if i.width >= i.height else round(i.width * catalog.FULL_PX / max(i.height, 1)),
               min(i.height, catalog.FULL_PX) if i.height >= i.width else round(i.height * catalog.FULL_PX / max(i.width, 1)))
              for i in images]
    tin = sum(_image_tokens(w, h, s.vision_detail) + PROMPT_TOKENS for w, h in stored)
    tout = OUTPUT_TOKENS * len(images)
    priced = s.vision_price_input_per_1m > 0 or s.vision_price_output_per_1m > 0
    cost = (tin * s.vision_price_input_per_1m + tout * s.vision_price_output_per_1m) / 1e6 if priced else None
    return {"images": len(images), "input_tokens": tin, "output_tokens": tout, "cost": round(cost, 2) if cost is not None else None}


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


def _describe_one(llm, img: catalog.DocImage, file_name: str) -> tuple[str, dict]:
    where = f"{file_name}, {catalog._where(img.location) or 'document'}"
    data = base64.b64encode(catalog.file_path(img).read_bytes()).decode()
    usage: dict = {}
    msg = llm.invoke([("user", [
        {"type": "text", "text": PROMPT.format(where=where, context=img.context.strip()[:800] or "(none)")},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}", "detail": get_settings().vision_detail}},
    ])])
    add_usage(usage, msg)
    return str(msg.content).strip(), usage


def start_job(user_id: int, doc_ids: list[str] | None = None, image_ids: list[str] | None = None) -> dict[str, Any]:
    """Start describing the selected waiting pictures in the background. Raises if disabled or already running."""
    llm = get_vision_model()
    if llm is None:
        raise RuntimeError("No vision deployment configured (AZURE_OPENAI_VISION_DEPLOYMENT)")
    todo = catalog.waiting(doc_ids, image_ids)
    with _lock:
        if _job.get("state") == "running":
            raise RuntimeError("A describe run is already in progress")
        if not todo:
            raise ValueError("No pictures are waiting")
        _job.clear()
        _job.update(state="running", total=len(todo), done=0, described=0, decorative=0, failed=0, input_tokens=0,
                    output_tokens=0, started_at=time.time(), user_id=user_id, cancel=False, estimate=estimate(todo))
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
            decorative = text.strip().upper().rstrip(".") == "DECORATIVE"
            catalog.record_result(img.id, description=text, decorative=decorative, usage=u)
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
