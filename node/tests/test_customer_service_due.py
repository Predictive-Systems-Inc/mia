"""Customer service due work on the tick (scenario 10): the opening digest of the day's pickups
to clerks and supervisors once per branch and day, and pickup reminders inside the customer's
24-hour window and outside quiet hours, once per order and pickup time."""

import datetime as dt
import functools

import pytest
from sqlmodel import Session, col, select

from mia.agents.base import call_tool
from mia.agents.customer_service import due, tools
from mia.agents.customer_service.models import Order
from mia.core import orgconfig, store
from mia.core.ids import new_id
from mia.core.models import Actor, Approval, Branch, Event, Message, Person, Thread
from mia.i18n import t
from tests.conftest import MNL, TODAY, Shop
from tests.test_customer_service_tools import (
    BINDING,
    customer_by_lang,
    customer_deps,
    last_out,
    order_input,
    order_of,
    seeded_order,
)


def last_notification(session: Session, person: Person) -> Message:
    row = session.exec(
        select(Message)
        .join(Thread, col(Message.thread_id) == col(Thread.id))
        .where(Thread.person_id == person.id)
        .where(Message.agent_id == "customer_service")
        .order_by(col(Message.id).desc())
    ).first()
    assert row is not None, "no notification"
    return row


def markers(session: Session, action: str) -> list[Event]:
    return list(session.exec(select(Event).where(Event.action == action)).all())


def _set(session: Session, row: object, changes: dict[str, object]) -> None:
    store.update(session, row, changes, Actor.system(getattr(row, "branch_id")))  # noqa: B009
    session.commit()


def cancel_seeded(session: Session) -> None:
    _set(session, seeded_order(session, "fil"), {"status": "cancelled"})


def window(session: Session, lang: str, at: dt.datetime) -> None:
    """The customer last wrote at `at`."""
    _set(session, customer_by_lang(session, lang), {"last_inbound_at": at})


def move_seeded(session: Session, hhmm: str) -> None:
    pickup = dt.datetime.combine(TODAY, dt.time.fromisoformat(hhmm), MNL)
    _set(session, seeded_order(session, "fil"), {"pickup_at": pickup})


def stall_order_at(session: Session, hhmm: str) -> None:
    """Mila's order moves to the street stall (opens 06:00) for tomorrow at hhmm, and she
    wrote at 05:00 tomorrow, so her window is open then."""
    stall = session.exec(select(Branch).where(Branch.name == "Street stall")).one()
    tomorrow = TODAY + dt.timedelta(days=1)
    pickup = dt.datetime.combine(tomorrow, dt.time.fromisoformat(hhmm), MNL)
    _set(session, seeded_order(session, "fil"), {"pickup_at": pickup, "branch_id": stall.id})
    window(session, "fil", dt.datetime.combine(tomorrow, dt.time(5), MNL))


# ---- what is due (pure) ---------------------------------------------------------------------


def test_the_digest_is_due_only_in_the_first_hour_after_opening(cs: Shop, session: Session) -> None:
    hours: due.Hours = []  # no rows: open every day 09:00 to 21:00
    at = [cs.pin(8, 59), cs.pin(9, 0), cs.pin(9, 59), cs.pin(10, 0)]
    assert [due.digest_due(cs.kiosk, hours, now) for now in at] == [None, TODAY, TODAY, None]


def test_a_reminder_is_due_in_the_hour_before_pickup_outside_quiet_hours(
    cs: Shop, session: Session
) -> None:
    order = seeded_order(session, "fil")  # 15:00
    times = [cs.pin(13, 59), cs.pin(14, 0), cs.pin(14, 59), cs.pin(15, 0)]
    assert [due.reminder_due(order, now, quiet=False) for now in times] == [
        False,
        True,
        True,
        False,
    ]
    assert not due.reminder_due(order, cs.pin(14, 30), quiet=True)


# ---- the opening digest -------------------------------------------------------------------


def test_the_opening_digest_lists_todays_orders(cs: Shop, session: Session) -> None:
    assert due.run_due(session, cs.pin(9, 10)) == 1
    text = last_notification(session, cs.people["Liza"]).text
    assert text == t("cs.digest", "fil", orders="15:00 Mila R. (Classic x10)")
    assert "Mila R." in last_notification(session, cs.people["Marites"]).text
    (marker,) = markers(session, due.DIGEST)
    assert marker.after is not None and marker.after["date"] == TODAY.isoformat()


def test_the_digest_is_sent_once_per_branch_and_day(cs: Shop, session: Session) -> None:
    due.run_due(session, cs.pin(9, 10))
    assert due.run_due(session, cs.pin(9, 40)) == 0


