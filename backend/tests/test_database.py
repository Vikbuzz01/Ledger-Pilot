"""Explicit SQL Server connectivity and migration verification (never SQLite)."""

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from alembic import command
from app.core.config import Settings
from app.db.session import get_engine


@pytest.mark.database
def test_sql_server_connectivity_and_migration_state() -> None:
    try:
        Settings()
    except Exception as exc:
        pytest.fail(f"DATABASE_URL is unset or invalid; SQL Server verification is blocked: {exc}")

    try:
        with get_engine().connect() as connection:
            version = connection.execute(text("SELECT @@VERSION")).scalar_one()
            assert "Microsoft SQL Server" in version

        config = Config("alembic.ini")
        command.upgrade(config, "head")
        with get_engine().connect() as connection:
            current_revision = MigrationContext.configure(connection).get_current_revision()
        expected_revision = ScriptDirectory.from_config(config).get_current_head()
        assert current_revision == expected_revision, (
            f"Database revision {current_revision!r} does not match application head "
            f"{expected_revision!r}."
        )
    except (SQLAlchemyError, OSError) as exc:
        pytest.fail(f"SQL Server connectivity or Alembic migration verification failed: {exc}")
