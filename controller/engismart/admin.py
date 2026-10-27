"""Who am I, health, domains, per-user domain settings and the usage page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from controller.engismart.envelope import EnvelopeRoute
from controller.engismart.helper import visible_documents
from controller.engismart.validator import UserDomainsUpdate
from services.engismart import directory
from services.engismart import usage as usage_store
from services.engismart.access import Principal, current_user, require, role_of
from services.engismart.config import get_settings
from services.engismart.db import SessionLocal, UserAccess, iso, utcnow
from services.engismart.domains import DOMAIN_IDS, UNASSIGNED, domains_payload
from services.engismart.ingestion import SUPPORTED_EXTENSIONS
from services.engismart.llm import get_reranker
from services.engismart.store import get_store

router = APIRouter(route_class=EnvelopeRoute)
developer = require("developer")


@router.get("/me")
def me(p: Principal = Depends(current_user)):
    return p.public()


@router.get("/health")
def health(p: Principal = Depends(current_user)):
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


@router.get("/domains")
def list_domains(p: Principal = Depends(current_user)):
    """Developers get document counts; other roles get the domains they may ask about."""
    allowed = p.allowed_domains()
    if not p.is_developer:
        return [d for d in domains_payload() if allowed is None or d["id"] in allowed]
    stats = get_store().domain_stats()
    empty = {"documents": 0, "chunks": 0}
    out = [{**d, **stats.get(d["id"], empty)} for d in domains_payload()]
    out.append({"id": UNASSIGNED, "name": "Unassigned", "description": "Documents not yet classified.",
                **stats.get(UNASSIGNED, empty)})
    return out


def _user_out(info: dict, domains: list[str], stats: dict | None) -> dict:
    s = stats or {}
    return {"id": info["id"], "username": info["username"], "display_name": info["display_name"],
            "role": role_of(info["roles"], info["is_admin"]), "domains": domains, "is_active": info["is_active"],
            "questions_30d": s.get("questions", 0), "tokens_30d": s.get("input_tokens", 0) + s.get("output_tokens", 0),
            "last_active": iso(s.get("last_active"))}


def _domains_by_user() -> dict[int, list[str]]:
    with SessionLocal() as db:
        return {r.user_id: list(r.domains or []) for r in db.scalars(select(UserAccess)).all()}


@router.get("/users")
def list_users(_: Principal = Depends(developer)):
    """Platform users Engismart knows (asked a question or has a domain setting). Accounts and roles are managed in the platform."""
    ids = usage_store.known_user_ids()
    info, stats, domains = directory.describe_users(ids), usage_store.per_user_stats(30), _domains_by_user()
    return [_user_out(info[i], domains.get(i, []), stats.get(i)) for i in ids if i in info]


@router.get("/users/lookup")
def lookup_users(q: str, _: Principal = Depends(developer)):
    """Find a platform user by name to give them a domain setting."""
    domains, stats = _domains_by_user(), usage_store.per_user_stats(30)
    return [_user_out(u, domains.get(u["id"], []), stats.get(u["id"])) for u in directory.search_users(q)]


@router.put("/users/{user_id}/domains")
def set_user_domains(user_id: int, req: UserDomainsUpdate, _: Principal = Depends(developer)):
    """Limit the domains a user may ask about (empty list = all). Roles are changed in the platform, not here."""
    bad = [d for d in req.domains if d not in DOMAIN_IDS]
    if bad:
        raise HTTPException(422, f"Unknown domain(s): {bad}. Valid: {sorted(DOMAIN_IDS)}")
    if user_id not in directory.describe_users([user_id]):
        raise HTTPException(404, "User not found")
    domains = list(dict.fromkeys(req.domains))
    with SessionLocal() as db:
        row = db.get(UserAccess, user_id)
        if row is None:
            db.add(UserAccess(user_id=user_id, domains=domains, updated_at=utcnow()))
        else:
            row.domains, row.updated_at = domains, utcnow()
        db.commit()
    return {"user_id": user_id, "domains": domains}


@router.get("/usage/summary")
def usage_summary(days: int = 30, _: Principal = Depends(developer)):
    return usage_store.summary(max(1, min(days, 365)))
