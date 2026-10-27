"""Alembic environment for Engismart's own tables. The app passes its connection (config.attributes["connection"]).
Our revisions are recorded in alembic_version_engismart, never in the platform's tables."""
from alembic import context

from services.engismart.db import VERSION_TABLE, Base
from services.engismart.images import catalog  # noqa: F401 - registers the picture table on the shared metadata

config = context.config


def run_migrations_online() -> None:
    connection = config.attributes["connection"]
    context.configure(connection=connection, target_metadata=Base.metadata, version_table=VERSION_TABLE,
                      compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
