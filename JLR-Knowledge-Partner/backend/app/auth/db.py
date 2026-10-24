"""Account database (SQLAlchemy 2.0). SQLite by default; DATABASE_URL=postgresql+psycopg://... selects PostgreSQL.

The schema is owned by Alembic (backend/migrations): init_db() upgrades the database to the latest revision."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from ..config import BASE_DIR, get_settings

ROLES = ("user", "superuser", "developer")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    """ISO-8601 with an explicit UTC offset (SQLite returns naive datetimes; browsers would read them as local time)."""
    if dt is None:
        return None
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).isoformat()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")
    # domain ids this user may query; empty list = all domains (role "user" still never sees confidential files)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # bumped on password change / deactivation: tokens issued before become invalid
    token_version: Mapped[int] = mapped_column(Integer, default=0)


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
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

    __tablename__ = "upload_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
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
MIGRATIONS_DIR = BASE_DIR / "migrations"


def make_engine(url: str):
    """Engine for a SQLite file or a PostgreSQL server (UTC session time zone, pooled connections)."""
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(conn, _):  # foreign keys + concurrent readers
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    s = get_settings()
    return create_engine(url, pool_pre_ping=True, pool_size=s.db_pool_size, max_overflow=s.db_max_overflow,
                         pool_recycle=s.db_pool_recycle_s, connect_args={"options": "-c timezone=UTC"})


def run_migrations(engine) -> None:
    """Bring the database to the latest schema revision. A database created before migrations existed
    (tables made by create_all) is handled by the idempotent baseline revision. One process at a time on PostgreSQL."""
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
                           f"{str(e.orig).strip().splitlines()[0] if e.orig else e}. Check that the server is running and that "
                           "DATABASE_URL in backend\\.env is correct.") from e
    _engine = engine
    SessionLocal.configure(bind=engine)
