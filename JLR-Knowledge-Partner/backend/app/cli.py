"""Command line access (stop the API first when using embedded Qdrant: only one process can open it).

    python -m app.cli ingest C:\\KG\\DATA --meta "{\"project\": \"EDS\"}" [--force]
    python -m app.cli search "magnesium cross car beam" [--top 5] [--mode hybrid|dense|keyword]
    python -m app.cli docs
    python -m app.cli delete <doc_id>
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .graphs.ingest_graph import run_ingest
from .ingestion import SUPPORTED_EXTENSIONS
from .store import get_store


def _files(paths: list[str]) -> list[Path]:
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith("~$")))
        elif p.exists():
            out.append(p)
        else:
            print(f"not found: {p}", file=sys.stderr)
    return out


def _create_user(a) -> int:
    import secrets

    from sqlalchemy import func, select

    from .auth.db import SessionLocal, User, init_db
    from .auth.security import MIN_PASSWORD_LENGTH, hash_password
    from .domains import DOMAIN_IDS

    init_db()
    domains = [d.strip() for d in a.domains.split(",") if d.strip()]
    bad = [d for d in domains if d not in DOMAIN_IDS]
    if bad:
        print(f"unknown domains {bad}; valid: {sorted(DOMAIN_IDS)}", file=sys.stderr)
        return 2
    password = a.password or secrets.token_urlsafe(12)
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"password must be at least {MIN_PASSWORD_LENGTH} characters", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        if db.scalar(select(User).where(func.lower(User.username) == a.username.lower())):
            print(f"user '{a.username}' already exists", file=sys.stderr)
            return 1
        db.add(User(username=a.username, display_name=a.display_name, password_hash=hash_password(password),
                    role=a.role, domains=domains))
        db.commit()
    print(f"created {a.role} '{a.username}'" + ("" if a.password else f" with password: {password}"))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("paths", nargs="+")
    p_ing.add_argument("--meta", default="{}", help="JSON object of manual fields attached to every chunk")
    p_ing.add_argument("--force", action="store_true")
    p_ing.add_argument("--domain", default=None, help="engineering domain id (adas, benchmarking, eds, ...); default keeps the current one")
    p_s = sub.add_parser("search")
    p_s.add_argument("query")
    p_s.add_argument("--top", type=int, default=5)
    p_s.add_argument("--mode", default="hybrid", choices=["hybrid", "dense", "keyword"])
    sub.add_parser("docs")
    p_d = sub.add_parser("delete")
    p_d.add_argument("doc_id")
    p_x = sub.add_parser("extract-images", help="extract pictures of indexed documents (no re-embedding of text)")
    p_x.add_argument("doc_ids", nargs="*", help="default: every document")
    p_g = sub.add_parser("build-signatures", help="build the similar-document data of documents ingested earlier (no re-embedding)")
    p_g.add_argument("doc_ids", nargs="*", help="default: every document without one")
    p_u = sub.add_parser("create-user", help="create an account (works while the API is running)")
    p_u.add_argument("username")
    p_u.add_argument("--role", default="user", choices=["user", "superuser", "developer"])
    p_u.add_argument("--display-name", default="")
    p_u.add_argument("--domains", default="", help="comma separated domain ids; empty = all domains")
    p_u.add_argument("--password", default="", help="omit to generate a random one")
    a = ap.parse_args(argv)

    if a.cmd == "create-user":  # account DB only: no Qdrant needed
        return _create_user(a)

    store = get_store()
    try:
        if a.cmd == "ingest":
            meta = json.loads(a.meta)
            for f in _files(a.paths):
                r = run_ingest(f, meta=meta, force=a.force, domain=a.domain)
                extra = r.get("error") or r.get("reason") or f"{r.get('records', 0)} records, {r.get('text_blocks', 0)} text blocks -> {r.get('chunks', 0)} chunks"
                print(f"[{r['status']:8}] {r['file_name']}  ({r['seconds']}s)  {extra}")
                for w in r.get("warnings", []):
                    print(f"           ! {w}")
            print(store.stats())
        elif a.cmd == "search":
            for h in store.search(a.query, a.top, mode=a.mode):
                print(f"\n{h['score']:.4f}  {h['context']}\n  " + h["text"][:300].replace("\n", "\n  "))
        elif a.cmd == "docs":
            for d in store.list_documents():
                print(f"{d['doc_id']}  {d['file_type']:5} {d['chunks']:5} chunks  {d['file_name']}")
        elif a.cmd == "delete":
            from .images import catalog

            found = store.delete_document(a.doc_id)
            catalog.delete_document(a.doc_id)
            print("deleted" if found else "not found")
        elif a.cmd == "build-signatures":
            from .graphs.ingest_graph import rebuild_signature

            for d in store.list_documents():
                if (a.doc_ids and d["doc_id"] in a.doc_ids) or (not a.doc_ids and "sig_size" not in d):
                    print(f"{d['file_name']}: {'ok' if rebuild_signature(d['doc_id']) else 'original file not found'}")
        elif a.cmd == "extract-images":
            from .graphs.ingest_graph import refresh_images

            for d in store.list_documents():
                if not a.doc_ids or d["doc_id"] in a.doc_ids:
                    print(f"{d['file_name']}: {refresh_images(d['doc_id'])}")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
