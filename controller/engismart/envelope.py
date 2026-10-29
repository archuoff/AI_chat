"""Every Engismart JSON answer uses the platform's envelope  {"status": bool, "data": ..., "message": str, "error": str|None}.

Streams (chat tokens) and files (pictures) are not JSON and are returned as they are."""
from __future__ import annotations


def ok(data, message: str = "") -> dict:
    return {"status": True, "data": data, "message": message, "error": None}


def fail(message: str, error: str | None = None, data=None) -> dict:
    return {"status": False, "data": data, "message": message, "error": error}
