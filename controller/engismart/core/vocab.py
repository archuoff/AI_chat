"""Vocabulary of names found in the ingested data, used to recognise them in questions.

* sheets   : Excel sheet names that hold tables ("CCB", "FRONT BUMPER FASCIA")
* entities : short record titles grouped by an alias key, so different spellings of the same thing
             ("MERC – GLC 300e 4MATIC PHEV (2023)", "Mercedes GLC 300e 4MATIC AMG Line (2023)") share one key
             ("mercedes glc")
* headers  : table column names ("Weight Details", "Part Material (Type & Grade)")
Rebuilt lazily after every ingestion.
"""
from __future__ import annotations

import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from controller.engismart.core.store import get_store

_SPELLING = {"centre": "center", "mould": "mold", "moulding": "molding", "colour": "color", "aluminium": "aluminum",
             "fibre": "fiber", "merc": "mercedes", "benz": "mercedes", "vw": "volkswagen"}
_STOP = {"the", "a", "an", "of", "for", "and", "or", "in", "on", "to", "is", "are", "what", "which", "how", "does",
         "do", "with", "by", "from", "at", "its", "it", "me", "show", "give", "tell", "about", "all", "vs", "versus"}


def norm_tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", text.lower().replace("‑", "-"))
    return [_SPELLING.get(t, t) for t in toks]


def norm(text: str) -> str:
    return " ".join(norm_tokens(text))


def content_tokens(text: str) -> list[str]:
    return [t for t in norm_tokens(text) if t not in _STOP]


def entity_key(title: str) -> str | None:
    """'BMW – X5 xDrive50e PHEV (2026)' -> 'bmw x5'.  None for titles that are not names."""
    t = re.sub(r"\([^)]*\)", " ", title)
    toks = norm_tokens(t)
    if not toks or len(title) > 80 or len(title.split()) > 12 or all(x.isdigit() for x in toks):
        return None
    return " ".join(toks[:2])


@dataclass
class Vocabulary:
    sheets: dict[str, set[str]] = field(default_factory=dict)  # sheet name -> file names
    entities: dict[str, set[str]] = field(default_factory=dict)  # alias key -> original titles
    headers: set[str] = field(default_factory=set)

    # ---------------------------------------------------------------- matching
    def match_sheets(self, question: str) -> list[str]:
        q = f" {norm(question)} "
        words = norm_tokens(question)
        initials = {"".join(w[0] for w in words[i : i + n]) for n in (2, 3, 4) for i in range(len(words) - n + 1)}
        found = []
        for sheet in self.sheets:
            s = norm(sheet)
            if not s:
                continue
            if f" {s} " in q:
                found.append(sheet)
            elif " " not in s and len(s) >= 3 and s in initials:  # "cross car beam" -> CCB
                found.append(sheet)
        return found

    def match_entities(self, question: str) -> list[str]:
        """Full alias match ('bmw x5'); a lone first word ('audi') matches every alias starting with it."""
        q = set(norm_tokens(question))
        full = [key for key in self.entities if set(key.split()) <= q]
        heads = {k.split()[0] for k in full}
        partial = [key for key in self.entities
                   if " " in key and key.split()[0] in q and key.split()[0] not in heads and len(key.split()[0]) >= 3]
        return full + partial


_lock = threading.Lock()
_cache: Vocabulary | None = None


def invalidate_vocabulary() -> None:
    global _cache
    with _lock:
        _cache = None


def get_vocabulary() -> Vocabulary:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        sheets: dict[str, set[str]] = defaultdict(set)
        entities: dict[str, set[str]] = defaultdict(set)
        headers: set[str] = set()
        rows = get_store().scroll_chunks({"kind": "record", "!superseded": True}, limit=100_000, fields=["file_name", "title", "location", "fields"])
        for r in rows:
            sheet = (r.get("location") or {}).get("sheet")
            if sheet:
                sheets[sheet].add(r["file_name"])
            key = entity_key(r.get("title") or "")
            if key and len(key) >= 3:
                entities[key].add(r["title"])
            headers.update((r.get("fields") or {}).keys())
        _cache = Vocabulary(dict(sheets), dict(entities), headers)
        return _cache
