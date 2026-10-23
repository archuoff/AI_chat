"""Find existing documents that look like an uploaded file (code only, no LLM).

Every ingested document keeps a small signature on its registry entry:

    {"v": 1, "codes": [...], "topic": [...], "size": {...}}

* codes  bottom-k sketch of hashes of the document's cleaned cells / lines: two versions of one document
         share most codes, two documents built on the same template do not (template codes are ignored
         when they occur in many documents)
* topic  mean embedding of the document's chunks (what it is about)
* size   sheets / pages / slides and element counts (partial-update warning)

`suggest` ranks the visible documents for a new file and says why: similar name, same content, same topic.
The SME decides; nothing here replaces or hides a document.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

from ..config import get_settings
from .models import ParsedDocument

SKETCH_SIZE = 1024
TOPIC_SAMPLES = 16
SIGNATURE_VERSION = 1

_B, _E = r"(?<![a-z0-9])", r"(?![a-z0-9])"  # word edges that also work next to "_"
_DATE_RES = (re.compile(_B + r"\d{4}[-_.]\d{1,2}[-_.]\d{1,2}" + _E), re.compile(_B + r"\d{1,2}[-_.]\d{1,2}[-_.]\d{2,4}" + _E),
             re.compile(_B + r"(?:19|20)\d{6}" + _E))
_VERSION_RES = (re.compile(r"\(\d+\)"), re.compile(r"\brev(?:ision)?\s*[a-z0-9]{1,2}\b"),
                re.compile(r"\bv(?:er(?:sion)?)?\s*\d+(?:\s\d+)?\b"), re.compile(r"\b(?:copy|final|draft|latest)\b"))
_DECIMAL = re.compile(r"\d+[.,]\d+")
_NOT_WORD = re.compile(r"[^\w.]+")


def clean_name(file_name: str) -> str:
    """'Radar_spec Rev C (2).xlsx' -> 'radar spec'. Product numbers such as 'Gen 2' are kept."""
    s = file_name.lower()
    s = re.sub(r"\.[a-z0-9]{2,5}$", "", s)
    for rx in _DATE_RES:
        s = rx.sub(" ", s)
    s = re.sub(r"[_\-.]+", " ", s)
    for rx in _VERSION_RES:
        s = rx.sub(" ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]+", " ", s)).strip()


def name_score(a: str, b: str) -> float:
    ca, cb = clean_name(a), clean_name(b)
    if not ca or not cb:
        return 0.0
    return 1.0 if ca == cb else round(SequenceMatcher(None, ca, cb).ratio(), 3)


def _number(m: re.Match) -> str:
    s = m.group().replace(",", ".")
    return s.rstrip("0").rstrip(".") if "." in s else s


def normalize(text: Any) -> str:
    """Same value, same string: '5.50' = '5,5' = '5.5', case / spacing / punctuation ignored."""
    s = str(text).lower().replace(" ", " ")
    s = _DECIMAL.sub(_number, s)
    return re.sub(r"\s+", " ", _NOT_WORD.sub(" ", s)).strip()


def _hash(s: str) -> int:
    return int.from_bytes(hashlib.sha1(s.encode("utf-8")).digest()[:8], "big") >> 2  # 62 bits: safe for JSON / Qdrant


def content_codes(parsed: ParsedDocument) -> list[int]:
    """Bottom-k sketch of the document's cleaned cells (table records) and lines (text)."""
    codes: set[int] = set()
    for el in parsed.elements:
        if el.kind == "record" and el.fields:
            for k, v in el.fields.items():
                value = normalize(v)
                if value:
                    codes.add(_hash(f"{normalize(k)}={value}"))
        else:
            for line in el.text.split("\n"):
                line = normalize(line)
                if len(line) >= 15:
                    codes.add(_hash(line))
    return sorted(codes)[:SKETCH_SIZE]


def size_of(parsed: ParsedDocument) -> dict[str, Any]:
    st = parsed.stats or {}
    if parsed.file_type in ("xlsx", "xlsm"):
        unit, units = "sheets", sum(1 for s in (st.get("sheets") or {}).values() if not s.get("skipped"))
    elif parsed.file_type == "pdf":
        unit, units = "pages", int(st.get("pages") or 0)
    elif parsed.file_type == "pptx":
        unit, units = "slides", int(st.get("slides") or 0)
    else:
        unit, units = "", 0
    return {"unit": unit, "units": units, "records": sum(e.kind == "record" for e in parsed.elements),
            "text_blocks": sum(e.kind == "text" for e in parsed.elements)}


def mean_vector(vectors: list[list[float]]) -> list[float] | None:
    vectors = [v for v in vectors if v]
    if not vectors:
        return None
    n = len(vectors)
    return [round(sum(col) / n, 4) for col in zip(*vectors)]


