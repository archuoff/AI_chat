"""Common intermediate format every parser produces, whatever the source file type."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ElementKind = Literal["text", "record"]


@dataclass
class Element:
    """One unit of content.

    text   -> prose (a PDF page, a Word section, a slide's text)
    record -> one table row with its header-path -> value fields (Excel / Word / PowerPoint tables)
    """

    kind: ElementKind
    text: str
    section: list[str] = field(default_factory=list)  # e.g. ["CCB"] or ["Requirements", "Positional Overview"]
    location: dict[str, Any] = field(default_factory=dict)  # e.g. {"sheet": "CCB", "row": 3} / {"page": 4}
    fields: dict[str, Any] | None = None  # records only, values kept exact
    title: str | None = None  # records only: the row's key value (e.g. vehicle name)


@dataclass
class RawImage:
    """A picture found in the document, with where it sits and the text around it (for describing it later)."""

    data: bytes
    ext: str  # png / jpeg / emf ... as stored in the file
    location: dict[str, Any]  # {"slide": 4} / {"page": 2} / {"sheet": "CCB", "row": 5, "cell": "D5"} / {"section": "..."}
    context: str = ""  # slide title + text, table row, section heading + paragraph


@dataclass
class ParsedDocument:
    file_name: str
    file_type: str
    elements: list[Element]
    stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    images: list[RawImage] = field(default_factory=list)
