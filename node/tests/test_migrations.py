"""Alembic migrations create exactly the tables in the models, plus the event triggers."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.util import CommandError
from sqlalchemy import inspect, text

from mia.cli import _alembic_config
from mia.core.db import get_engine
from mia.schema import metadata


def test_upgrade_matches_models_and_adds_triggers() -> None:
    command.upgrade(_alembic_config(), "head")
    engine = get_engine()
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names()) - {"alembic_version"}
        assert tables == set(metadata.tables)
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
        assert diff == [], diff
        triggers = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))
        }
        assert {"events_no_update", "events_no_delete"} <= triggers
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_downgrade_removes_everything() -> None:
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    with get_engine().connect() as conn:
        assert set(inspect(conn).get_table_names()) == {"alembic_version"}


def test_a_database_from_before_the_squash_fails_loudly() -> None:
    """Revisions 0001 to 0008 were squashed (ADR 014); a database still stamped with one of them
    must be rebuilt, not silently taken as current."""
    with get_engine().begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    with pytest.raises(CommandError):
        command.upgrade(_alembic_config(), "head")
