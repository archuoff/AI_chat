"""Account database (SQLAlchemy 2.0). SQLite by default; set DATABASE_URL for Postgres etc."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from ..config import get_settings

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


def init_db() -> None:
    global _engine
    if _engine is not None:
        return
    url = get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(conn, _):  # foreign keys + concurrent readers
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    else:
        _engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(_engine)
    SessionLocal.configure(bind=_engine)