def test_no_digest_without_orders_today(cs: Shop, session: Session) -> None:
    cancel_seeded(session)
    assert due.run_due(session, cs.pin(9, 10)) == 0 and not markers(session, due.DIGEST)


def test_the_digest_names_no_customer_in_the_event_log(cs: Shop, session: Session) -> None:
    due.run_due(session, cs.pin(9, 10))
    sent = markers(session, "notification.sent")
    assert sent and all("Mila" not in str(e.after) for e in sent)


# ---- pickup reminders ---------------------------------------------------------------------


def test_a_pickup_reminder_respects_the_window(cs: Shop, session: Session) -> None:
    assert due.run_due(session, cs.pin(14, 5)) == 0
    assert markers(session, due.SKIPPED)  # Mila's window is closed
    assert not markers(session, due.REMINDER)
    window(session, "fil", dt.datetime.combine(TODAY, dt.time(13, 5), MNL))
    move_seeded(session, "16:00")  # a moved pickup is reminded again
    assert due.run_due(session, cs.pin(15, 5)) == 1
    assert last_out(session).text == t("cs.reminder", "fil", time="16:00")
    assert last_out(session).status == "queued"  # public.send_pending sends it on the tick
    assert due.run_due(session, cs.pin(15, 20)) == 0  # once per order and pickup time


def test_a_pickup_reminder_waits_for_quiet_hours(cs: Shop, session: Session) -> None:
    stall_order_at(session, "06:30")
    due.run_due(session, cs.pin(5, 40, days=1))
    assert not markers(session, due.REMINDER) and not markers(session, due.SKIPPED)
    due.run_due(session, cs.pin(6, 1, days=1))
    assert markers(session, due.REMINDER)


def test_no_reminder_for_an_order_not_open(cs: Shop, session: Session) -> None:
    window(session, "fil", dt.datetime.combine(TODAY, dt.time(13), MNL))
    cancel_seeded(session)
    assert due.run_due(session, cs.pin(14, 30)) == 0
    assert not markers(session, due.REMINDER) and not markers(session, due.SKIPPED)
    assert session.exec(select(Order).where(Order.status == "cancelled")).first()


def test_nothing_runs_for_an_organisation_without_the_customer_service(
    cs: Shop, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    none = orgconfig.OrgSettings(agents=[])
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: none))
    assert due.run_due(session, cs.pin(9, 10)) == 0 and not markers(session, due.DIGEST)


# ---- waiting orders nobody decided -----------------------------------------------------------


def waiting_on(cs: Shop, session: Session, pickup: dt.datetime) -> Approval:
    """Mila's order recorded waiting for a pickup at `pickup`; its approval."""
    deps, args = customer_deps(cs, session), order_input(session, pickup_at=pickup)
    out = call_tool(deps, BINDING[tools.PLACE_ORDER], args, new_id())
    tools.record_waiting(deps, args, str(out["approval_id"]))
    session.commit()
    approval = session.get(Approval, out["approval_id"])
    assert approval is not None
    return approval


def test_a_waiting_order_whose_pickup_passed_is_closed_and_the_customer_told(
    cs: Shop, session: Session
) -> None:
    a = waiting_on(cs, session, dt.datetime.combine(TODAY, dt.time(16), MNL))
    due.run_due(session, cs.pin(16, 5))
    session.refresh(a)
    assert (order_of(a).status, a.status, a.reason) == ("rejected", "expired", "past")
    assert last_out(session).text == t("cs.order_rejected.other", "fil", time="16:00")
    due.run_due(session, cs.pin(16, 20))  # the status change is the guard: handled once
    assert len(markers(session, "customer_service.order_rejected")) == 1
    assert len(markers(session, "approval.expired")) == 1


def test_a_waiting_order_past_its_approval_ttl_is_closed(cs: Shop, session: Session) -> None:
    pickup = dt.datetime.combine(TODAY + dt.timedelta(days=2), dt.time(16), MNL)
    a = waiting_on(cs, session, pickup)
    due.run_due(session, cs.pin(9, 55, days=1))  # the approval is good until 10:00 tomorrow
    assert order_of(a).status == "waiting"
    due.run_due(session, cs.pin(10, 5, days=1))
    session.refresh(a)
    assert (order_of(a).status, a.status, a.reason) == ("rejected", "expired", "timeout")
    assert last_out(session).text == t("cs.order_rejected.other", "fil", time="16:00")
    due.run_due(session, cs.pin(10, 30, days=1))
    assert len(markers(session, "customer_service.order_rejected")) == 1
