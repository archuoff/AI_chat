"""Pictures of documents: library counts, describing (vision model), include / exclude, extraction. The picture file itself
is served by `file_router`, which is not logged per request (a sheet preview loads many thumbnails)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from controller.engismart.envelope import EnvelopeRoute
from controller.engismart.helper import doc_or_404
from controller.engismart.validator import DescribeRequest, ImageUpdate
from services.engismart.access import Principal, current_user, require
from services.engismart.graphs.ingest_graph import refresh_images
from services.engismart.images import catalog as image_catalog
from services.engismart.images import describe as image_describe
from services.engismart.store import get_store

router = APIRouter(route_class=EnvelopeRoute)
file_router = APIRouter()
developer = require("developer")


@router.get("/images/summary")
def images_summary(_: Principal = Depends(developer)):
    """Library-wide picture counts, whether describing is switched on, the running job and a cost estimate."""
    return {"counts": image_catalog.summary(), "vision": image_describe.config(), "job": image_describe.status(),
            "estimate": image_describe.estimate(image_catalog.waiting())}


@router.get("/documents/{doc_id}/images")
def document_images(doc_id: str, _: Principal = Depends(developer)):
    doc_or_404(doc_id)
    imgs = image_catalog.list_images(doc_id)
    return {"images": [image_catalog.public(i) for i in imgs], "counts": image_catalog.summary(doc_id),
            "vision": image_describe.config(), "estimate": image_describe.estimate([i for i in imgs if i.status in ("waiting", "failed")])}


@file_router.get("/images/{image_id}/file")
def image_file(image_id: str, thumb: bool = False, p: Principal = Depends(current_user)):
    """The picture itself; same access rules as the document it belongs to (domain + confidential)."""
    img = image_catalog.get_image(image_id)
    doc = get_store().get_document(img.doc_id) if img else None
    allowed = p.allowed_domains()
    if (img is None or doc is None or (doc.get("confidential") and not p.sees_confidential)
            or (allowed is not None and doc.get("domain") not in allowed)):
        raise HTTPException(404, "picture not found")
    path = image_catalog.file_path(img, thumb)
    if not path.exists():
        raise HTTPException(404, "picture file not available")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.patch("/images/{image_id}")
def update_image(image_id: str, req: ImageUpdate, _: Principal = Depends(developer)):
    try:
        return image_catalog.public(image_catalog.set_included(image_id, req.included))
    except KeyError as e:
        raise HTTPException(404, "picture not found") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/images/describe")
def describe_images(req: DescribeRequest, p: Principal = Depends(developer)):
    try:
        return image_describe.start_job(p.id, req.doc_ids, req.image_ids)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e)) from e


@router.get("/images/job")
def describe_job(_: Principal = Depends(developer)):
    return image_describe.status()


@router.post("/images/job/cancel")
def cancel_describe_job(_: Principal = Depends(developer)):
    image_describe.cancel()
    return image_describe.status()


@router.post("/documents/{doc_id}/images/extract")
def extract_document_images(doc_id: str, _: Principal = Depends(developer)):
    """Extract the pictures of an already indexed document from its stored original (text is not re-embedded)."""
    doc_or_404(doc_id)
    try:
        return refresh_images(doc_id)
    except FileNotFoundError as e:
        raise HTTPException(409, "the original file is not stored; upload it again") from e
