"""Engismart: the router that `router/router_outlet.py` mounts at  {PREFIX}engismart .

Mounted twice: `router` (every call is logged by track_module_usage) and `file_router` (picture files: many calls per page, not logged)."""
from fastapi import APIRouter, Depends

from controller.engismart import admin, chat, documents, images
from controller.engismart.helper import ensure_ready

router = APIRouter(dependencies=[Depends(ensure_ready)])
for part in (admin.router, documents.router, images.router, chat.router):
    router.include_router(part)

file_router = APIRouter(dependencies=[Depends(ensure_ready)])
file_router.include_router(images.file_router)
