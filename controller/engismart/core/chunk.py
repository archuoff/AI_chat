"""The unit that is embedded and stored in Qdrant (what the ingestion produces and the search returns)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    id: str
    doc_id: str
    index: int
    kind: str
    text: str
    context: str
    section: list[str]
    location: dict[str, Any]
    fields: dict[str, Any] | None = None
    title: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    breadcrumb: list[str] = field(default_factory=list)  # the path to this chunk: file > sheet / headings > unit > row title
    relations: dict[str, Any] = field(default_factory=dict)  # group, prev / next chunk in that group, parent, row_key (pictures)

    @property
    def embed_text(self) -> str:
        return f"{self.context}\n{self.text}"
