"""Engismart's own tables (SQLAlchemy 2.0) and the migrations that create them.

Platform users live in the platform's tbl_users: nothing here stores a password, a login or a role.
The database is the platform's (DATABASE_URL); our tables are prefixed tbl_engismart_ and have their own Alembic version table,
so our migrations never touch the platform's schema. SQLite works for local runs and tests."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import get_settings

VERSION_TABLE = "alembic_version_engismart"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    """ISO-8601 with an explicit UTC offset (SQLite returns naive datetimes; browsers would read them as local time)."""
    if dt is None:
        return None
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).isoformat()


class Base(DeclarativeBase):
    pass


class UserAccess(Base):
    """Which engineering domains a platform user may ask about (no row or an empty list = all domains)."""

    __tablename__ = "tbl_engismart_user_access"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # tbl_users.id (platform)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageEvent(Base):
    __tablename__ = "tbl_engismart_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)  # tbl_users.id (platform)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="question")  # question | classify
    session_id: Mapped[str] = mapped_column(String(128), default="")
    question_chars: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(32), default="")
    intent: Mapped[str] = mapped_column(String(32), default="")
    found: Mapped[bool] = mapped_column(Boolean, default=True)


class UploadDecision(Base):
    """What the system suggested for an upload and what the SME chose: lets us measure the suggestions."""

    __tablename__ = "tbl_engismart_upload_decision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    check_id: Mapped[str] = mapped_column(String(64), default="")
    file_name: Mapped[str] = mapped_column(String(255), default="")
    domain: Mapped[str] = mapped_column(String(64), default="")
    intent: Mapped[str] = mapped_column(String(16), default="new")  # new | update
    replaces: Mapped[str] = mapped_column(String(64), default="")  # doc_id of the document the SME chose to update
    exact: Mapped[list] = mapped_column(JSON, default=list)
    suggestions: Mapped[list] = mapped_column(JSON, default=list)  # [{doc_id, label, scores}]
    result_status: Mapped[str] = mapped_column(String(16), default="")


_engine = None
SessionLocal = sessionmaker(expire_on_commit=False)


def make_engine(url: str):
    """Engine for a SQLite file or a server database (UTC session time zone on PostgreSQL, pooled connections)."""
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(conn, _):  # concurrent readers
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    s = get_settings()
    kwargs = {"connect_args": {"options": "-c timezone=UTC"}} if url.startswith("postgresql") else {}
    return create_engine(url, pool_pre_ping=True, pool_size=s.db_pool_size, max_overflow=s.db_max_overflow,
                         pool_recycle=s.db_pool_recycle_s, **kwargs)


def run_migrations(engine) -> None:
    """Bring our tables to the latest revision. One process at a time on PostgreSQL."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.exec_driver_sql("SELECT pg_advisory_xact_lock(7240011)")  # released when this transaction ends
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def init_db() -> None:
    global _engine
    if _engine is not None:
        return
    engine = make_engine(get_settings().db_url)
    try:
        run_migrations(engine)
    except OperationalError as e:  # server down, wrong password, unknown database: say what to check (never print the password)
        raise RuntimeError(f"Cannot open the database {engine.url.render_as_string(hide_password=True)}: "
                           f"{str(e.orig).strip().splitlines()[0] if e.orig else e}. Check that the server is running and "
                           "that DATABASE_* (or DATABASE_URL) in the .env file is correct.") from e
    _engine = engine
    SessionLocal.configure(bind=engine)
