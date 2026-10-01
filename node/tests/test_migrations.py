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


def test_upgrade_from_1_0_keeps_employee_data() -> None:
    """Availability and work limits move from the cleaning template to core with their rows."""
    cfg = _alembic_config()
    command.upgrade(cfg, "0001")
    rows = {
        "organisation": "('O', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'Org', 'FI', 'fi')",
        "branch": "('B', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'O', 'Hki', 'Europe/Helsinki')",
        "person": "('P', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'B', 'Pia', 'active', "
        "'[\"staff\"]', '[]', 'employee', 'fi')",
        "cleaning_availability": "('A', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'B', 'P', 0, '06:00', '20:00')",
        "cleaning_work_limits": "('W', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'B', 'P', 600, 2400)",
    }
    with get_engine().begin() as conn:
        for table, values in rows.items():
            conn.execute(text(f"INSERT INTO {table} VALUES {values}"))
    command.upgrade(cfg, "head")
    with get_engine().connect() as conn:
        assert conn.execute(text('SELECT start, "end" FROM availability')).one() == (
            "06:00",
            "20:00",
        )
        assert conn.execute(text("SELECT max_weekly_minutes FROM work_limits")).scalar() == 2400
        person = conn.execute(text("SELECT home_address, accepts_calls FROM person")).one()
        assert person == ("", 1)
