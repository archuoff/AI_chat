"""Files waiting between the upload check and the commit.

`POST /api/documents/check` stores the file here, parses it once and suggests similar documents;
`POST /api/documents/commit` ingests the same file with the SME's choice (no second transfer, no second parse
for files below PARSE_CACHE_MAX_BYTES).
"""
from __future__ import annotations

import shutil
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from controller.engismart.core.config import get_settings
from controller.engismart.ingestion.models import ParsedDocument

PENDING_TTL_S = 24 * 3600
PARSE_CACHE_MAX_BYTES = 50 * 1024 * 1024  # larger files are parsed again at commit rather than held in memory
PARSE_CACHE_SIZE = 3


@dataclass
class Pending:
    check_id: str
    user_id: int
    file_name: str
    path: Path
    fingerprint: str
    size_bytes: int
    created: float = field(default_factory=time.time)
    found: dict = field(default_factory=dict)  # what the check suggested (exact copies + suggestions), for the log
    parsed: ParsedDocument | None = None


_lock = threading.Lock()
_items: dict[str, Pending] = {}
_parsed_order: OrderedDict[str, None] = OrderedDict()


def _root() -> Path:
    return Path(get_settings().upload_dir) / "pending"


def new_path(file_name: str) -> tuple[str, Path]:
    check_id = uuid.uuid4().hex
    folder = _root() / check_id
    folder.mkdir(parents=True, exist_ok=True)
    return check_id, folder / file_name


def add(item: Pending, parsed: ParsedDocument | None) -> None:
    with _lock:
        _items[item.check_id] = item
        if parsed is not None and item.size_bytes <= PARSE_CACHE_MAX_BYTES:
            item.parsed = parsed
            _parsed_order[item.check_id] = None
            while len(_parsed_order) > PARSE_CACHE_SIZE:
                old, _ = _parsed_order.popitem(last=False)
                if old in _items:
                    _items[old].parsed = None
    cleanup()


def get(check_id: str, user_id: int) -> Pending | None:
    with _lock:
        item = _items.get(check_id)
    return item if item and item.user_id == user_id and item.path.exists() else None


def discard(check_id: str) -> None:
    with _lock:
        _items.pop(check_id, None)
        _parsed_order.pop(check_id, None)
    shutil.rmtree(_root() / check_id, ignore_errors=True)


def cleanup() -> None:
    """Drop checks older than a day, including folders left behind by a restart."""
    limit = time.time() - PENDING_TTL_S
    root = _root()
    if not root.is_dir():
        return
    for folder in root.iterdir():
        try:
            if folder.stat().st_mtime < limit:
                discard(folder.name)
        except OSError:
            pass
