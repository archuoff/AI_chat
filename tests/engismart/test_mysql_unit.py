"""MySQL cannot be started in this environment: the MySQL chat-memory wiring is checked with a fake connection (no live server)."""
from unittest.mock import MagicMock

from conftest import FakeDense  # noqa: F401  (forces the patched imports first)


def test_backend_is_read_from_the_platform_url(monkeypatch):
    from controller.engismart.core import config
    for url, backend in (("mysql+pymysql://u:p@h:3306/db", "mysql"), ("postgresql+psycopg2://u@h/db", "postgresql"),
                         ("postgres://u@h/db", "postgresql"), ("sqlite:///x.db", "sqlite")):
        monkeypatch.setattr(config, "_platform_database_url", lambda url=url: url)
        assert config.get_settings().db_backend == backend


def test_mysql_saver_pings_before_every_use_and_sets_up(monkeypatch):
    import pymysql
    from controller.engismart.core import config
    from controller.engismart.chat import chat_graph as cg

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = None
    conn.cursor.return_value.__enter__.return_value = cur
    seen = {}

    def fake_connect(**kw):
        seen.update(kw)
        return conn
    monkeypatch.setattr(pymysql, "connect", fake_connect)
    monkeypatch.setattr(config, "_platform_database_url", lambda: "mysql+pymysql://chromo:pw@db.local:3307/chromosome")
    saver = cg._mysql_checkpointer()
    assert seen["host"] == "db.local" and seen["port"] == 3307 and seen["user"] == "chromo" and seen["database"] == "chromosome" and seen["autocommit"] is True
    assert conn.ping.called  # setup() went through the re-connecting cursor
    assert any("checkpoint_migrations" in str(c) for c in cur.execute.call_args_list)
    n = conn.ping.call_count
    with saver._cursor():
        pass
    assert conn.ping.call_count == n + 1
    cg.close_chat_memory()
    assert conn.close.called
