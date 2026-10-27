"""Picture catalog: files on disk + one database row per picture, and their search chunks."""
from __future__ import annotations

import hashlib
import io
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from ..config import DATA_DIR
from ..db import Base, SessionLocal, init_db, iso, utcnow
from ..ingestion.chunker import Chunk
from ..ingestion.models import RawImage

log = logging.getLogger(__name__)

IMAGE_DIR = DATA_DIR / "images"
FULL_PX = 1600  # long side of the stored copy (what the vision model receives)
THUMB_PX = 360
MIN_SIDE = 32  # smaller than this: icon / bullet
MIN_AREA = 48 * 48  # small in-cell part photos (~110x75) are real content
MAX_ASPECT = 8  # wider/taller than 8:1: line, banner, divider
REPEATED = 4  # default: the same picture on 4+ places of a PDF / Word / PowerPoint file = logo / template decoration
_NS = uuid.UUID("2b6e4f0a-7c1d-4e8b-9a35-5d0c8f1e2a77")

STATUSES = ("waiting", "described", "skipped", "unsupported", "failed")


class DocImage(Base):
    __tablename__ = "tbl_engismart_image"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    location: Mapped[dict] = mapped_column(JSON, default=dict)
    context: Mapped[str] = mapped_column(Text, default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="waiting", index=True)
    reason: Mapped[str] = mapped_column(String(160), default="")  # why skipped / unsupported / failed
    manual: Mapped[bool] = mapped_column(Boolean, default=False)  # status set by a person: kept on re-processing
    description: Mapped[str] = mapped_column(Text, default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    described_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def _db():
    """Session factory; init_db() has applied the migrations (the picture table is part of the baseline revision)."""
    init_db()
    return SessionLocal()


def image_dir(doc_id: str) -> Path:
    return IMAGE_DIR / doc_id


def file_path(img: DocImage, thumb: bool = False) -> Path:
    return image_dir(img.doc_id) / f"{img.id}{'_t' if thumb else ''}.jpg"


def public(img: DocImage) -> dict[str, Any]:
    return {
        "id": img.id, "doc_id": img.doc_id, "position": img.position, "location": img.location, "context": img.context,
        "width": img.width, "height": img.height, "status": img.status, "reason": img.reason, "manual": img.manual,
        "description": img.description, "input_tokens": img.input_tokens, "output_tokens": img.output_tokens,
        "described_at": iso(img.described_at),
    }


# ------------------------------------------------------------------ sync at ingest
def _to_rgb(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")  # transparent diagrams -> white paper, not black
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


def _save(im: Image.Image, path: Path, px: int) -> None:
    im = im.copy()
    im.thumbnail((px, px), Image.Resampling.LANCZOS)
    im.save(path, "JPEG", quality=85, optimize=True)


def _repeat_limit() -> int:
    from ..config import get_settings

    return max(2, get_settings().clean_repeat_pages)


def sync(doc_id: str, images: list[RawImage]) -> dict[str, int]:
    """Replace the document's pictures with the freshly extracted ones. Descriptions and manual
    decisions are kept for pictures that did not change (same bytes), so re-processing never pays twice."""
    with _db() as db:
        old = {i.id: i for i in db.scalars(select(DocImage).where(DocImage.doc_id == doc_id))}
    folder = image_dir(doc_id)
    folder.mkdir(parents=True, exist_ok=True)

    shas = [hashlib.sha256(r.data).hexdigest() for r in images]
    counts: dict[str, int] = {}
    for h in shas:
        counts[h] = counts.get(h, 0) + 1
    seen: dict[str, int] = {}
    rows: list[DocImage] = []
    for pos, (raw, sha) in enumerate(zip(images, shas, strict=False)):
        n = seen[sha] = seen.get(sha, 0) + 1
        img = DocImage(id=str(uuid.uuid5(_NS, f"{doc_id}:{sha}:{n}")), doc_id=doc_id, position=pos, sha256=sha,
                       location=raw.location, context=raw.context, status="waiting", reason="")
        try:
            with Image.open(io.BytesIO(raw.data)) as im:
                im.load()
                img.width, img.height = im.size
                rgb = _to_rgb(im)
        except (UnidentifiedImageError, OSError, ValueError) as e:
            img.status, img.reason = "unsupported", f"{raw.ext.upper()} picture could not be read ({type(e).__name__})"
            rows.append(img)
            continue
        w, h = img.width, img.height
        if min(w, h) < MIN_SIDE or w * h < MIN_AREA:
            img.status, img.reason = "skipped", "Too small (icon or bullet)"
        elif max(w, h) / max(min(w, h), 1) > MAX_ASPECT:
            img.status, img.reason = "skipped", "Line or banner"
        elif counts[sha] >= _repeat_limit() and "sheet" not in raw.location:
            # (not for Excel: the same car photo in several rows is real content, it is described once and shared)
            img.status, img.reason = "skipped", f"Repeated {counts[sha]}× in this document (logo or template)"
        elif n > 1:
            img.status, img.reason = "skipped", "Duplicate of an earlier picture"
        # ids come from the picture bytes: an unchanged picture keeps its id, files and description
        if not (folder / f"{img.id}_t.jpg").exists():
            _save(rgb, folder / f"{img.id}.jpg", FULL_PX)
            _save(rgb, folder / f"{img.id}_t.jpg", THUMB_PX)
        prev = old.get(img.id)
        if prev is not None and prev.status != "unsupported":
            if prev.status == "described":
                img.status, img.reason, img.description = "described", "", prev.description
                img.input_tokens, img.output_tokens, img.described_at = prev.input_tokens, prev.output_tokens, prev.described_at
            elif prev.manual:
                img.status, img.reason, img.manual = prev.status, prev.reason, True
        rows.append(img)

    with _db() as db:
        db.execute(delete(DocImage).where(DocImage.doc_id == doc_id))
        db.add_all(rows)
        db.commit()
    keep = {f"{r.id}{suffix}.jpg" for r in rows for suffix in ("", "_t")}
    for f in folder.iterdir():  # pictures no longer in the document
        if f.name not in keep:
            f.unlink(missing_ok=True)
    return summary(doc_id)


def delete_document(doc_id: str) -> None:
    with _db() as db:
        db.execute(delete(DocImage).where(DocImage.doc_id == doc_id))
        db.commit()
    shutil.rmtree(image_dir(doc_id), ignore_errors=True)


# ------------------------------------------------------------------ queries
def list_images(doc_id: str) -> list[DocImage]:
    with _db() as db:
        return list(db.scalars(select(DocImage).where(DocImage.doc_id == doc_id).order_by(DocImage.position)))


def get_image(image_id: str) -> DocImage | None:
    with _db() as db:
        return db.get(DocImage, image_id)


def summary(doc_id: str | None = None) -> dict[str, int]:
    """{"total", "waiting", "described", "skipped", "unsupported", "failed"} for one document or all."""
    q = select(DocImage.status, func.count()).group_by(DocImage.status)
    if doc_id:
        q = q.where(DocImage.doc_id == doc_id)
    with _db() as db:
        counts = dict(db.execute(q).all())
    out = {s: int(counts.get(s, 0)) for s in STATUSES}
    out["total"] = sum(out.values())
    return out


def summaries_by_document() -> dict[str, dict[str, int]]:
    with _db() as db:
        rows = db.execute(select(DocImage.doc_id, DocImage.status, func.count()).group_by(DocImage.doc_id, DocImage.status)).all()
    out: dict[str, dict[str, int]] = {}
    for doc_id, status, n in rows:
        d = out.setdefault(doc_id, {s: 0 for s in STATUSES} | {"total": 0})
        d[status] = int(n)
        d["total"] += int(n)
    return out


def waiting(doc_ids: list[str] | None = None, image_ids: list[str] | None = None) -> list[DocImage]:
    q = select(DocImage).where(DocImage.status.in_(("waiting", "failed"))).order_by(DocImage.doc_id, DocImage.position)
    if doc_ids:
        q = q.where(DocImage.doc_id.in_(doc_ids))
    if image_ids:
        q = q.where(DocImage.id.in_(image_ids))
    with _db() as db:
        return list(db.scalars(q))


def set_included(image_id: str, included: bool) -> DocImage:
    """A person decides: include a skipped picture for describing, or skip one (saves vision tokens)."""
    with _db() as db:
        img = db.get(DocImage, image_id)
        if img is None:
            raise KeyError(image_id)
        if img.status == "unsupported":
            raise ValueError("This picture format cannot be read")
        if included and img.status == "skipped":
            img.status, img.reason, img.manual = "waiting", "", True
        elif not included and img.status in ("waiting", "failed"):
            img.status, img.reason, img.manual = "skipped", "Skipped by you", True
        db.commit()
        return img


def share_with_duplicates(image_id: str) -> int:
    """The same picture used in several places (e.g. one car photo in several rows) is described once: the other copies
    get the same description at no cost, and each gets its own search chunk tied to its own row. Returns how many."""
    with _db() as db:
        src = db.get(DocImage, image_id)
        if src is None or src.status != "described":
            return 0
        twins = list(db.scalars(select(DocImage).where(DocImage.doc_id == src.doc_id, DocImage.sha256 == src.sha256,
                                                       DocImage.id != src.id, DocImage.status == "skipped",
                                                       DocImage.manual == False)))  # noqa: E712 - SQL comparison
        n = 0
        for t in twins:
            if t.reason.startswith("Duplicate"):
                t.status, t.reason, t.description, t.described_at = "described", "", src.description, utcnow()
                n += 1
        db.commit()
        return n


def record_result(image_id: str, *, description: str = "", error: str = "", decorative: bool = False,
                  usage: dict | None = None, note: str = "") -> None:
    u = usage or {}
    with _db() as db:
        img = db.get(DocImage, image_id)
        if img is None:
            return
        img.input_tokens += int(u.get("input_tokens", 0))
        img.output_tokens += int(u.get("output_tokens", 0))
        if error:
            img.status, img.reason = "failed", error[:160]
        elif decorative:
            img.status, img.reason, img.description = "skipped", "Decorative (judged by the vision model)", ""
        else:
            img.status, img.reason, img.description, img.described_at = "described", note[:160], description, utcnow()
        db.commit()


# ------------------------------------------------------------------ search chunks
def _where(loc: dict[str, Any]) -> str:
    if "slide" in loc:
        return f"slide {loc['slide']}"
    if "page" in loc:
        return f"page {loc['page']}"
    if "sheet" in loc:
        return f"{loc['sheet']}{' ' + loc['cell'] if loc.get('cell') else ''}"
    return loc.get("section") or ""


def image_chunks(doc_id: str, file_name: str, start_index: int) -> list[Chunk]:
    """One chunk per described picture: its description plus the text around it."""
    chunks = []
    for img in list_images(doc_id):
        if img.status != "described" or not img.description:
            continue
        where = _where(img.location)
        context = f"{file_name} › Picture" + (f" ({where})" if where else "")
        near = img.context.strip()
        text = f"Picture: {img.description}" + (f"\nShown with: {near[:400]}" if near else "")
        loc = {**img.location, "image": img.id}
        section = [s for s in [img.location.get("sheet") or img.location.get("section") or "", "Picture"] if s]
        box = next((ln.split(":", 1)[1].strip() for ln in img.context.splitlines() if ln.startswith("Box title:")), "")
        crumbs = [c for c in (file_name, *section[:-1], box, "Picture", where) if c]
        rel: dict[str, Any] = {"group": f"pictures:{doc_id}", "parent": box or (section[0] if section else None)}
        if img.location.get("sheet") is not None and img.location.get("row") is not None:
            rel["row_key"] = f"{img.location['sheet']}!{img.location['row']}"
        elif img.location.get("slide") is not None:
            rel["row_key"] = f"slide:{img.location['slide']}"
        chunks.append(Chunk(str(uuid.uuid5(_NS, f"{doc_id}:chunk:{img.id}")), doc_id, start_index + len(chunks), "image",
                            text, context, section, loc, extra={"image_id": img.id}, breadcrumb=crumbs, relations=rel))
    return chunks


def index_described(doc_id: str) -> int:
    """(Re)write the document's picture chunks in Qdrant; returns how many."""
    from ..store import get_store

    store = get_store()
    doc = store.get_document(doc_id)
    if doc is None:
        return 0
    start = 1_000_000  # after every text/record chunk index
    return store.replace_image_chunks(doc, image_chunks(doc_id, doc["file_name"], start))
