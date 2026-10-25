"""Deterministic noise removal for PDF, Word and PowerPoint (no AI, same result every time).

A picture or a table row that shows up on `clean_repeat_pages` (default 4) or more pages / slides is a logo, watermark
or header / footer table: noise.
Text: page numbers, separator lines, table-of-contents dot leaders, confidentiality / boilerplate lines and lines that
repeat on many pages or slides (running headers and footers, document ids, "Slide 3") are removed.
Pictures: icons, thin lines and dividers, blank images, logos / watermarks repeated across pages or slides and exact
duplicates are dropped, so the vision model is only asked about pictures that carry information.

Nothing is dropped silently: `doc.stats["cleaning"]` lists every rule with its count and a few examples.
Table rows (`record` elements) are never touched, and Excel is not cleaned here.
"""
from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter, defaultdict
from typing import Any

from ..config import get_settings
from .models import Element, ParsedDocument, RawImage

CLEAN_TYPES = {"pdf", "docx", "pptx"}
MIN_UNITS = 4  # pages / slides needed before "repeats on many of them" means anything
REPEAT_SHARE = 0.4
MIN_REPEAT_LEN = 6  # shorter lines ("Yes", "mm") are content more often than noise
MAX_REPEAT_LEN = 120
MIN_SIDE_PX = 48
MIN_AREA_PX = 3000
MAX_ASPECT = 12.0  # divider lines / banners
BLANK_STDDEV = 3.0
EXAMPLES = 10

_PAGE_LABELLED = re.compile(r"^(?:(?:page|slide|p\.?|sheet)\s*[-–—]?\s*\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?|\d{1,4}\s*(?:of|/)\s*\d{1,4}|[-–—]\s*\d{1,4}\s*[-–—])$", re.IGNORECASE)
_BARE_NUMBER = re.compile(r"^\d{1,4}$")
_SEPARATOR = re.compile(r"^[\s_\-–—=~*.·•|/\\]{4,}$")
_DOT_LEADER = re.compile(r"\.{4,}\s*\d{1,4}\s*$|(?:\s\.){4,}\s*\d{1,4}\s*$")
_BOILERPLATE = re.compile(
    r"^(?:(?:strictly |company |internal |jlr |proprietary )?confidential(?: and proprietary)?|"
    r"uncontrolled (?:when|if) printed|printed copies? (?:are|is) uncontrolled|all rights reserved|"
    r"click to edit master (?:title|text|subtitle) styles?|click to add (?:title|text|notes)|"
    r"(?:©|\(c\)|copyright)\s*.*|draft|do not copy)\.?$",
    re.IGNORECASE,
)
_PAGE_MARK = re.compile(r"\b(?:page|slide|sheet|p\.)\s*\d+(?:\s*(?:of|/)\s*\d+)?|\b\d+\s*(?:of|/)\s*\d+\b", re.IGNORECASE)


def _norm(line: str) -> str:
    """Case / spacing folded; only a page counter ("Page 3 of 9", "3/9") is folded, so a header that carries the page
    number repeats, while two lines that merely differ in a value ("Step 3", "Step 4") stay different."""
    return _PAGE_MARK.sub("#", " ".join(line.lower().split()))


def _unit(el_or_img: Any) -> Any:
    loc = el_or_img.location
    return loc.get("page") if loc.get("page") is not None else loc.get("slide")


def _rule(line: str, file_type: str, unit: Any) -> str | None:
    s = line.strip()
    if _PAGE_LABELLED.match(s):
        return "page_number"
    if _BARE_NUMBER.match(s) and (file_type == "pdf" or (isinstance(unit, int) and int(s) == unit)):
        return "page_number"  # a lone number: a page number in a PDF; in Word / PowerPoint only when it is the slide / page number
    if _SEPARATOR.match(s):
        return "separator"
    if _DOT_LEADER.search(s):
        return "toc_leader"
    if _BOILERPLATE.match(s):
        return "boilerplate"
    return None


