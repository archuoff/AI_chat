"""Step 7 of the RAG flow: write the answer with [n] citations.

Azure mode   : grounded generation, streamed token by token; any Azure failure falls back to extractive.
Offline mode : extractive answer built from the evidence (tables for comparisons, best fields for
               table lookups, best sentences for prose). Values are always copied verbatim.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable

from controller.engismart.chat.vision import image_parts
from controller.engismart.core.config import get_settings
from controller.engismart.core.llm import add_usage, describe_llm_error, get_chat_model, get_embedder
from controller.engismart.core.vocab import content_tokens, entity_key

log = logging.getLogger(__name__)

NOT_FOUND = ("I couldn't find this in the ingested documents. Try naming the part, vehicle, sheet or document, "
             "or rephrase with the terms used in the source files.")

SYSTEM_PROMPT = """You are Engismart, an engineering assistant for design guidelines, benchmarking data,
FMEAs, control plans, specifications and issue logs.

Grounding:
- Answer ONLY from the numbered sources provided. Do not use outside knowledge for facts.
- Copy numbers, units, ranges, IDs, part names and material grades EXACTLY as written in the sources.
- You may recognise equivalent engineering terms (e.g. USS = ultrasonic sensor, an ADAS parking sensor; CCB = cross car beam),
  but never invent values, definitions, expansions of abbreviations or classifications the sources do not state.
- Treat a different term as the one asked only if a source says they are the same (e.g. PPIR is not PIR).
- Never write what an abbreviation stands for (e.g. "PPIR (production PIR)") unless a source spells it out; use it exactly as written.
- If sources disagree, say so and cite both.

Style — write like a confident senior engineer:
- Lead with the answer. The first sentence (or the table) answers the question directly; no preamble, no restating the
  question, no "Based on the documents".
- State facts plainly ("The holder must be PP [1]."), not tentatively ("it appears that..."). Facts in the sources are certain.
- Cite each fact once with its source number in square brackets, e.g. [2] or [1][3]. Square brackets are ONLY for source
  numbers (never "[Weight Details]"). Do not add separate "Source:" lines. In tables, citations go only in the Source column.
- When listing or comparing several items (sensors, vehicles, parts, failure modes), use a markdown table with one row per
  item and a Source column. Include every item the sources list.
- Keep it tight: short paragraphs or bullets, only what helps the engineer act. No repetition.

Gaps:
- Answer every part the sources cover first. Then, only if something asked is not in the sources, add ONE short final line:
  "**Not covered in the documents:** <what is missing>." Do not cite sources for missing information and do not repeat it.
  Never refuse the whole question because one part is missing.
