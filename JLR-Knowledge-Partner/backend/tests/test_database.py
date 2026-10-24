"""Database layer: migrations, adopting a pre-Alembic SQLite file, SQLite -> PostgreSQL copy, chat memory on PostgreSQL."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, select, text

from conftest import PG_URL, reset_postgres

needs_pg = pytest.mark.skipif(not PG_URL, reason="set TEST_DATABASE_URL to a PostgreSQL URL")
UTC = timezone.utc


@pytest.fixture()
def fresh_app(tmp_path, monkeypatch, db_url):
    """The app's database module pointed at an empty database; returns (db module, url)."""
    monkeypatch.setenv("DATABASE_URL", db_url)
    from app import config
    from app.auth import db

    config.get_settings.cache_clear()
    monkeypatch.setattr(db, "_engine", None)
    yield db, db_url
    if db._engine is not None:
        db._engine.dispose()
    config.get_settings.cache_clear()


def test_url_is_routed_to_psycopg(monkeypatch):
    from app import config

    for given in ("postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"):
        monkeypatch.setenv("DATABASE_URL", given)
        config.get_settings.cache_clear()
        assert config.get_settings().db_url == "postgresql+psycopg://u:p@h:5432/d" and config.get_settings().db_is_postgres
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/x.db")
    config.get_settings.cache_clear()
    assert not config.get_settings().db_is_postgres
    config.get_settings.cache_clear()


def test_unreachable_database_gives_a_clear_message(monkeypatch):
    from app import config
    from app.auth import db

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://kp:secret-pw@127.0.0.1:1/none")
    config.get_settings.cache_clear()
    monkeypatch.setattr(db, "_engine", None)
    with pytest.raises(RuntimeError) as e:
        db.init_db()
    assert "Cannot open the database" in str(e.value) and "secret-pw" not in str(e.value) and "DATABASE_URL" in str(e.value)
    config.get_settings.cache_clear()