def clean_text_elements(elements: list[Element], file_type: str = "pdf") -> tuple[list[Element], dict[str, int], list[str], int]:
    """-> (kept elements, removed lines per rule, examples, dropped element count)"""
    counts: Counter = Counter()
    examples: list[str] = []

    def note(rule: str, line: str):
        counts[rule] += 1
        if len(examples) < EXAMPLES and line.strip() not in examples:
            examples.append(f"{rule}: {line.strip()[:80]}")

    need_pages = max(2, get_settings().clean_repeat_pages)
    row_pages: dict[str, set] = defaultdict(set)  # table rows (header / footer tables) repeated on many pages / slides
    for e in elements:
        if e.kind == "record" and _unit(e) is not None:
            row_pages[_norm(e.text)].add(_unit(e))
    repeated_rows = {k for k, pages in row_pages.items() if len(pages) >= need_pages}

    units = {_unit(e) for e in elements if e.kind == "text" and _unit(e) is not None}
    repeated: set[str] = set()
    if len(units) >= MIN_UNITS:  # lines that appear on many pages / slides
        seen: dict[str, set] = defaultdict(set)
        for e in elements:
            u = _unit(e)
            if e.kind != "text" or u is None:
                continue
            for line in e.text.split("\n"):
                s = line.strip()
                if MIN_REPEAT_LEN <= len(s) <= MAX_REPEAT_LEN:
                    seen[_norm(s)].add(u)
        need = max(3, math.ceil(REPEAT_SHARE * len(units)))
        repeated = {k for k, pages in seen.items() if len(pages) >= need}

    kept: list[Element] = []
    dropped = 0
    for e in elements:
        if e.kind == "record" and _unit(e) is not None and _norm(e.text) in repeated_rows:
            note("repeated_table_row", e.text.split("\n")[0])
            dropped += 1
            continue
        if e.kind != "text":
            kept.append(e)
            continue
        lines = []
        for line in e.text.split("\n"):
            rule = _rule(line, file_type, _unit(e)) if line.strip() else None
            if rule is None and line.strip() and _norm(line.strip()) in repeated:
                rule = "repeated"
            if rule:
                note(rule, line)
            else:
                lines.append(line)
        text = "\n".join(lines).strip()
        if len(text) < 3:
            if e.text.strip():
                dropped += 1
            continue
        e.text = text
        kept.append(e)
    return kept, dict(counts), examples, dropped


def _measure(img: RawImage) -> tuple[int, int, float | None] | None:
    """(width, height, grey-level spread) or None when the format cannot be decoded (emf / wmf / svg ...)."""
    try:
        from PIL import Image, ImageStat

        with Image.open(io.BytesIO(img.data)) as im:
            w, h = im.size
            small = im.convert("L").resize((48, 48))
            return w, h, float(ImageStat.Stat(small).stddev[0])
    except Exception:  # noqa: BLE001 - unknown format: keep the picture, it just cannot be judged by size
        return None


def filter_images(images: list[RawImage], n_units: int) -> tuple[list[RawImage], dict[str, int]]:
    dropped: Counter = Counter()
    digests = [hashlib.sha256(i.data).hexdigest() for i in images]
    places: dict[str, set] = defaultdict(set)
    for img, d in zip(images, digests):
        places[d].add(_unit(img) if _unit(img) is not None else id(img))
    need = max(2, get_settings().clean_repeat_pages)  # the same picture on this many pages / slides: logo, watermark, background
    kept: list[RawImage] = []
    seen_here: set[tuple] = set()
    for img, d in zip(images, digests):
        reason = None
        m = _measure(img)
        if len(places[d]) >= need:
            reason = "repeated"  # logo / watermark / background on many pages or slides
        elif m is not None:
            w, h, spread = m
            if max(w, h) / max(1, min(w, h)) > MAX_ASPECT:
                reason = "extreme_aspect"  # divider lines, banners
            elif min(w, h) < MIN_SIDE_PX or w * h < MIN_AREA_PX:
                reason = "too_small"  # icons, bullets
            elif spread is not None and spread < BLANK_STDDEV:
                reason = "blank"
        if reason is None:
            key = (d, _unit(img), tuple(sorted((k, str(v)) for k, v in img.location.items() if k != "bbox")))
            if key in seen_here:
                reason = "duplicate"
            seen_here.add(key)
        if reason:
            dropped[reason] += 1
        else:
            kept.append(img)
    return kept, dict(dropped)


def clean_document(doc: ParsedDocument) -> ParsedDocument:
    """Apply every rule in place and report what was removed in `doc.stats["cleaning"]`."""
    if doc.file_type not in CLEAN_TYPES:
        return doc
    elements, lines, examples, dropped = clean_text_elements(doc.elements, doc.file_type)
    n_units = len({_unit(e) for e in doc.elements if _unit(e) is not None} | {_unit(i) for i in doc.images if _unit(i) is not None})
    images, img_dropped = filter_images(doc.images, n_units)
    doc.elements, doc.images = elements, images
    doc.stats["cleaning"] = {"lines_removed": lines, "elements_dropped": dropped, "images_dropped": img_dropped,
                             "images_kept": len(images), "examples": examples}
    return doc
