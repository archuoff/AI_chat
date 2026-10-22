"""Suggest which engineering domain a document belongs to.

Azure OpenAI reads the file name + a sample of the document's chunks and picks a domain (structured
output, validated). Without Azure, or if the call fails, keyword scoring is used. The suggestion is
only a suggestion: the user confirms it on the Manage page.
"""
from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from .domains import DOMAINS, UNASSIGNED
from .llm import add_usage, describe_llm_error, get_chat_model
from .store import get_store

log = logging.getLogger(__name__)

SAMPLE_CHUNKS = 12
SAMPLE_CHARS = 3000

DomainId = Literal["adas", "benchmarking", "eds", "lead-engineering", "materials-net", "supplier-database", "unassigned"]


class DomainSuggestion(BaseModel):
    domain: DomainId = Field(description="The best matching domain id, or 'unassigned' if none fits.")
    confidence: float = Field(ge=0, le=1, description="0..1 confidence in this classification.")
    reason: str = Field(description="One short sentence explaining the choice, referring to the document content.")


def _sample(doc_id: str, file_name: str) -> str:
    chunks = get_store().scroll_chunks({"doc_id": doc_id}, limit=SAMPLE_CHUNKS, fields=["context", "text"])
    body = "\n".join(f"{c.get('context', '')}\n{c.get('text', '')}" for c in chunks)
    return f"File name: {file_name}\n\n{body}"[:SAMPLE_CHARS]


def _keyword_suggestion(sample: str, file_name: str) -> dict:
    text = sample.lower()
    name = file_name.lower()
    scores = {}
    for d in DOMAINS:
        hits = sum(len(re.findall(re.escape(k), text)) for k in d.keywords)
        hits += 3 * sum(k in name for k in d.keywords)  # file names are strong signals
        scores[d.id] = hits
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if scores[best] == 0:
        return {"domain": UNASSIGNED, "confidence": 0.0, "reason": "No domain keywords found.", "method": "keywords", "scores": scores}
    return {"domain": best, "confidence": round(scores[best] / total, 2),
            "reason": f"Keyword matches: {scores[best]} of {total} for this domain.", "method": "keywords", "scores": scores}


_PROMPT = """Classify an engineering document into exactly one knowledge domain.

DOMAINS:
{domains}

Pick the domain the document is primarily about. Use 'unassigned' only if none fits.
Base the decision on the file name and the content sample."""


def suggest_domain(doc_id: str, usage: dict | None = None) -> dict:
    doc = get_store().get_document(doc_id)
    if doc is None:
        raise KeyError(doc_id)
    sample = _sample(doc_id, doc["file_name"])
    fallback = _keyword_suggestion(sample, doc["file_name"])
    llm = get_chat_model(fast=True)
    if llm is None:
        return fallback
    domains = "\n".join(f"- {d.id}: {d.name} — {d.description}" for d in DOMAINS)
    try:
        res = llm.with_structured_output(DomainSuggestion, method="function_calling", include_raw=True).invoke(
            [("system", _PROMPT.format(domains=domains)), ("user", sample)])
        add_usage(usage, res.get("raw"))
        s: DomainSuggestion | None = res.get("parsed")
        if s is None:
            raise ValueError(f"unparseable suggestion: {res.get('parsing_error')}")
    except Exception as e:  # noqa: BLE001 - fall back to keywords
        log.warning("LLM domain suggestion failed: %s", describe_llm_error(e))
        return {**fallback, "notice": describe_llm_error(e)}
    return {"domain": s.domain, "confidence": round(s.confidence, 2), "reason": s.reason, "method": "azure-openai",
            "scores": fallback["scores"]}
