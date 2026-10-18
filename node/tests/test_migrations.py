"""Alembic migrations create exactly the tables in the models, plus the event triggers."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, inspect, text

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


def test_upgrade_from_1_2_keeps_link_codes_and_attempts() -> None:
    """Link codes and attempts move to auth_codes and auth_attempts with their rows."""
    cfg = _alembic_config()
    command.upgrade(cfg, "0003")
    ts = "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'"
    with get_engine().begin() as conn:
        conn.execute(text(f"INSERT INTO organisation VALUES ('O', {ts}, 'Org', 'FI', 'fi')"))
        conn.execute(text(f"INSERT INTO branch VALUES ('B', {ts}, 'O', 'Hki', 'Europe/Helsinki')"))
        conn.execute(
            text(
                f"INSERT INTO person VALUES ('P', {ts}, 'B', 'Pia', 'active', '[\"staff\"]', '[]', "
                "'employee', 'fi', '', NULL, NULL, 1)"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO channel_link_codes VALUES ('C', {ts}, 'B', 'P', 'abc', 'invite', "
                "'2026-01-08T00:00:00+00:00', NULL, 'P')"
            )
        )
        conn.execute(
            text(f"INSERT INTO channel_link_attempts VALUES ('A', {ts}, 'whatsapp', '358401', 0)")
        )
    command.upgrade(cfg, "head")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT purpose, address, tries FROM auth_codes")).one() == (
            "invite",
            None,
            0,
        )
        assert conn.execute(text("SELECT kind, key, ok FROM auth_attempts")).one() == (
            "link_code",
            "whatsapp:358401@-",
            0,
        )
        tables = set(inspect(conn).get_table_names())
        assert {"auth_credentials", "auth_devices", "auth_sessions", "auth_clients"} <= tables
        assert not {"channel_link_codes", "channel_link_attempts"} & tables
    command.downgrade(cfg, "0003")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT channel, address FROM channel_link_attempts")).one() == (
            "whatsapp",
            "358401",
        )


RENAMED = {
    "dispatcher_absences": "absences",
    "dispatcher_cover_requests": "cover_requests",
    "dispatcher_timesheets": "timesheets",
    "dispatcher_site_problems": "incidents",
    "dispatcher_checklist_ticks": "cleaning_checklist_ticks",
}


def _insert(conn: Connection, table: str, **cols: object) -> None:
    names = ", ".join(cols)
    marks = ", ".join(f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO {table} ({names}) VALUES ({marks})"), cols)


def _seed_0007(conn: Connection) -> None:
    """One row in each of the five old tables, plus rows that name the old agent id."""
    ts = "2026-01-01T00:00:00+00:00"
    base = {"created_at": ts, "updated_at": ts}
    b = {**base, "branch_id": "B"}
    _insert(conn, "organisation", **base, id="O", name="Org", country="FI", default_language="fi")
    _insert(
        conn, "branch", **base, id="B", organisation_id="O", name="Hki", timezone="Europe/Helsinki"
    )
    _insert(
        conn, "person", **b, id="P", name="Pia", status="active", roles='["staff"]', skills="[]",
        engagement_type="employee", language="fi", home_address="", home_lat=None,
        home_lon=None, accepts_calls=1,
    )  # fmt: skip
    _insert(conn, "client", **b, id="C", name="Client", type="business", status="active")
    _insert(
        conn, "location", **b, id="L", client_id="C", name="Site", address="x", geofence="{}",
        instructions="", access_notes="",
    )  # fmt: skip
    _insert(
        conn, "job", **b, id="J", location_id="L", name="Daily", recurrence="DAILY",
        start_time="08:00", duration_minutes=60, required_skills="[]", resources="[]",
    )  # fmt: skip
    _insert(
        conn, "visit", **b, id="V", job_id="J", location_id="L", date="2026-01-02",
        assigned_person_ids='["P"]', planned_start=ts, planned_end=ts, status="planned",
        proof_refs="[]",
    )  # fmt: skip
    _insert(
        conn, "dispatcher_absences", **b, id="A", person_id="P", date="2026-01-02",
        reason="sick", partial_day=None, reported_by="P",
    )  # fmt: skip
    _insert(
        conn, "dispatcher_cover_requests", **b, id="R", visit_id="V", candidate_id="P",
        replace_person_ids="[]", queue="[]", instructed_by="P", approval_id=None,
        status="open", stage="asked", next_action_at=None,
    )  # fmt: skip
    _insert(
        conn, "dispatcher_timesheets", **b, id="T", visit_id="V", person_id="P", date="2026-01-02",
        start=ts, end=ts, minutes=60, source="check_in", status="draft", entered_by="P", note="",
    )  # fmt: skip
    _insert(
        conn, "dispatcher_site_problems", **b, id="S", visit_id="V", person_id="P", kind="other",
        text="leak", status="open",
    )  # fmt: skip
    _insert(
        conn, "dispatcher_checklist_ticks", **b, id="K", visit_id="V", item="floors",
        ticked_by="P", ticked_at=ts,
    )  # fmt: skip
    _insert(conn, "chat_threads", **b, id="H", person_id="P", agent_id="dispatcher", title="t")
    _insert(
        conn, "chat_messages", **b, id="M", thread_id="H", role="assistant", sender_id="agent.dispatcher",
        text="hi", blocks="[]", agent_id="dispatcher", model_messages="[]",
    )  # fmt: skip
    _insert(
        conn, "approval", **b, id="G", type="dispatcher.cover_override", requester_type="agent",
        requester_id="agent.dispatcher", subject_type="visit", subject_id="V", summary="s",
        evidence="{}", approver_roles="[]", channel="any", escalate_to="[]", status="pending",
    )  # fmt: skip


def _index_names(conn: Connection, table: str) -> set[str]:
    return {str(i["name"]) for i in inspect(conn).get_indexes(table)}


def test_upgrade_from_1_3_keeps_agent_rows_in_shared_tables() -> None:
    """The dispatcher's tables become shared (data standard 1.4) with their rows and indexes,
    and ordinary rows that name the old agent follow the rename (events stay as written)."""
    cfg = _alembic_config()
    command.upgrade(cfg, "0007")
    with get_engine().begin() as conn:
        _seed_0007(conn)
        old_indexes = {old: _index_names(conn, old) for old in RENAMED}
    assert all(old_indexes.values())
    command.upgrade(cfg, "head")
    with get_engine().connect() as conn:
        tables = set(inspect(conn).get_table_names())
        assert set(RENAMED.values()) <= tables
        assert not set(RENAMED) & tables
        for old, new in RENAMED.items():
            assert conn.execute(text(f"SELECT count(*) FROM {new}")).scalar() == 1
            expected = {n.replace(f"ix_{old}_", f"ix_{new}_", 1) for n in old_indexes[old]}
            assert _index_names(conn, new) == expected
            assert all(n.startswith(f"ix_{new}_") for n in expected)
        assert conn.execute(text("SELECT reason FROM absences")).scalar() == "sick"
        assert (
            conn.execute(text("SELECT agent_id FROM chat_threads")).scalar() == "shift_supervisor"
        )
        assert conn.execute(text("SELECT agent_id FROM chat_messages")).scalar() == (
            "shift_supervisor"
        )
        assert conn.execute(text("SELECT sender_id FROM chat_messages")).scalar() == (
            "agent.shift_supervisor"
        )
        assert conn.execute(text("SELECT type, requester_id FROM approval")).one() == (
            "shift_supervisor.cover_override",
            "agent.shift_supervisor",
        )
    command.downgrade(cfg, "0007")
    with get_engine().connect() as conn:
        tables = set(inspect(conn).get_table_names())
        assert set(RENAMED) <= tables
        assert not set(RENAMED.values()) & tables
        for old in RENAMED:
            assert conn.execute(text(f"SELECT count(*) FROM {old}")).scalar() == 1
            assert _index_names(conn, old) == old_indexes[old]
        assert conn.execute(text("SELECT reason FROM dispatcher_absences")).scalar() == "sick"
        assert conn.execute(text("SELECT agent_id FROM chat_threads")).scalar() == "dispatcher"
        assert conn.execute(text("SELECT agent_id FROM chat_messages")).scalar() == "dispatcher"
        assert conn.execute(text("SELECT sender_id FROM chat_messages")).scalar() == (
            "agent.dispatcher"
        )
        assert conn.execute(text("SELECT type, requester_id FROM approval")).one() == (
            "dispatcher.cover_override",
            "agent.dispatcher",
        )
