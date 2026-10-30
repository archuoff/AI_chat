"""Request bodies and the checks of an upload.

* Pydantic bodies of the JSON endpoints (read by helper.run_endpoint after the login check).
* validate_upload: the platform's upload checks in the platform's order (compare upload_tabular_file in controller/common/common.py):
  extension -> size -> virus scan (ClamAV) -> content matches the extension. It is written for every format Engismart reads
  (xlsx, xlsm, csv, pdf, docx, pptx, txt, md); the platform's own functions only know csv/xlsx/xls. It holds nothing
  Engismart-specific, so it can move to common.py unchanged (ask the team; see ENGISMART_CHANGES.md).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from controller.common.common import scan_file_content_for_virus
from controller.engismart.core.config import get_settings
from controller.engismart.helper import audit
from controller.engismart.ingestion import SUPPORTED_EXTENSIONS

log = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default_factory=lambda: get_settings().top_k, ge=1, le=50)
    mode: Literal["hybrid", "dense", "keyword"] = "hybrid"
    filters: dict[str, Any] | None = Field(default=None, description='e.g. {"file_type": "xlsx", "meta.project": "EDS"}')


class FolderIngestRequest(BaseModel):
    path: str
    meta: dict[str, Any] = {}
    force: bool = False
    domain: str | None = None


class ParseOptionsUpdate(BaseModel):
    parse_options: dict[str, Any] = Field(
        description='{"sheets": {"Sheet1": {"skip": true}}, "tables": {"Sheet1!A1:H20": {"header_rows": 2, "skip": false}}}')


class DomainUpdate(BaseModel):
    domain: str


class BulkDomainUpdate(BaseModel):
    doc_ids: list[str] = Field(min_length=1, max_length=500)
    domain: str


class AccessUpdate(BaseModel):
    confidential: bool


class ImageUpdate(BaseModel):
    included: bool


class DescribeRequest(BaseModel):
    doc_ids: list[str] | None = None  # None = every document
    image_ids: list[str] | None = None


class CommitRequest(BaseModel):
    check_id: str
    intent: Literal["new", "update"] = "new"
    replaces: str | None = None  # doc_id of the document this file updates (intent "update")
    domain: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    force: bool = False
    allow_duplicate: bool = False


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    filters: dict[str, Any] | None = None
    images: list[str] = Field(default_factory=list, description="Attached images as data URLs (png/jpeg/webp/gif, max 4 x 5 MB)")


class RewindRequest(BaseModel):
    turns: int = Field(ge=0, le=500, description="Keep the first N questions with their answers; everything after is forgotten")


# ------------------------------------------------------------------ uploads
ZIP_MAGIC = b"PK\x03\x04"  # xlsx, xlsm, docx and pptx are zip containers
PDF_MAGIC = b"%PDF"
TEXT_EXTENSIONS = {".csv", ".txt", ".md"}


def content_matches_extension(ext: str, content: bytes) -> bool:
    """Reject a file whose real content does not fit its extension (e.g. an .exe renamed to .xlsx)."""
    if ext in (".xlsx", ".xlsm", ".docx", ".pptx"):
        return content.startswith(ZIP_MAGIC)
    if ext == ".pdf":
        return PDF_MAGIC in content[:1024]  # the header may follow a few bytes of junk
    if ext in TEXT_EXTENSIONS:
        return b"\x00" not in content[:8192]  # binary content is not text
    return False


def read_limited(stream, name: str) -> bytes:
    """The whole upload in memory (needed for the scan), refused above MAX_UPLOAD_MB."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    content = stream.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"{name} is too large. The maximum is {get_settings().max_upload_mb} MB.")
    return content


def validate_upload(user_id: int, name: str, content: bytes) -> str:
    """Raises HTTPException when the file must not be accepted; returns the lower-case extension."""
    ext = Path(name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
    if not content:
        raise HTTPException(422, f"{name} is empty.")
    if get_settings().virus_scan == "on":
        try:
            clean = scan_file_content_for_virus(content)
        except RuntimeError as e:  # scanner not reachable: refuse, do not skip the scan
            log.error("virus scan failed: %s", e)
            raise HTTPException(503, "The file could not be scanned for viruses (scanner not reachable). Try again later.") from e
        if not clean:
            audit(user_id, f"Security Alert: Virus detected in {name}")
            raise HTTPException(422, "File rejected! Security threat detected.")
    if not content_matches_extension(ext, content):
        audit(user_id, f"Upload rejected, content does not match extension: {name}")
        raise HTTPException(422, f"{name} does not look like a valid {ext} file.")
    return ext
