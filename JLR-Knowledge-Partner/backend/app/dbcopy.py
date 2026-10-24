"""Copy the account database (users, usage, upload decisions, picture catalog) from SQLite to PostgreSQL.

    python -m app.cli migrate-db --target postgresql+psycopg://user:pass@localhost:5432/knowledge_partner

The source is only read. The target gets the latest schema (Alembic), then the rows with their ids, then its id counters
are moved past the copied ids, and finally row counts and checksums of both sides are compared.
Chat memory is not copied (it starts empty on PostgreSQL); document files and the Qdrant store are separate.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Integer, delete, func, inspect, select, text
from sqlalchemy.engine import Engine

import app.images.catalog  # noqa: F401 - registers the picture table on the shared metadata
from .auth.db import Base, make_engine, run_migrations

log = logging.getLogger(__name__)
BATCH = 1000


@dataclass
class TableReport:
    table: str
    source_rows: int = 0
    copied: int = 0
    target_rows: int = 0
    truncated_values: int = 0
    skipped: str = ""
    checks: dict[str, tuple[Any, Any]] = field(default_factory=dict)  # name -> (source, target)

    @property
    def ok(self) -> bool:
        return bool(self.skipped) or (self.source_rows == self.copied == self.target_rows
                                      and all(a == b for a, b in self.checks.values()))


def _checksums(engine: Engine, table) -> dict[str, Any]:
    """Row count, sums of numeric columns and a digest of text columns that must survive unchanged."""
    out: dict[str, Any] = {}
    with engine.connect() as conn:
        out["rows"] = conn.scalar(select(func.count()).select_from(table))
        for col in table.columns:
            if isinstance(col.type, Integer) and not col.foreign_keys:
                out[f"sum({col.name})"] = int(conn.scalar(select(func.coalesce(func.sum(col), 0))) or 0)
        for name in ("password_hash", "username", "sha256", "file_name"):
            if name in table.columns:
                values = conn.scalars(select(table.c[name]).order_by(table.c.id)).all()
                out[f"digest({name})"] = hashlib.sha256("\x1f".join(map(str, values)).encode()).hexdigest()[:16]
    return out


def _aware(value: Any) -> Any:
    """SQLite stores UTC without a zone: say so, or PostgreSQL would read it in the server's time zone."""
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


def copy_database(source_url: str, target_url: str, replace: bool = False) -> list[TableReport]:
    source, target = make_engine(source_url), make_engine(target_url)
    if source.dialect.name == target.dialect.name and source.url == target.url:
        raise ValueError("Source and target are the same database.")
    run_migrations(target)
    present = set(inspect(source).get_table_names())
    tables = list(Base.metadata.sorted_tables)  # parents before children

    with target.connect() as conn:
        filled = [t.name for t in tables if conn.scalar(select(func.count()).select_from(t))]
    if filled and not replace:
        raise ValueError(f"The target already has data in {', '.join(filled)}. Use --replace to empty it first.")

    reports: list[TableReport] = []
    with target.begin() as out:
        for t in reversed(tables):  # children first
            out.execute(delete(t))
        for t in tables:
            rep = TableReport(t.name)
            reports.append(rep)
            if t.name not in present:
                rep.skipped = "not in the source database"
                continue
            source_cols = {c["name"] for c in inspect(source).get_columns(t.name)}
            cols = [c for c in t.columns if c.name in source_cols]
            with source.connect() as src:
                rep.source_rows = src.scalar(select(func.count()).select_from(t))
                result = src.execute(select(*cols).order_by(*t.primary_key.columns))
                while True:
                    rows = result.fetchmany(BATCH)
                    if not rows:
                        break
                    batch = []
                    for row in rows:
                        rec = {}
                        for c, v in zip(cols, row):
                            v = _aware(v)
                            limit = getattr(c.type, "length", None)
                            if isinstance(v, str) and limit and len(v) > limit:  # PostgreSQL enforces VARCHAR(n)
                                v, rep.truncated_values = v[:limit], rep.truncated_values + 1
                            rec[c.name] = v
                        batch.append(rec)
                    out.execute(t.insert(), batch)
                    rep.copied += len(batch)
        if target.dialect.name == "postgresql":  # next generated id = highest copied id + 1
            for t in tables:
                pk = list(t.primary_key.columns)
                if len(pk) == 1 and isinstance(pk[0].type, Integer):
                    out.execute(text(f"SELECT setval(pg_get_serial_sequence('{t.name}', '{pk[0].name}'), "
                                     f"COALESCE((SELECT MAX({pk[0].name}) FROM {t.name}), 0) + 1, false)"))

    for rep, t in zip(reports, tables):
        if rep.skipped:
            continue
        a, b = _checksums(source, t), _checksums(target, t)
        rep.target_rows = b["rows"]
        rep.checks = {k: (a[k], b[k]) for k in a if k != "rows"}
    return reports
