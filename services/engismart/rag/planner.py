"""Step 1-2 of the RAG flow: understand the question and plan the search.

plan_rules()  - offline: regex + vocabulary matching, follow-up handling from the previous plan
plan_llm()    - Azure OpenAI structured output, validated against the vocabulary; falls back to rules
"""
from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from ..llm import add_usage, describe_llm_error, get_chat_model
from .vocab import content_tokens, get_vocabulary

log = logging.getLogger(__name__)

Intent = Literal["lookup", "comparison", "list", "explanation", "exact_id", "chitchat"]

_ID = re.compile(r"\b(?=[\w.-]*\d)(?=[\w.-]*[A-Za-z])[A-Za-z][\w]*[-_.][\w.-]*[A-Za-z0-9]\b|\b[A-Za-z]{2,}\d{2,}\b")
_GREETING = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening)|ok|okay)\W*$", re.I)
_COMPARE = re.compile(r"\b(compare|comparison|vs\.?|versus|differences?|differ|across|between|each vehicle|all vehicles|every vehicle)\b", re.I)
_LIST = re.compile(r"^\s*(list|show (me )?all|which|what are (all )?the|how many|give me all)\b|\ball\b", re.I)
_EXPLAIN = re.compile(r"^\s*(how|why|explain|describe|what should|what is the (process|procedure|rule))\b|\b(guideline|rule|recommend|requirement)s?\b", re.I)
_FOLLOW_UP = re.compile(r"^\s*(and|what about|how about|same for|also|what of|for)\b|\b(it|its|they|them|those|that one|this one)\b", re.I)


class QueryPlan(BaseModel):
    standalone_question: str = Field(description="The question rewritten to be understandable without chat history.")
    intent: Intent = Field(description="lookup=single fact; comparison=same attribute across several items; list=enumerate/filter "
                                       "items; explanation=how/why/guidelines; exact_id=question is about a specific ID/code; "
                                       "chitchat=greeting or thanks, no document search needed.")
    sub_questions: list[str] = Field(default_factory=list, description="The distinct parts of the question, each self-contained "
                                     "(1 item if the question asks one thing; at most 3).")
    search_queries: list[str] = Field(default_factory=list, description="1-4 short search queries for a document search engine. "
                                      "Cover every sub-question and add engineering synonyms / expansions of abbreviations.")
    ids: list[str] = Field(default_factory=list, description="Exact IDs / codes / part numbers mentioned (e.g. req-5256401-00139853).")
    sheets: list[str] = Field(default_factory=list, description="Names from the KNOWN SHEETS list the question is about (exact spelling).")
    entities: list[str] = Field(default_factory=list, description="Vehicles or named items mentioned, lower case brand + model "
                                "(e.g. 'bmw x5'). Empty if none.")


def _extract_ids(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(0).strip(".-_") for m in _ID.finditer(text)))


def _intent(q: str, ids: list[str]) -> Intent:
    if _GREETING.match(q):
        return "chitchat"
    if ids and len(content_tokens(q)) <= len(ids) + 3:
        return "exact_id"
    if _COMPARE.search(q):
        return "comparison"
    if _LIST.search(q):
        return "list"
    if _EXPLAIN.search(q):
        return "explanation"
    return "lookup"


def plan_rules(question: str, previous: dict | None = None) -> QueryPlan:
    vocab = get_vocabulary()
    q = question.strip()
    ids = _extract_ids(q)
    sheets = vocab.match_sheets(q)
    entities = vocab.match_entities(q)
    intent = _intent(q, ids)
    standalone = q
    names_something = bool(ids or sheets or entities)
    is_follow_up = bool(_FOLLOW_UP.search(q)) or (len(content_tokens(q)) <= 1 and not names_something)
    if previous and intent not in ("chitchat", "exact_id") and is_follow_up:
        # follow-up: carry over what the previous question was about
        sheets = sheets or previous.get("sheets", [])
        if not entities:
            entities = previous.get("entities", [])
        if intent == "lookup" and previous.get("intent") in ("comparison", "list"):
            intent = previous["intent"]
        standalone = f"{q} (follow-up to: {previous.get('standalone_question', '')})"
    return QueryPlan(standalone_question=standalone, intent=intent, search_queries=[standalone] if intent != "chitchat" else [],
                     sub_questions=[standalone] if intent != "chitchat" else [], ids=ids, sheets=sheets, entities=entities)


