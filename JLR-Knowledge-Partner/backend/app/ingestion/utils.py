from __future__ import annotations

import datetime as dt
import re
from typing import Any

EXCEL_ERRORS = {"#VALUE!", "#REF!", "#N/A", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!", "#SPILL!", "#CALC!"}
_PLACEHOLDER = re.compile(r"^\(insert [^)]*\)$|^picture$", re.IGNORECASE)
_WS = re.compile(r"[ \t ]+")


def clean_text(s: str) -> str:
    lines = [_WS.sub(" ", line).strip() for line in str(s).replace("\r", "\n").split("\n")]
    out, blank = [], False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def normalize_value(v: Any) -> Any:
    """Return a clean JSON-safe value, or None if the cell should count as empty."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (dt.datetime, dt.date)):
        if isinstance(v, dt.datetime) and v.time() == dt.time(0):
            return v.date().isoformat()
        return v.isoformat()
    if isinstance(v, float):
        if v != v:  # NaN
            return None
        return int(v) if v.is_integer() else v
    if isinstance(v, int):
        return v
    s = clean_text(str(v))
    if not s or s in EXCEL_ERRORS or _PLACEHOLDER.match(s):
        return None
    return s


def is_textual(v: Any) -> bool:
    return isinstance(v, str)


def render_fields(fields: dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in fields.items())


def unique_keys(names: list[str], fallbacks: list[str]) -> list[str]:
    """Make header names unique and non-empty."""
    seen: dict[str, int] = {}
    out = []
    for name, fb in zip(names, fallbacks):
        name = name or fb
        if name in seen:
            seen[name] += 1
            name = f"{name} ({fb})"
        else:
            seen[name] = 1
        out.append(name)
    return out
