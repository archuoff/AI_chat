"""Checks and bookkeeping for uploaded documents, in the order of the platform's upload_tabular_file (controller/common/common.py):
extension -> size -> virus scan (ClamAV) -> content matches the extension -> [our own parse] -> save -> tbl_files row -> audit log.

It is written for every format Engismart reads (xlsx, xlsm, csv, pdf, docx, pptx, txt, md); the platform's own functions only
know csv/xlsx/xls (upload_files, upload_tabular_file). It holds nothing Engismart-specific, so it can move to common.py unchanged
(ask the team; see docs/ENGISMART_CHANGES.md). The saving itself stays in documents.py: the file waits between "check" and "commit"."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from constants.constant import CONSTANT
from controller.common.common import application_logs, scan_file_content_for_virus
from models.model import models
from models.orm_models import File as FileRecord

from .config import get_settings
from .ingestion import SUPPORTED_EXTENSIONS

log = logging.getLogger(__name__)
ModuleName = "engismart"

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


def _audit(user_id: int, text: str) -> None:
    try:
        application_logs({"current_user": user_id, "date": datetime.now(), "module_name": ModuleName, "activity_text": text[:255]})
    except Exception:  # noqa: BLE001
        log.warning("could not write the audit log", exc_info=True)


def read_limited(stream, name: str) -> bytes:
    """The whole upload in memory (needed for the scan), refused above MAX_UPLOAD_MB."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    content = stream.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"{name} is too large. The maximum is {get_settings().max_upload_mb} MB.")
    return content


def check_upload(user_id: int, name: str, content: bytes) -> str:
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
            _audit(user_id, f"Security Alert: Virus detected in {name}")
            raise HTTPException(422, "File rejected! Security threat detected.")
    if not content_matches_extension(ext, content):
        _audit(user_id, f"Upload rejected, content does not match extension: {name}")
        raise HTTPException(422, f"{name} does not look like a valid {ext} file.")
    return ext


def record_upload(user_id: int, original_name: str, stored_path: Path, size_bytes: int) -> None:
    """One tbl_files row per accepted document (the platform's file list) and the audit line. Never fails the upload.
    tbl_files.file_type is a fixed list in the platform: `pdf` for PDFs, `file` for everything else; the real type stays in the name."""
    now = datetime.now()
    ext = Path(original_name).suffix.lower()
    file_type = "pdf" if ext == ".pdf" else "file"
    try:
        with models() as db:
            db.insert_record(FileRecord, {
                "datetime": now, "user_id": user_id, "filename": stored_path.name[:200], "original_filename": original_name[:255],
                "module": ModuleName, "file_type": file_type, "file_type_display_name": CONSTANT.get(file_type, "Document"),
                "file_size": round(size_bytes / 1_000_000, 4), "file_path": str(stored_path)[:255],
                "extra": str({"extension": ext}), "created_on": now,
            })
    except Exception:  # noqa: BLE001
        log.warning("could not record %s in tbl_files", original_name, exc_info=True)
    _audit(user_id, f"Successfully uploaded a {ext} file: {original_name}")
