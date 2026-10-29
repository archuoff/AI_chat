"""Request bodies."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from controller.engismart.config import get_settings


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