_PLANNER_PROMPT = """You plan searches over an automotive engineering knowledge base (JLR / Tata Technologies):
benchmarking tables, FMEAs and control plans, design guidelines and specifications (Excel, PDF, Word, PowerPoint).

1. Rewrite the user's latest question so it stands alone (resolve follow-ups using the chat history).
   If it already stands alone, keep the user's wording unchanged.
2. Split it into its distinct parts (sub_questions). A question that asks two things gets two sub-questions.
3. Write search queries that cover every part. Documents use their own vocabulary, so add synonyms and
   expansions, e.g. "ADAS sensors" -> also "ultrasonic sensors USS PDC parking sensors radar camera";
   "CCB" <-> "cross car beam"; "IP" <-> "instrument panel".
   Each query: plain words, at most ~12 words, no quotation marks. Do not invent part names or codes.
   Never guess what an unfamiliar abbreviation stands for (e.g. PIR, PPIR): search it exactly as written,
   and do not mix in sheet names or other terms that are not part of the question.
4. Classify the intent. Only name a sheet if the question is clearly about that table.

KNOWN SHEETS (Excel tables, one row per item): {sheets}
"""


def needs_llm_planning(question: str, history: list[dict]) -> bool:
    """Quality mode ("always"): every question is planned by the LLM (sub-questions + synonyms).
    Speed mode ("follow-ups"): only follow-ups need it; rules plan the rest in ~0 ms."""
    from ..config import get_settings

    if get_settings().llm_planning == "always":
        return not _GREETING.match(question)
    if not history:
        return False
    q = question.strip()
    return bool(_FOLLOW_UP.search(q)) or len(content_tokens(q)) <= 3


def plan_llm(question: str, history: list[dict], previous: dict | None = None,
             usage: dict | None = None) -> tuple[QueryPlan, str | None]:
    """Return (plan, notice). notice is set when Azure failed and rules were used instead.
    Token usage of the planning call is added to `usage`."""
    llm = get_chat_model(fast=True)
    if llm is None or not needs_llm_planning(question, history):
        return plan_rules(question, previous), None
    vocab = get_vocabulary()
    system = _PLANNER_PROMPT.format(sheets=", ".join(sorted(vocab.sheets)) or "none")
    msgs = [("system", system)] + [(m["role"], m["content"][:1500]) for m in history[-6:]] + [("user", question)]
    try:
        out = llm.with_structured_output(QueryPlan, method="function_calling", include_raw=True).invoke(msgs)
        add_usage(usage, out.get("raw"))
        plan: QueryPlan | None = out.get("parsed")
        if plan is None:
            raise ValueError(f"unparseable plan: {out.get('parsing_error')}")
    except Exception as e:  # noqa: BLE001 - never let planning break the chat
        log.warning("LLM planning failed, using rules: %s", e)
        return plan_rules(question, previous), f"Azure OpenAI planning unavailable ({describe_llm_error(e)}); used rule-based planning."
    # validate against what really exists, and merge what the rules detect (IDs, sheets, entities)
    rules = plan_rules(question, previous)
    plan.sheets = list(dict.fromkeys([s for s in plan.sheets if s in vocab.sheets] + rules.sheets))
    plan.entities = list(dict.fromkeys([e for e in plan.entities if e in vocab.entities] + rules.entities))
    plan.ids = list(dict.fromkeys(plan.ids + rules.ids))
    if plan.intent == "chitchat" and rules.intent != "chitchat":
        plan.intent = rules.intent
    if plan.intent != "chitchat":
        plan.sub_questions = [q for q in plan.sub_questions if q.strip()][:3] or [plan.standalone_question]
        # the original wording is always searched too; then the LLM's expanded queries
        plan.search_queries = list(dict.fromkeys([plan.standalone_question] + [q for q in plan.search_queries if q.strip()]))[:4]
    return plan, None
