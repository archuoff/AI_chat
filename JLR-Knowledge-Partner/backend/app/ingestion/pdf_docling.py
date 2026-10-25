"""PDF extraction with Docling (layout + table models), exported as chunking-ready JSON.

One file, three jobs:

1. ``convert(path)``            Docling conversion (models from a local folder: DOCLING_ARTIFACTS_PATH).
2. ``export_chunk_ready(doc)``  the DoclingDocument -> plain JSON the chunkers read:
     sections   heading tree (title, level, pages, block ids, children): the input of hierarchical chunking
     blocks     every paragraph / list item / caption / table / picture in reading order, with page, box,
                heading path and neighbours: the input of semantic chunking inside a section
     tables     header rows + rows + records (header -> value) + markdown
     pictures   page, box, caption, class, context text, optional image file
     checks     nothing silent: item counts, scanned pages, flat headings, empty tables
3. ``to_parsed_document(export)`` the same content as the app's ``ParsedDocument`` (text + record Elements with
   the heading path as ``section``, pictures as ``RawImage``) so chunker, store, VLM and chat keep working.

Run:  python -m app.ingestion.pdf_docling file.pdf --json out.json [--images folder]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from pathlib import Path
from typing import Any

from .models import Element, ParsedDocument, RawImage
from .tables import table_to_elements
from .utils import clean_text

SCHEMA = "pdf-chunk-ready-v1"
_NUMBERED = re.compile(r"^\s*((?:\d+\.)*\d+)[.)]?\s+\S")
_TEXT_TYPES = {"paragraph", "list_item", "caption", "footnote", "code", "formula"}
_FURNITURE = {"page_header", "page_footer"}


# ------------------------------------------------------------------ 1. conversion
def convert(path: str | Path) -> tuple[Any, dict[str, Any], Any]:
    """Run Docling on one PDF -> (DoclingDocument, configuration used, conversion result)."""
    path = Path(path)
    with path.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise ValueError(f"Not a PDF: {path}")
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise RuntimeError("Docling is not installed in this Python environment") from exc

    opts = PdfPipelineOptions()
    opts.do_ocr = os.environ.get("DOCLING_OCR", "1") != "0"
    opts.do_table_structure = True
    opts.table_structure_options.mode = (TableFormerMode.FAST if os.environ.get("DOCLING_TABLE_MODE", "accurate") == "fast"
                                         else TableFormerMode.ACCURATE)
    opts.do_code_enrichment = os.environ.get("DOCLING_CODE_FORMULA", "0") == "1"  # extra models + time; off by default
    opts.do_formula_enrichment = opts.do_code_enrichment
    opts.generate_picture_images = True
    opts.enable_remote_services = False
    config: dict[str, Any] = {"engine": "docling", "ocr": opts.do_ocr, "table_mode": opts.table_structure_options.mode.value,
                              "code_formula": opts.do_code_enrichment}
    try:  # these presets depend on the Docling version; a missing one must not stop the conversion
        from docling.datamodel.pipeline_options import LayoutObjectDetectionOptions
        opts.layout_options = LayoutObjectDetectionOptions.from_preset("layout_heron_default")
        config["layout_model"] = "layout_heron_default"
    except Exception as exc:  # noqa: BLE001
        config["layout_model"] = f"default ({type(exc).__name__})"
    try:
        from docling.datamodel.picture_classification_options import DocumentPictureClassifierOptions
        opts.picture_classification_options = DocumentPictureClassifierOptions.from_preset("document_figure_classifier_v2")
        opts.do_picture_classification = True
        config["picture_classifier"] = "document_figure_classifier_v2"
    except Exception as exc:  # noqa: BLE001
        config["picture_classifier"] = f"off ({type(exc).__name__})"
    artifacts = os.environ.get("DOCLING_ARTIFACTS_PATH", "").strip()
    if artifacts:
        if not Path(artifacts).is_dir():
            raise ValueError(f"DOCLING_ARTIFACTS_PATH is not a folder: {artifacts}")
        opts.artifacts_path = artifacts
    config["artifacts_path"] = artifacts or None
    try:
        import importlib.metadata as md
        config["docling_version"] = md.version("docling")
    except Exception:  # noqa: BLE001
        config["docling_version"] = "unknown"
    result = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}).convert(
        str(path), raises_on_error=False)
    if getattr(result, "document", None) is None:
        raise RuntimeError(f"Docling returned no document ({getattr(result, 'status', '?')}): "
                           f"{[str(e)[:200] for e in (getattr(result, 'errors', None) or [])][:3]}")
    return result.document, config, result


# ------------------------------------------------------------------ 2. export
def _label(item: Any) -> str:
    return str(getattr(getattr(item, "label", None), "value", getattr(item, "label", "")))


def _where(doc: Any, item: Any) -> tuple[int | None, list[float] | None]:
    """Page number + box as fractions of the page (left, top, right, bottom; origin top-left)."""
    prov = (getattr(item, "prov", None) or [None])[0]
    if prov is None:
        return None, None
    page = doc.pages.get(prov.page_no) if getattr(doc, "pages", None) else None
    box = None
    if page is not None and getattr(page, "size", None) and page.size.height and page.size.width:
        b = prov.bbox.to_top_left_origin(page_height=page.size.height)
        box = [round(b.l / page.size.width, 4), round(b.t / page.size.height, 4),
               round(b.r / page.size.width, 4), round(b.b / page.size.height, 4)]
    return prov.page_no, box


def _numbered_level(title: str) -> int | None:
    m = _NUMBERED.match(title)
    return m.group(1).count(".") + 1 if m else None


def _picture_class(item: Any) -> tuple[str | None, float | None]:
    """Docling stores the figure class in `meta.classification` (new) or `annotations` (old)."""
    meta = getattr(item, "meta", None)
    cls = getattr(meta, "classification", None) if meta is not None else None
    for pred in (getattr(cls, "predictions", None) or []):
        return getattr(pred, "class_name", None), getattr(pred, "confidence", None)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        annotations = list(getattr(item, "annotations", None) or [])
    for ann in annotations:
        classes = getattr(ann, "predicted_classes", None)
        if classes:
            return getattr(classes[0], "class_name", None), getattr(classes[0], "confidence", None)
    return None, None


def _table(doc: Any, item: Any) -> dict[str, Any]:
    grid = [[clean_text(getattr(c, "text", "") or "") for c in row] for row in (getattr(item.data, "grid", None) or [])]
    header_rows = 0
    for row in (getattr(item.data, "grid", None) or []):
        if row and all(getattr(c, "column_header", False) for c in row if getattr(c, "text", "")) and any(getattr(c, "text", "") for c in row):
            header_rows += 1
        else:
            break
    heads: list[str] = []
    if header_rows:  # multi-level headers joined "Parent > Child"
        for col in range(len(grid[0])):
            parts: list[str] = []
            for r in range(header_rows):
                if grid[r][col] and (not parts or parts[-1] != grid[r][col]):
                    parts.append(grid[r][col])
            heads.append(" > ".join(parts) or f"Column {col + 1}")
    records = []
    if heads:
        for row in grid[header_rows:]:
            rec = {h: v for h, v in zip(heads, row) if v}
            if rec:
                records.append(rec)
    try:
        md = item.export_to_markdown(doc)
    except Exception:  # noqa: BLE001
        md = ""
    return {"rows": grid, "header_rows": header_rows, "headers": heads, "records": records,
            "n_rows": len(grid), "n_cols": len(grid[0]) if grid else 0, "markdown": md,
            "caption": clean_text(item.caption_text(doc) or "") if hasattr(item, "caption_text") else ""}


def export_chunk_ready(doc: Any, file_name: str = "", *, images_dir: str | Path | None = None, config: dict | None = None,
                       conversion_status: Any = None, source_sha256: str | None = None) -> dict[str, Any]:
    """DoclingDocument -> chunking-ready JSON (see module docstring)."""
    images_dir = Path(images_dir) if images_dir else None
    if images_dir:
        images_dir.mkdir(parents=True, exist_ok=True)
    blocks: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []  # open sections, outermost first
    tables: list[dict[str, Any]] = []
    pictures: list[dict[str, Any]] = []
    root = {"id": "s0", "title": file_name or "document", "level": 0, "page_start": None, "page_end": None,
            "block_ids": [], "children": [], "parent": None}
    sections.append(root)

    def current() -> dict[str, Any]:
        return stack[-1] if stack else root

    def path() -> list[str]:
        return [s["title"] for s in stack]

    def touch(section: dict, page: int | None):
        if page is not None:
            section["page_start"] = page if section["page_start"] is None else min(section["page_start"], page)
            section["page_end"] = page if section["page_end"] is None else max(section["page_end"], page)

    # Docling often reports every PDF heading as level 1: use the numbering ("2.3.1" = depth 3) when most headings have it
    raw = [(clean_text(getattr(i, "text", "") or ""), int(getattr(i, "level", 1) or 1)) for i, _ in doc.iterate_items()
           if _label(i) == "section_header"]
    flat = len(raw) > 3 and len({lv for _, lv in raw}) <= 1
    use_numbers = flat and sum(_numbered_level(t) is not None for t, _ in raw) >= 0.5 * len(raw)

    n_text_items = n_furniture = 0
    for item, _depth in doc.iterate_items():
        kind = _label(item)
        page, box = _where(doc, item)
        if kind in _FURNITURE:
            n_furniture += 1
            continue
        block: dict[str, Any] = {"id": f"b{len(blocks) + 1:05d}", "page": page, "bbox": box}
        if kind in ("section_header", "title"):
            n_text_items += 1
            title = clean_text(getattr(item, "text", "") or "")
            if not title:
                continue
            level = 1 if kind == "title" else int(getattr(item, "level", 1) or 1)
            if use_numbers and kind == "section_header":
                level = _numbered_level(title) or level
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            sec = {"id": f"s{len(sections)}", "title": title, "level": level, "page_start": page, "page_end": page,
                   "block_ids": [], "children": [], "parent": current()["id"]}
            current()["children"].append(sec["id"])
            sections.append(sec)
            stack.append(sec)
            block.update(type="heading", level=level, text=title)
        elif kind == "table":
            t = _table(doc, item)
            t.update(id=f"t{len(tables) + 1}", block_id=block["id"], page=page, bbox=box, heading_path=path())
            tables.append(t)
            block.update(type="table", table_id=t["id"], text=t["markdown"] or t["caption"])
        elif kind in ("picture", "chart"):
            cls, conf = _picture_class(item)
            pic = {"id": f"p{len(pictures) + 1}", "block_id": block["id"], "page": page, "bbox": box, "kind": kind,
                   "caption": clean_text(item.caption_text(doc) or "") if hasattr(item, "caption_text") else "",
                   "class": cls, "class_confidence": conf, "heading_path": path(), "image_file": None, "context": ""}
            if images_dir is not None:
                try:
                    img = item.get_image(doc)
                    if img is not None:
                        pic["image_file"] = f"{pic['id']}_page{page}.png"
                        img.save(images_dir / pic["image_file"], format="PNG")
                except Exception:  # noqa: BLE001 - the picture is still listed; the check below counts it
                    pass
            pictures.append(pic)
            block.update(type="picture", picture_id=pic["id"], text=pic["caption"])
        elif kind in ("text", "paragraph", "list_item", "caption", "footnote", "code", "formula", "reference"):
            n_text_items += 1
            text = clean_text(getattr(item, "text", "") or "")
            if not text:
                continue
            block.update(type={"text": "paragraph", "reference": "paragraph"}.get(kind, kind), text=text)
            if kind == "list_item":
                block["marker"] = getattr(item, "marker", None)
        else:  # form fields, key-value regions, checkboxes ... keep the text, never drop silently
            n_text_items += 1
            text = clean_text(getattr(item, "text", "") or "")
            if not text:
                continue
            block.update(type="paragraph", text=text, docling_label=kind)
        sec = current()
        block.update(section_id=sec["id"], heading_path=path(), char_count=len(block.get("text", "")))
        if blocks:
            block["prev"] = blocks[-1]["id"]
            blocks[-1]["next"] = block["id"]
        blocks.append(block)
        sec["block_ids"].append(block["id"])
        touch(sec, page)

    for pic in pictures:  # context for the picture description: the text just before and after it
        i = next(k for k, b in enumerate(blocks) if b["id"] == pic["block_id"])
        before = [b["text"] for b in blocks[max(0, i - 3):i] if b["type"] in _TEXT_TYPES | {"heading"} and b.get("text")]
        after = [b["text"] for b in blocks[i + 1:i + 3] if b["type"] in _TEXT_TYPES and b.get("text")]
        pic["context"] = clean_text("\n".join([*pic["heading_path"][-1:], *before[-2:], *after[:1]]))[:900]

    # tables split by a page break: same width, top of the next page, nothing but the table in between
    for a, b in zip(tables, tables[1:]):
        if (a["n_cols"] == b["n_cols"] and a["page"] and b["page"] == a["page"] + 1 and (b["bbox"] or [0, 1])[1] < 0.2
                and int(b["block_id"][1:]) == int(a["block_id"][1:]) + 1):
            b["continues"] = a["id"]

    for sec in sections:
        sec["char_count"] = sum(blocks[int(i[1:]) - 1]["char_count"] for i in sec["block_ids"])
        sec["block_count"] = len(sec["block_ids"])

    # headings: Docling often reports every PDF heading as level 1. Numbered headings ("2.3.1") give the real depth.
    headings = [s for s in sections[1:]]
    levels_flat = len({s["level"] for s in headings}) <= 1 and len(headings) > 3  # still flat after the numbering fix
    page_count = len(getattr(doc, "pages", {}) or {})
    pages_with_text = {b["page"] for b in blocks if b.get("page") and b["type"] != "picture" and b.get("text")}
    empty_pages = [p for p in range(1, page_count + 1) if p not in pages_with_text]
    exported_text = sum(1 for b in blocks if b["type"] not in ("table", "picture"))
    checks = {
        "page_count": page_count, "pages_without_text": empty_pages,
        "text_items_seen": n_text_items, "text_blocks_exported": exported_text, "furniture_removed": n_furniture,
        "tables": len(tables), "tables_without_rows": [t["id"] for t in tables if not t["n_rows"]],
        "tables_without_header": [t["id"] for t in tables if t["n_rows"] and not t["header_rows"]],
        "pictures": len(pictures), "pictures_without_image": [p["id"] for p in pictures if images_dir and not p["image_file"]],
        "headings": len(headings), "heading_levels_flat": levels_flat, "heading_levels_from_numbering": use_numbers,
        "conversion_status": str(getattr(conversion_status, "value", conversion_status)) if conversion_status is not None else None,
        "problems": [],
    }
    if empty_pages:
        checks["problems"].append(f"{len(empty_pages)} page(s) without text (scanned or image only): pages {empty_pages[:20]}")
    if levels_flat:
        checks["problems"].append("all headings share one level and have no numbering; the section tree is flat")
    if not blocks:
        checks["problems"].append("no content extracted")
    if checks["tables_without_rows"]:
        checks["problems"].append(f"{len(checks['tables_without_rows'])} table(s) without rows")
    if checks["conversion_status"] and "success" not in checks["conversion_status"].lower():
        checks["problems"].append(f"Docling status: {checks['conversion_status']}")
    return {"schema": SCHEMA, "file_name": file_name, "source_sha256": source_sha256, "configuration": config or {},
            "sections": sections, "blocks": blocks, "tables": tables, "pictures": pictures, "checks": checks}


# ------------------------------------------------------------------ 3. adapter to the app's model
def _image_bytes(folder: Path | None, name: str | None) -> bytes | None:
    if folder is None or not name:
        return None
    try:
        return (folder / name).read_bytes()
    except OSError:
        return None


def to_parsed_document(export: dict[str, Any], *, images_dir: str | Path | None = None) -> ParsedDocument:
    """Same content as the old pypdf parser returned, but with headings, real tables and positioned pictures."""
    images_dir = Path(images_dir) if images_dir else None
    elements: list[Element] = []
    run: list[dict] = []

    def flush():
        if not run:
            return
        pages = sorted({b["page"] for b in run if b.get("page")})
        text = "\n".join(b["text"] for b in run)
        elements.append(Element("text", text, [s for s in run[0]["heading_path"]], {"page": pages[0] if pages else None,
                                "pages": pages, "blocks": [b["id"] for b in run]}))
        run.clear()

    tables = {t["id"]: t for t in export["tables"]}
    table_no = 0
    for b in export["blocks"]:
        kind = b["type"]
        if kind == "heading":
            flush()
        elif kind == "table":
            flush()
            t = tables[b["table_id"]]
            table_no += 1
            rows = [t["headers"], *[[r.get(h, "") for h in t["headers"]] for r in t["records"]]] if t["headers"] else t["rows"]
            elements.extend(table_to_elements(rows, b["heading_path"], {"page": b["page"], "table_id": t["id"]}, table_no))
            if t["caption"]:
                elements.append(Element("text", t["caption"], b["heading_path"], {"page": b["page"]}))
        elif kind == "picture":
            if b.get("text"):
                run.append(b)
        elif b.get("text"):
            if run and run[-1].get("section_id") != b.get("section_id"):
                flush()
            run.append(b)
    flush()
    images = []
    for p in export["pictures"]:
        data = _image_bytes(images_dir, p.get("image_file"))
        if data:
            images.append(RawImage(data, "png", {"page": p["page"], "bbox": p["bbox"], "picture": p["id"]}, p["context"]))
    checks = export["checks"]
    stats = {"pages": checks["page_count"], "tables": checks["tables"], "pictures": checks["pictures"],
             "headings": checks["headings"], "engine": "docling", "removed_header_lines": checks["furniture_removed"]}
    return ParsedDocument(export["file_name"], "pdf", elements, stats, list(checks["problems"]), images)


def parse_pdf_docling(path: str | Path, images_dir: str | Path | None = None) -> ParsedDocument:
    path = Path(path)
    import tempfile

    doc, config, result = convert(path)
    own = images_dir is None
    folder = Path(tempfile.mkdtemp(prefix="pdfimg_")) if own else Path(images_dir)
    try:
        export = export_chunk_ready(doc, path.name, images_dir=folder, config=config, conversion_status=getattr(result, "status", None),
                                    source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        return to_parsed_document(export, images_dir=folder)
    finally:
        if own:
            import shutil
            shutil.rmtree(folder, ignore_errors=True)


# ------------------------------------------------------------------ CLI
def _main() -> int:
    ap = argparse.ArgumentParser(description="Extract one PDF with Docling and write chunking-ready JSON")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--json", type=Path, default=None, help="where to write the JSON (default: <pdf>.chunks.json)")
    ap.add_argument("--images", type=Path, default=None, help="folder for the extracted pictures")
    args = ap.parse_args()
    doc, config, result = convert(args.pdf)
    export = export_chunk_ready(doc, args.pdf.name, images_dir=args.images, config=config,
                                conversion_status=getattr(result, "status", None),
                                source_sha256=hashlib.sha256(args.pdf.read_bytes()).hexdigest())
    out = args.json or args.pdf.with_suffix(".chunks.json")
    out.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
    c = export["checks"]
    print(f"{out}: {len(export['sections']) - 1} headings, {len(export['blocks'])} blocks, {c['tables']} tables, "
          f"{c['pictures']} pictures, {len(c['problems'])} problem(s)")
    for p in c["problems"]:
        print("  -", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
