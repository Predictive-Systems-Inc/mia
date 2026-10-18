"""Alembic migrations create exactly the tables in the models, plus the event triggers."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
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
