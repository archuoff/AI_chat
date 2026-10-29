"""Who am I, health and the domains. Accounts, roles and domain access are managed in the platform (see access.py)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from controller.engismart.access import Principal
from controller.engismart.config import get_settings
from controller.engismart.domains import UNASSIGNED, domains_payload
from controller.engismart.helper import run_endpoint, visible_documents
from controller.engismart.ingestion import SUPPORTED_EXTENSIONS
from controller.engismart.llm import get_reranker
from controller.engismart.store import get_store

router = APIRouter()


@router.get("/me")
async def me(request: Request):
    return await run_endpoint(request, lambda p: p.public(), what="/me")


@router.get("/health")
async def health(request: Request):
    def work(p: Principal):
        s = get_settings()
        store = get_store()
        out = {"status": "ok", "llm": "azure-openai" if s.llm_enabled else "offline", "documents": len(visible_documents(p))}
        if p.is_developer:
            reranker = get_reranker()
            out.update({"llm_deployment": s.azure_openai_chat_deployment if s.llm_enabled else None,
                        "embedding": store.embedder.name, "sparse": store.sparse.name,
                        "reranker": reranker.name if reranker else None, "qdrant": store.location,
                        "supported_extensions": SUPPORTED_EXTENSIONS, "chunks": store.stats()["chunks"]})
        return out

    return await run_endpoint(request, work, what="/health")


@router.get("/domains")
async def list_domains(request: Request):
    """Superusers and developers get document counts; a normal user gets the domains they may ask about."""
    def work(p: Principal):
        allowed = p.allowed_domains()
        if not p.manages_knowledge:
            return [d for d in domains_payload() if allowed is None or d["id"] in allowed]
        stats = get_store().domain_stats()
        empty = {"documents": 0, "chunks": 0}
        out = [{**d, **stats.get(d["id"], empty)} for d in domains_payload()]
        out.append({"id": UNASSIGNED, "name": "Unassigned", "description": "Documents not yet classified.",
                    **stats.get(UNASSIGNED, empty)})
        return out

    return await run_endpoint(request, work, what="/domains")