def test_migrations_match_the_models(fresh_app):
    """The Alembic baseline creates exactly what the ORM models describe (no drift)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    db, _ = fresh_app
    db.init_db()
    with db._engine.connect() as conn:
        assert {"users", "usage_events", "upload_decisions", "doc_images", "alembic_version"} <= set(inspect(conn).get_table_names())
        assert compare_metadata(MigrationContext.configure(conn), db.Base.metadata) == []
        assert conn.scalar(text("select version_num from alembic_version")) == "0001"
    db.init_db()  # running it again changes nothing


def test_database_created_before_alembic_is_adopted(fresh_app):
    """An old install (tables from create_all, one table missing, no alembic_version) keeps its rows and gets the rest."""
    db, url = fresh_app
    engine = create_engine(url)
    db.Base.metadata.create_all(engine, tables=[db.User.__table__])  # what the first version made
    with engine.begin() as conn:
        conn.execute(db.User.__table__.insert(), [{"username": "old", "display_name": "Old", "password_hash": "x", "role": "user",
                                                   "domains": [], "is_active": True, "created_at": datetime.now(UTC), "token_version": 0}])
    engine.dispose()
    db.init_db()
    with db.SessionLocal() as s:
        assert [u.username for u in s.scalars(select(db.User))] == ["old"]
    assert {"usage_events", "upload_decisions", "doc_images"} <= set(inspect(db._engine).get_table_names())


def test_overlong_values_do_not_break_the_decision_log(api):
    """PostgreSQL enforces VARCHAR(n); the log shortens what it stores instead of failing."""
    from pathlib import Path

    from app import main, uploads
    from app.auth import Principal
    from app.auth.db import SessionLocal, UploadDecision

    item = uploads.Pending("c" * 90, 1, "n" * 400 + ".xlsx", Path("/x"), "f", 1)
    req = main.CommitRequest(check_id="c", intent="new", domain="d" * 90)
    main._log_decision(Principal(1, "dev", "Dev", "developer"), item, req, {"status": "indexed"})
    with SessionLocal() as db:
        row = db.query(UploadDecision).one()
    assert len(row.file_name) == 255 and len(row.check_id) == 64 and len(row.domain) == 64


# ------------------------------------------------------------------ SQLite -> PostgreSQL copy
def _fill_source(tmp_path, n_usage=2500):
    """A SQLite database in the old shape, with the awkward cases: unicode, JSON, naive datetimes, booleans, nulls, long text."""
    from app.auth import db
    from app.images.catalog import DocImage

    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = create_engine(url)
    db.Base.metadata.create_all(engine)
    base = datetime(2026, 3, 1, 23, 30, 0)  # naive: SQLite stores UTC without a zone
    with engine.begin() as conn:
        conn.execute(db.User.__table__.insert(), [
            {"id": 1, "username": "dev", "display_name": "Dév Üser 日本", "password_hash": "$argon2id$v=19$m=65536$abc", "role": "developer",
             "domains": [], "is_active": True, "created_at": base, "last_login_at": None, "token_version": 3},
            {"id": 7, "username": "anna", "display_name": "Anna", "password_hash": "$argon2id$v=19$m=65536$def", "role": "user",
             "domains": ["adas", "eds"], "is_active": False, "created_at": base, "last_login_at": base + timedelta(days=1), "token_version": 0}])
        conn.execute(db.UsageEvent.__table__.insert(), [
            {"user_id": 1 if i % 2 else 7, "created_at": base + timedelta(minutes=i), "kind": "question", "session_id": f"s{i}",
             "question_chars": i, "input_tokens": i * 3, "output_tokens": i, "llm_calls": 2, "latency_ms": 100 + i, "mode": "azure-openai",
             "intent": "lookup", "found": bool(i % 5)} for i in range(n_usage)])
        conn.execute(db.UploadDecision.__table__.insert(), [
            {"created_at": base, "user_id": 1, "check_id": "c1", "file_name": "Ünïcode ✓.xlsx", "domain": "adas", "intent": "update",
             "replaces": "d1", "exact": [], "suggestions": [{"doc_id": "d1", "label": "likely", "scores": {"name": 1.0, "content": 0.9}}],
             "result_status": "indexed"}])
        conn.execute(DocImage.__table__.insert(), [
            {"id": "img-1", "doc_id": "d1", "position": 0, "sha256": "a" * 64, "location": {"slide": 3}, "context": "x" * 5000, "width": 10,
             "height": 20, "status": "failed", "reason": "r" * 300, "manual": False, "description": "", "input_tokens": 1, "output_tokens": 2,
             "described_at": None, "created_at": base}])
    engine.dispose()
    return url


@needs_pg
def test_copy_sqlite_to_postgres(tmp_path):
    from app.auth import db
    from app.dbcopy import copy_database
    from app.images.catalog import DocImage

    source = _fill_source(tmp_path)
    reset_postgres(PG_URL)
    reports = copy_database(source, PG_URL)
    assert all(r.ok for r in reports), [(r.table, r.checks, r.source_rows, r.target_rows) for r in reports if not r.ok]
    by = {r.table: r for r in reports}
    assert (by["users"].copied, by["usage_events"].copied, by["upload_decisions"].copied, by["doc_images"].copied) == (2, 2500, 1, 1)
    assert by["doc_images"].truncated_values == 1  # a 300-character reason became 160

    engine = db.make_engine(PG_URL)
    with engine.connect() as conn:
        user = conn.execute(select(db.User.__table__).where(db.User.__table__.c.id == 7)).one()
        assert user.created_at == datetime(2026, 3, 1, 23, 30, tzinfo=UTC)  # same instant, not shifted by a server time zone
        assert user.domains == ["adas", "eds"] and user.is_active is False
        assert conn.scalar(select(db.User.__table__.c.display_name).where(db.User.__table__.c.id == 1)) == "Dév Üser 日本"
        assert conn.scalar(select(DocImage.__table__.c.location)) == {"slide": 3}
    # new rows continue after the copied ids
    with engine.begin() as conn:
        new_id = conn.execute(db.User.__table__.insert().returning(db.User.__table__.c.id),
                              {"username": "new", "display_name": "N", "password_hash": "h", "role": "user", "domains": [],
                               "is_active": True, "created_at": datetime.now(UTC), "token_version": 0}).scalar()
    assert new_id == 8
    engine.dispose()


@needs_pg
def test_copy_refuses_a_filled_target_unless_replace(tmp_path):
    from app.dbcopy import copy_database

    source = _fill_source(tmp_path, n_usage=10)
    reset_postgres(PG_URL)
    copy_database(source, PG_URL)
    with pytest.raises(ValueError, match="already has data"):
        copy_database(source, PG_URL)
    assert all(r.ok for r in copy_database(source, PG_URL, replace=True))  # re-run is safe and gives the same result


@needs_pg
def test_cli_migrate_db_reports_and_exits_zero(tmp_path, capsys):
    from app import cli

    source = _fill_source(tmp_path, n_usage=20)
    reset_postgres(PG_URL)
    assert cli.main(["migrate-db", "--source", source, "--target", PG_URL]) == 0
    out = capsys.readouterr().out
    assert "users" in out and "Copy complete and verified." in out
    assert cli.main(["migrate-db", "--source", source, "--target", "sqlite:///x.db"]) == 2  # target must be PostgreSQL


@needs_pg
def test_chat_memory_lives_in_postgres(monkeypatch):
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    from app import config
    from app.graphs import chat_graph

    reset_postgres(PG_URL)
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    config.get_settings.cache_clear()

    class S(TypedDict, total=False):
        n: int

    g = StateGraph(S)
    g.add_node("inc", lambda s: {"n": s.get("n", 0) + 1})
    g.add_edge(START, "inc")
    g.add_edge("inc", END)
    saver = chat_graph._postgres_checkpointer()
    try:
        graph = g.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "u1:abc"}}
        graph.invoke({"n": 1}, cfg)
        assert graph.get_state(cfg).values == {"n": 2}
        saver.delete_thread("u1:abc")
        assert graph.get_state(cfg).values == {}
    finally:
        chat_graph.close_chat_memory()
        config.get_settings.cache_clear()
