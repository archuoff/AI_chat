"""LLM relevance judge: decides which retrieved passages actually help answer the question.

Cross-encoders score word overlap well but miss domain synonyms (an "ADAS sensor" question vs a
table of "USS Front S1" rows scores ~0). The judge reads the question parts and the candidate
passages together and keeps the ones that contain needed information. Returns None on failure so
the caller can fall back to score thresholds.
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from ..llm import add_usage, describe_llm_error, get_chat_model

log = logging.getLogger(__name__)

PASSAGE_CHARS = 700

_PROMPT = """You filter search results for an automotive engineering assistant (JLR / Tata Technologies).

For each numbered passage decide whether it contains information needed to answer the question
(or one of its parts). Use engineering knowledge to recognise equivalent terms: e.g. "USS Front S1"
is an ADAS ultrasonic (parking) sensor; "CCB" is a cross car beam; FMEA rows describe failure causes.

Grades:
  2 = directly answers (part of) the question: it is about the SPECIFIC item asked (e.g. for a CCB question, a CCB
      row — not another part from the same benchmarking workbook; for a PIR question, the PIR entries)
  1 = useful supporting context (definitions, conditions, related values)
Be precise: leave out passages about other parts, vehicles, sensors or topics even if they come from the same document
and look similar, and passages that only share the general topic. List only passages graded 1 or 2; if nothing helps, return an empty list."""


class JudgedPassage(BaseModel):
    id: int = Field(description="Passage number")
    grade: Literal[0, 1, 2] = Field(description="0 = not relevant (or simply omit the passage)")


class Judgement(BaseModel):
    relevant: list[JudgedPassage] = Field(default_factory=list)


def judge(question: str, sub_questions: list[str], passages: list[str], usage: dict | None = None) -> dict[int, int] | None:
    """Return {passage index: grade} for relevant passages, or None if the LLM is unavailable/failed.
    Token usage of the judging call is added to `usage`."""
    llm = get_chat_model(fast=True)
    if llm is None or not passages:
        return None
    parts = "\n".join(f"  - {q}" for q in sub_questions if q.strip() and q.strip() != question.strip())
    body = f"Question: {question}\n" + (f"Parts:\n{parts}\n" if parts else "") + "\nPassages:\n"
    body += "\n\n".join(f"[{i}] {p[:PASSAGE_CHARS]}" for i, p in enumerate(passages, start=1))
    try:
        res = llm.with_structured_output(Judgement, method="function_calling", include_raw=True).invoke(
            [("system", _PROMPT), ("user", body)])
        add_usage(usage, res.get("raw"))
        out: Judgement | None = res.get("parsed")
        if out is None:
            raise ValueError(f"unparseable judgement: {res.get('parsing_error')}")
    except Exception as e:  # noqa: BLE001 - fall back to thresholds
        log.warning("LLM judge failed: %s", describe_llm_error(e))
        return None
    return {p.id - 1: p.grade for p in out.relevant if p.grade and 1 <= p.id <= len(passages)}