- Only if the sources contain nothing relevant at all, reply: "I couldn't find this in the documents." followed by one
  short sentence on what related information the knowledge base does contain, if any."""

Emit = Callable[[dict], None]


# ------------------------------------------------------------------ helpers
_header_cache: dict[str, list[float]] = {}


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _rank_headers(question: str, headers: list[str]) -> list[tuple[str, float]]:
    """Score column names against the question: embedding similarity + word overlap."""
    emb = get_embedder()
    qv = emb.embed_query(question)
    missing = [h for h in headers if h not in _header_cache]
    for h, v in zip(missing, emb.embed_documents(missing), strict=False):
        _header_cache[h] = v
    qt = {t.rstrip("s") for t in content_tokens(question)}
    out = []
    for h in headers:
        overlap = len(qt & {t.rstrip("s") for t in content_tokens(h)})
        out.append((h, _cos(qv, _header_cache[h]) + 0.25 * overlap))
    return sorted(out, key=lambda x: x[1], reverse=True)


def _best_sentences(question: str, text: str, k: int = 3) -> list[str]:
    parts = [p.strip(" -•\t") for p in re.split(r"(?<=[.!?])\s+|\n", text)]
    parts = [p for p in parts if len(p) > 15]
    if len(parts) <= k:
        return parts
    emb = get_embedder()
    qv = emb.embed_query(question)
    scored = [(i, _cos(qv, v)) for i, v in enumerate(emb.embed_documents(parts))]
    keep = sorted(i for i, _ in sorted(scored, key=lambda x: x[1], reverse=True)[:k])
    return [parts[i] for i in keep]


def _cell(v, limit: int) -> str:
    s = re.sub(r"\s*\n\s*", "; ", str(v)).replace("|", "/")
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _where(e: dict) -> str:
    loc = e["location"]
    for k in ("sheet", "page", "slide", "section"):
        if loc.get(k):
            label = {"page": "p.", "slide": "slide"}.get(k, "")
            return f"{label} {loc[k]}".strip()
    return e["file_name"]


# ------------------------------------------------------------------ offline composer
def _table(question: str, rows: list[dict]) -> str:
    headers = list(dict.fromkeys(h for r in rows for h in r["fields"]))
    ranked = _rank_headers(question, headers)

    def distinct(h: str) -> bool:
        return len({str(r["fields"].get(h)) for r in rows}) > 1

    # row label: the first column if it tells the rows apart (e.g. vehicle), else the most relevant column that does
    first = Counter(next(iter(r["fields"])) for r in rows).most_common(1)[0][0]
    key_header = first if distinct(first) else next((h for h, _ in ranked if distinct(h)), first)
    ranked = [(h, sc) for h, sc in ranked if h != key_header]
    varying = [(h, sc) for h, sc in ranked if distinct(h)]
    top = varying[0][1] if varying else 0
    cols = [h for h, sc in varying[:3] if sc >= top - 0.08]
    # columns with the same value on every row are stated once above the table
    common = [h for h, _ in ranked[:4] if not distinct(h) and all(h in r["fields"] for r in rows)][:2]
    lines = [f"**{h}:** {_cell(rows[0]['fields'][h], 300)}  " for h in common]
    if lines:
        lines.append("")
    lines += [f"| {key_header} | " + " | ".join(cols) + " | Source |", "|" + "---|" * (len(cols) + 2)]
    for r in rows:
        f = r["fields"]
        vals = [_cell(f.get(c, "–"), 220) for c in cols]
        lines.append(f"| {_cell(f.get(key_header, r.get('title') or ''), 80)} | " + " | ".join(vals) + f" | [{r['n']}] |")
    return "\n".join(lines)


def _record_lines(question: str, e: dict, k: int = 3, ids: list[str] | None = None) -> list[str]:
    fields = e["fields"] or {}
    picked: list[str] = []
    if ids:  # fields that literally contain the ID first
        picked = [h for h, v in fields.items() if any(i.lower() in str(v).lower() for i in ids)][:2]
    for h, _ in _rank_headers(question, [h for h in fields if h not in picked]):
        if len(picked) >= k:
            break
        picked.append(h)
    return [f"- **{h}**: {_cell(fields[h], 500)} [{e['n']}]" for h in picked]


def compose_extractive(question: str, plan: dict, evidence: list[dict]) -> str:
    if not evidence:
        return NOT_FOUND
    intent = plan.get("intent")
    records = [e for e in evidence if e["kind"] == "record" and e["fields"]]
    out: list[str] = []

    if intent in ("comparison", "list") and len(records) >= 2:
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in records:
            groups[f"{r['file_name']} › {_where(r)}"].append(r)
        name, rows = max(groups.items(), key=lambda kv: (len(kv[1]), max(r["score"] for r in kv[1])))
        out += [f"**{name}**", "", _table(question, rows)]
        rest = [e for e in evidence if e not in rows][:2]
        if rest:
            out += ["", "Related:"] + [f"- {e['context']} [{e['n']}]" for e in rest]
        return "\n".join(out)

    top = evidence[0]
    shown = [e for e in evidence[:3] if e["score"] >= top["score"] * 0.6]
    entities = set(plan.get("entities") or [])
    if entities:  # question names a specific item: prefer rows about that item
        named = [e for e in shown if entity_key(e.get("title") or "") in entities]
        shown = named or shown
    same_table = {f"{e['file_name']} › {_where(e)}" for e in shown}
    if len(shown) >= 2 and len(same_table) == 1 and all(e["kind"] == "record" and e["fields"] for e in shown):
        return "\n".join([f"**{same_table.pop()}**", "", _table(question, shown)])
    for e in shown:
        if e["kind"] == "record" and e["fields"]:
            out.append(f"**{e.get('title') or _where(e)}** — {e['file_name']} › {_where(e)}")
            out += _record_lines(question, e, ids=plan.get("ids"))
        else:
            out.append(f"**{e['context']}**")
            out += [f"> {s} [{e['n']}]" for s in _best_sentences(question, e["text"])]
        out.append("")
    return "\n".join(out).strip()


# ------------------------------------------------------------------ Azure generation
def _source_blocks(evidence: list[dict], budget: int) -> str:
    blocks, used = [], 0
    for e in evidence:
        block = f"[{e['n']}] {e['context']}\n{e['text']}"
        if used + len(block) > budget:
            block = block[: max(budget - used, 0)]
        if not block:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


IMAGE_RULES = """
The user attached image(s) to this question.
- Use what you see in the image(s) together with the sources. Label observations taken from the image as
  "From your image:", and cite document facts with [n] as usual.
