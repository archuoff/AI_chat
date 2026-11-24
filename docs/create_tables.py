"""Creates the 6 tables Engismart needs. For the platform / DBA person: run it ONCE per environment with an account that may create tables.

    tbl_engismart_image       the picture catalog (ours; class EngismartImage in models/orm_models.py)
    tbl_engismart_chat_turn   the questions, answers and sources of the conversations (ours; class ChatTurn)
    checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations
                          the chat memory (LangGraph's own tables, created through the library so they always match the installed version)

Run it from the project root, with the .env.<environment> of the TARGET database (DATABASE_* of an account that can create tables):

    uv run python docs/engismart/create_tables.py                 create the tables that are missing (safe to run twice)
    uv run python docs/engismart/create_tables.py --print-sql     print the SQL and create nothing (to review it, or to run it in your own SQL tool)
    uv run python docs/engismart/create_tables.py --print-sql --dialect mysql        the same for another database (mysql | postgresql)

Afterwards:
  * set CHAT_MEMORY_SETUP=off in the application's .env: the app then never runs DDL, its database account only needs
    SELECT / INSERT / UPDATE / DELETE on these 6 tables (plus the platform tables it already uses);
  * the SQL printed by --print-sql includes the version rows of checkpoint_migrations. Keep them: they tell the library that its
    tables are complete. Run the statements ONE BY ONE with autocommit (PostgreSQL's CREATE INDEX CONCURRENTLY cannot run in a transaction).
"""
import argparse
import os
import sys

sys.path.insert(0, os.getcwd())

from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.dialects import mysql, postgresql  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from models.orm_models import ChatTurn, EngismartImage, engine  # noqa: E402

CHAT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations")
OUR_TABLES = (EngismartImage, ChatTurn)
DIALECTS = {"mysql": mysql.dialect(), "postgresql": postgresql.dialect()}


def _saver_class(dialect: str):
    if dialect == "mysql":
        from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
        return PyMySQLSaver
    from langgraph.checkpoint.postgres import PostgresSaver
    return PostgresSaver


def print_sql(dialect: str) -> None:
    d = DIALECTS[dialect]
    print(f"-- Engismart tables for {dialect}. Run the statements one by one, with autocommit.\n")
    print("-- 1. our tables")
    for model in OUR_TABLES:
        table = model.__table__
        print(str(CreateTable(table).compile(dialect=d)).strip() + ";")
        for idx in table.indexes:
            print(str(CreateIndex(idx).compile(dialect=d)).strip() + ";")
    print("\n-- 2. the chat memory: the library's own statements, each followed by its version row")
    for v, statement in enumerate(_saver_class(dialect).MIGRATIONS):
        print(statement.strip().rstrip(";") + ";")
        print(f"INSERT INTO checkpoint_migrations (v) VALUES ({v});")


def create() -> None:
    url = engine.url
    dialect = engine.dialect.name
    print("Database:", url.render_as_string(hide_password=True), f"({dialect})")
    if dialect not in DIALECTS:
        sys.exit(f"{dialect} is not supported by this script (MySQL and PostgreSQL only; a SQLite test database creates its tables itself).")
    for model in OUR_TABLES:
        model.__table__.create(bind=engine, checkfirst=True)
    print("our tables: ok")
    if dialect == "mysql":
        import pymysql
        u = make_url(str(url))
        conn = pymysql.connect(host=u.host or "localhost", port=u.port or 3306, user=u.username, password=u.password or "",
                               database=u.database, autocommit=True, charset="utf8mb4")
        try:
            _saver_class("mysql")(conn).setup()
        finally:
            conn.close()
    else:
        conninfo = url.set(drivername="postgresql").render_as_string(hide_password=False)
        with _saver_class("postgresql").from_conn_string(conninfo) as saver:
            saver.setup()
    print("chat memory tables: ok")
    have = set(inspect(engine).get_table_names())
    for name in (*(m.__tablename__ for m in OUR_TABLES), *CHAT_TABLES):
        print(f"  {name:24s} {'present' if name in have else 'MISSING'}")
    print("\nNext: set CHAT_MEMORY_SETUP=off in the application's .env.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print-sql", action="store_true", help="print the SQL and create nothing")
    ap.add_argument("--dialect", choices=sorted(DIALECTS), help="with --print-sql: the database type (default: the one of DATABASE_*)")
    a = ap.parse_args()
    if a.print_sql:
        print_sql(a.dialect or ("postgresql" if engine.dialect.name == "postgresql" else "mysql"))
    else:
        create()