def cosine(a: list[float] | None, b: list[float] | None) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return None if not na or not nb else round(sum(x * y for x, y in zip(a, b)) / (na * nb), 3)


def sample_texts(parsed: ParsedDocument) -> list[str]:
    """Evenly spread element texts: the input of the topic vector of a file that is not indexed yet."""
    els = [e for e in parsed.elements if e.text.strip()]
    if not els:
        return []
    step = max(1, len(els) // TOPIC_SAMPLES)
    return [f"{parsed.file_name}\n{e.text[:600]}" for e in els[::step][:TOPIC_SAMPLES]]


def build_signature(parsed: ParsedDocument, topic: list[float] | None) -> dict[str, Any]:
    return {"v": SIGNATURE_VERSION, "codes": content_codes(parsed), "topic": topic, "size": size_of(parsed)}


def jaccard(a: set[int], b: set[int]) -> float:
    """Overlap estimate of two bottom-k sketches (exact when both hold the whole document)."""
    if not a or not b:
        return 0.0
    union = sorted(a | b)[:SKETCH_SIZE]
    return round(sum(1 for x in union if x in a and x in b) / len(union), 3)


def document_frequency(docs: list[dict]) -> tuple[Counter, int]:
    """In how many documents each content code occurs; codes of template / boilerplate occur in many."""
    df: Counter = Counter()
    n = 0
    for d in docs:
        codes = (d.get("signature") or {}).get("codes")
        if codes:
            n += 1
            df.update(set(codes))
    return df, n


def _ranked(scores: dict[str, Any], same_domain: bool) -> float:
    topic = scores["topic"]
    return (0.5 * (scores["content"] or 0) + 0.3 * scores["name"] + 0.2 * (max(0.0, (topic - 0.5) / 0.5) if topic else 0)
            + (0.05 if same_domain else 0))


def classify(scores: dict[str, Any]) -> str | None:
    s = get_settings()
    content, name, topic = scores["content"], scores["name"], scores["topic"]
    if content is not None and content >= s.sim_likely_content:
        return "likely"
    if name >= s.sim_likely_name and ((content or 0) >= s.sim_related_content or (topic or 0) >= s.sim_likely_topic):
        return "likely"
    if (topic or 0) >= s.sim_related_topic or name >= s.sim_related_name or (content or 0) >= s.sim_related_content:
        return "related"
    return None


def suggest(file_name: str, fingerprint: str, signature: dict | None, docs: list[dict], domain: str = "",
            limit: int = 5) -> dict[str, Any]:
    """docs = the registry entries the uploader may see (with signatures). Returns exact copies + ranked suggestions."""
    live = [d for d in docs if not d.get("superseded")]
    df, n = document_frequency(live)
    common = {c for c, k in df.items() if k >= max(3, math.ceil(0.2 * n))}
    mine = set((signature or {}).get("codes") or []) - common
    topic = (signature or {}).get("topic")
    exact = [{"doc_id": d["doc_id"], "file_name": d["file_name"], "domain": d.get("domain", ""),
              "superseded": bool(d.get("superseded")), "replaced_by": d.get("replaced_by")}
             for d in docs if d.get("content_hash") == fingerprint]
    out, unchecked = [], 0
    for d in live:
        sig = d.get("signature")
        if not sig:
            unchecked += 1
        scores = {"name": name_score(file_name, d["file_name"]),
                  "content": jaccard(mine, set(sig.get("codes") or []) - common) if sig and mine else None,
                  "topic": cosine(topic, sig.get("topic")) if sig else None}
        label = classify(scores)
        if label is None:
            continue
        same_domain = bool(domain) and d.get("domain") == domain
        reasons = []
        if scores["name"] >= get_settings().sim_related_name:
            reasons.append(f"similar name {round(scores['name'] * 100)}%")
        if scores["content"] is not None and scores["content"] >= get_settings().sim_related_content:
            reasons.append(f"{round(scores['content'] * 100)}% same content")
        if (scores["topic"] or 0) >= get_settings().sim_related_topic:
            reasons.append("similar topic")
        if same_domain:
            reasons.append("same domain")
        out.append({"doc_id": d["doc_id"], "file_name": d["file_name"], "domain": d.get("domain", ""), "label": label,
                    "reasons": reasons, "scores": scores, "size": d.get("sig_size"), "_rank": _ranked(scores, same_domain)})
    out.sort(key=lambda x: (x["label"] == "likely", x["_rank"]), reverse=True)
    for x in out:
        del x["_rank"]
    return {"exact": exact, "suggestions": out[:limit], "unchecked": unchecked}
