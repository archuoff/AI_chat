"""Engismart: the routers that `router/router_outlet.py` mounts at  {PREFIX}engismart .

Mounted twice: `router` (every call is logged by track_module_usage) and `file_router` (picture files: many calls per page, not logged).
Every endpoint follows the platform's pattern (see helper.run_endpoint): token -> user -> role -> work in a thread pool -> envelope."""
from fastapi import APIRouter

from controller.engismart import admin, chat, documents, pictures
from controller.engismart.helper import warm_up

router = APIRouter()
for part in (admin.router, documents.router, pictures.router, chat.router):
    router.include_router(part)

file_router = APIRouter()
file_router.include_router(pictures.file_router)

warm_up()  # opens the search index in the background; never delays or breaks the platform's start-up
