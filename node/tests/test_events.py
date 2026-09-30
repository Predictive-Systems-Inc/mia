"""Events log: append-only and hash-chained (required negative tests)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlmodel import Session, select

from mia.core import events
from mia.core.events import AppendOnlyViolation, verify_chain
from mia.core.models import Actor, Event


def _emit(session: Session, n: int, branch_id: str = "B1") -> None:
    actor = Actor.system(branch_id)
    for i in range(n):
        events.emit(session, "test.happened", ("thing", str(i)), None, {"i": i}, actor)


def test_chain_verifies_after_100_inserts(session: Session) -> None:
    _emit(session, 100)
    session.commit()
    rows = session.exec(select(Event)).all()
    assert len(rows) == 100
    assert rows[0].prev_hash == events.GENESIS_HASH
    assert verify_chain(session)


def test_orm_update_of_event_raises(session: Session) -> None:
    _emit(session, 3)
    session.commit()
    row = session.exec(select(Event)).first()
    assert row is not None
    row.action = "tampered"
    session.add(row)
    with pytest.raises(AppendOnlyViolation):
        session.flush()


def test_orm_delete_of_event_raises(session: Session) -> None:
    _emit(session, 3)
    session.commit()
    row = session.exec(select(Event)).first()
    session.delete(row)
    with pytest.raises(AppendOnlyViolation):
        session.flush()


@pytest.mark.parametrize("sql", ["UPDATE events SET action = 'x'", "DELETE FROM events"])
def test_sql_update_or_delete_is_aborted_by_trigger(session: Session, sql: str) -> None:
    _emit(session, 2)
    session.commit()
    with pytest.raises(DatabaseError, match="append-only"):
        session.exec(text(sql))  # type: ignore[call-overload]


def test_tampering_breaks_the_chain(session: Session) -> None:
    _emit(session, 5)
    session.commit()
    session.exec(text("DROP TRIGGER events_no_update"))  # type: ignore[call-overload]
    session.exec(text("UPDATE events SET after = '{\"i\": 99}' WHERE rowid = 3"))  # type: ignore[call-overload]
    session.commit()
    session.expire_all()
    assert not verify_chain(session)


def test_event_records_actor_and_on_behalf_of(session: Session) -> None:
    from mia.core.models import Principal

    person = Principal(type="person", id="P1", roles=["staff"])
    actor = Actor(principal=person, branch_id="B1").as_agent("agent.dispatcher")
    ev = events.emit(session, "x", ("thing", "1"), None, None, actor, tool_call_id="call-1")
    assert (ev.actor_type, ev.actor_id, ev.on_behalf_of) == ("agent", "agent.dispatcher", "P1")
    assert ev.tool_call_id == "call-1"
