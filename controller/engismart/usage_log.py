"""Token usage, cost and latency of LLM calls -> the platform's tbl_langfuse_usage_logs (one row per call).

Developers read it with SQL (queries in docs/ENGISMART_CHANGES.md). Mapping:
  application_name  'engismart' (a chat question) or 'engismart-<kind>' (classify, vision)
  trace_id          the chat session id (groups the questions of one conversation); empty for other kinds
  token             input + output tokens         cost  tokens x LLM_PRICE_*_PER_1M (0 while no price is set)
  latency           seconds                        model_name  the Azure deployment that answered"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from models.model import models
from models.orm_models import LangfuseUsageLogs

from .config import get_settings

log = logging.getLogger(__name__)
APPLICATION_NAME = "engismart"


def cost_of(input_tokens: int, output_tokens: int) -> Decimal:
    s = get_settings()
    return Decimal(str(round((input_tokens * s.llm_price_input_per_1m + output_tokens * s.llm_price_output_per_1m) / 1_000_000, 6)))


def record(user_id: int, *, kind: str = "question", session_id: str = "", usage: dict | None = None, latency_ms: int = 0) -> bool:
    """Never raises: usage accounting must not break a chat or a describe run."""
    u = usage or {}
    tokens_in, tokens_out = int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
    now = datetime.now()
    s = get_settings()
    try:
        with models() as db:
            saved = db.insert_record(LangfuseUsageLogs, {
                "user_id": user_id,
                "application_name": APPLICATION_NAME if kind == "question" else f"{APPLICATION_NAME}-{kind}",
                "token": tokens_in + tokens_out,
                "cost": cost_of(tokens_in, tokens_out),
                "latency": round(latency_ms / 1000, 3),
                "input_timestamp": now,
                "update_timestamp": now,
                "trace_id": (session_id or "")[:255] or None,
                "model_name": (s.azure_openai_vision_deployment if kind == "vision" else s.azure_openai_chat_deployment) or "offline",
            })
        return saved is not None
    except Exception:  # noqa: BLE001
        log.warning("could not record usage", exc_info=True)
        return False
