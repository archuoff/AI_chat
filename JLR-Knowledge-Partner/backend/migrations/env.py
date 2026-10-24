"""Alembic environment. The app passes its own connection (config.attributes["connection"]); the `alembic` command
line builds one from DATABASE_URL."""
from logging.config import fileConfig

from alembic import context

import app.images.catalog  # noqa: F401 - registers the picture table on the shared metadata
from app.auth.db import Base, make_engine
from app.config import get_settings

config = context.config
target_metadata = Base.metadata


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                      render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:  # started by the app: no logging reconfiguration
        _run(connection)
        return
    if config.config_file_name:
        fileConfig(config.config_file_name)
    with make_engine(get_settings().db_url).connect() as conn:
        _run(conn)
        conn.commit()


run_migrations_online()