- If no source matches, still answer what the image shows, and say plainly that no matching documents were
  found in the knowledge base. Never invent specification values that are not visible in the image or in a source."""


def generate_llm(question: str, history: list[dict], evidence: list[dict], emit: Emit,
                 usage: dict | None = None, images: list[str] | None = None,
                 image_context: str = "") -> tuple[str, str | None]:
    """Stream a grounded answer. Returns (answer, notice); raises on Azure failure before any token."""
    s = get_settings()
    llm = get_chat_model()
    sources = _source_blocks(evidence, s.max_context_chars) or "(no matching documents found in the knowledge base)"
    user = f"Question: {question}\n\nSources:\n{sources}"
    msgs = [("system", SYSTEM_PROMPT + (IMAGE_RULES if images else ""))]
    msgs += [(m["role"], m["content"][:2000]) for m in history[-2 * s.history_turns :]]
    if images:
        note = f"\n\nDescription of the attached image(s): {image_context}" if image_context else ""
        msgs.append(("user", [{"type": "text", "text": user + note}] + image_parts(images)))
    else:
        msgs.append(("user", user))
    parts: list[str] = []
    finish = None
    last_usage = None
    for chunk in llm.stream(msgs):
        token = chunk.content if isinstance(chunk.content, str) else ""
        if token:
            parts.append(token)
            emit({"type": "token", "text": token})
        finish = (chunk.response_metadata or {}).get("finish_reason") or finish
        if getattr(chunk, "usage_metadata", None):
            last_usage = chunk  # token counts arrive on the final chunk (stream_usage=True)
    add_usage(usage, last_usage)
    notice = None
    if finish == "content_filter":
        notice = "Part of the answer was blocked by the Azure OpenAI content filter."
    elif finish == "length":
        notice = "The answer was cut off at LLM_MAX_TOKENS."
    return "".join(parts), notice


def answer(question: str, plan: dict, history: list[dict], evidence: list[dict], emit: Emit,
           usage: dict | None = None, images: list[str] | None = None,
           image_context: str = "") -> tuple[str, str, str | None]:
    """Returns (answer, mode, notice). Token usage is added to `usage`.
    With attached images the LLM answers even without matching documents (it can still read the image)."""
    if get_chat_model() is not None and (evidence or images):
        streamed = []

        def tracking_emit(ev: dict):
            streamed.append(ev)
            emit(ev)

        try:
            text, notice = generate_llm(question, history, evidence, tracking_emit, usage, images, image_context)
            return text, "azure-openai", notice
        except Exception as e:  # noqa: BLE001 - degrade to extractive, never crash the chat
            log.warning("Azure generation failed: %s", e)
            if streamed:
                emit({"type": "reset"})
            notice = f"{describe_llm_error(e)} Showing an extractive answer instead."
            text = compose_extractive(question, plan, evidence)
            _emit_text(text, emit)
            return text, "offline-fallback", notice
    text = compose_extractive(question, plan, evidence)
    _emit_text(text, emit)
    return text, "offline", None


def _emit_text(text: str, emit: Emit) -> None:
    for piece in re.findall(r"\S+\s*", text):
        emit({"type": "token", "text": piece})


def cited_sources(answer_text: str, evidence: list[dict]) -> list[dict]:
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer_text)}
    return [{
        "n": e["n"], "file_name": e["file_name"], "file_type": e["file_type"], "doc_id": e["doc_id"],
        "location": e["location"], "context": e["context"], "breadcrumb": e.get("breadcrumb") or [], "title": e.get("title"), "score": e.get("relevance", e["score"]),
        "snippet": e["text"][:400], "cited": e["n"] in cited, "image_id": e.get("image_id"),
    } for e in evidence]
