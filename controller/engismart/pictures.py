"""Pictures of documents: library counts, describing (vision model), include / exclude, extraction. Superuser and developer roles
(Manage knowledge). The picture file itself is served by `file_router`, which is not logged per request (a sheet preview loads
many thumbnails)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from controller.engismart.access import MANAGERS, ROLES, Principal
from controller.engismart.graphs.ingest_graph import refresh_images
from controller.engismart.helper import doc_or_404, run_endpoint
from controller.engismart.images import catalog as image_catalog
from controller.engismart.images import describe as image_describe
from controller.engismart.store import get_store
from controller.engismart.validator import DescribeRequest, ImageUpdate

router = APIRouter()
file_router = APIRouter()


@router.get("/images/summary")
async def images_summary(request: Request):
    """Library-wide picture counts, whether describing is switched on, the running job and a cost estimate."""
    def work(p: Principal):
        return {"counts": image_catalog.summary(), "vision": image_describe.config(), "job": image_describe.status(),
                "estimate": image_describe.estimate(image_catalog.waiting())}

    return await run_endpoint(request, work, roles=MANAGERS, what="/images/summary")


@router.get("/documents/{doc_id}/images")
async def document_images(doc_id: str, request: Request):
    def work(p: Principal):
        doc_or_404(doc_id)
        imgs = image_catalog.list_images(doc_id)
        return {"images": [image_catalog.public(i) for i in imgs], "counts": image_catalog.summary(doc_id),
                "vision": image_describe.config(),
                "estimate": image_describe.estimate([i for i in imgs if i.status in ("waiting", "failed")])}

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/images")


@file_router.get("/images/{image_id}/file")
async def image_file(image_id: str, request: Request, thumb: bool = False):
    """The picture itself; same access rules as the document it belongs to (domain + confidential)."""
    def work(p: Principal):
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

    return await run_endpoint(request, work, roles=ROLES, what="/images/file")


@router.patch("/images/{image_id}")
async def update_image(image_id: str, request: Request):
    def work(p: Principal, req: ImageUpdate):
        try:
            return image_catalog.public(image_catalog.set_included(image_id, req.included))
        except KeyError as e:
            raise HTTPException(404, "picture not found") from e
        except ValueError as e:
            raise HTTPException(409, str(e)) from e

    return await run_endpoint(request, work, roles=MANAGERS, body=ImageUpdate, what="/images/update")


@router.post("/images/describe")
async def describe_images(request: Request):
    def work(p: Principal, req: DescribeRequest):
        try:
            return image_describe.start_job(p.id, req.doc_ids, req.image_ids)
        except (RuntimeError, ValueError) as e:
            raise HTTPException(409, str(e)) from e

    return await run_endpoint(request, work, roles=MANAGERS, body=DescribeRequest, what="/images/describe")


@router.get("/images/job")
async def describe_job(request: Request):
    return await run_endpoint(request, lambda p: image_describe.status(), roles=MANAGERS, what="/images/job")


@router.post("/images/job/cancel")
async def cancel_describe_job(request: Request):
    def work(p: Principal):
        image_describe.cancel()
        return image_describe.status()

    return await run_endpoint(request, work, roles=MANAGERS, what="/images/job/cancel")


@router.post("/documents/{doc_id}/images/extract")
async def extract_document_images(doc_id: str, request: Request):
    """Extract the pictures of an already indexed document from its stored original (text is not re-embedded)."""
    def work(p: Principal):
        doc_or_404(doc_id)
        try:
            return refresh_images(doc_id)
        except FileNotFoundError as e:
            raise HTTPException(409, "the original file is not stored; upload it again") from e

    return await run_endpoint(request, work, roles=MANAGERS, what="/documents/images/extract")
