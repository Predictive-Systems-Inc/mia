"""Sales supervisor due work on the tick: reminders, the missing list, the owner's report, the
morning message and the why question, each once per branch and business date."""

import datetime as dt
from collections.abc import Callable, Iterator

import pytest
from sqlmodel import Session, select

from mia.agents.sales_supervisor import MANIFEST, due, tools
from mia.agents.sales_supervisor.tools import CountIn, RecordCountsInput, SetTargetInput
from mia.channels import registry
from mia.channels.simulator import SimAdapter
from mia.core import orgconfig, store
from mia.core.models import (
    Actor,
    Branch,
    ChannelIdentity,
    ChannelOutbox,
    Client,
    Event,
    Job,
    Location,
    Message,
    Person,
    Thread,
    Visit,
)
from mia.core.orgconfig import ChannelConfig, OrgSettings, QuietHours
from mia.core.people import add_person
from mia.i18n import t
from mia.templates.retail.models import RetailBranchHours, RetailItem
from tests.test_sales_tools import deps_for

Ferinos = tuple[Branch, dict[str, Person]]
At = Callable[[int, int], dt.datetime]


def _notes(session: Session, person: Person | None = None) -> list[Message]:
    stmt = select(Message).where(Message.role == "notification")
    rows = [m for m in session.exec(stmt).all() if m.agent_id == MANIFEST.id]
    if person is None:
        return rows
    return [m for m in rows if _owner(session, m) == person.id]


def _owner(session: Session, message: Message) -> str:
    thread = session.get(Thread, message.thread_id)
    assert thread is not None
    return thread.person_id


def _report(session: Session, person: Person, quantity: int = 3) -> None:
    special = session.exec(select(RetailItem).where(RetailItem.name == "Special")).one().id
    args = RecordCountsInput(items=[CountIn(item_id=special, quantity=quantity)])
    tools.record_counts(deps_for(session, person), args, "c1")
    session.commit()


def _stall(session: Session) -> Branch:
    return session.exec(select(Branch).where(Branch.name == "Street stall")).one()


def _hours(session: Session, branch: Branch) -> list[RetailBranchHours]:
    stmt = select(RetailBranchHours).where(RetailBranchHours.branch_id == branch.id)
    return list(session.exec(stmt).all())


# ---- the pure "is it due" functions ---------------------------------------------------------


def test_windows_follow_the_branch_hours(session: Session, ferinos: Ferinos, manila_at: At) -> None:
    kiosk, _ = ferinos
    hours = _hours(session, kiosk)
    at = manila_at
    assert not due.closing_reminder(kiosk, hours, at(20, 29))
    assert due.closing_reminder(kiosk, hours, at(20, 30))
    assert not due.closing_reminder(kiosk, hours, at(21, 0))
    assert not due.missing_list(kiosk, hours, at(21, 29)) and due.missing_list(
        kiosk, hours, at(21, 30)
    )
    assert not due.owner_report(kiosk, hours, at(21, 59)) and due.owner_report(
        kiosk, hours, at(22, 0)
    )
    assert due.why_question(kiosk, hours, at(22, 0)) and not due.why_question(
        kiosk, hours, at(21, 30)
    )
    assert not due.morning_message(kiosk, hours, at(8, 59))
    assert due.morning_message(kiosk, hours, at(9, 0))
    assert not due.morning_message(kiosk, hours, at(10, 0))


def test_windows_fall_back_to_nine_to_nine_without_hours(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    kiosk, _ = ferinos
    assert due.closing_reminder(kiosk, [], manila_at(20, 45))
    assert due.morning_message(kiosk, [], manila_at(9, 15))


def test_good_day_beats_the_target_or_the_average_by_a_fifth() -> None:
    assert due.good_day(1001, 1000, None) and not due.good_day(1000, 1000, 1)
    assert due.good_day(1200, None, 1000) and not due.good_day(1199, None, 1000)
    assert not due.good_day(0, None, None)


# ---- closing reminders ----------------------------------------------------------------------


def test_reminder_goes_to_clerks_without_counts(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    _, people = ferinos
    _report(session, people["Ana"])
    due.run_due(session, manila_at(20, 35))  # the stall closed at 19:00: its own work runs too
    assert _notes(session, people["Ana"]) == []
    (note,) = _notes(session, people["Liza"])
    assert note.text == t("sales.reminder", "fil") and note.sender_id == "system"


def test_reminder_once_per_branch_and_day(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    assert due.run_due(session, manila_at(20, 35)) > 0
    assert due.run_due(session, manila_at(20, 50)) == 0
    marker = session.exec(select(Event).where(Event.action == "sales.reminder_sent")).one()
    assert marker.after is not None and marker.after["date"] == manila_at(20, 50).date().isoformat()


def test_reported_clerks_get_no_reminder(session: Session, ferinos: Ferinos, manila_at: At) -> None:
    _, people = ferinos
    _report(session, people["Ana"])
    _report(session, people["Liza"])
    due.run_due(session, manila_at(20, 35))
    assert _notes(session, people["Ana"]) == _notes(session, people["Liza"]) == []
    assert session.exec(select(Event).where(Event.action == "sales.reminder_sent")).first() is None


def test_reminder_only_to_clerks_on_shift_when_visits_exist(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    kiosk, people = ferinos
    at = manila_at(20, 35)
    system = Actor.system(kiosk.id)
    client = store.insert(session, Client(branch_id=kiosk.id, name="Mall"), system)
    place = Location(branch_id=kiosk.id, client_id=client.id, name="Kiosk", address="Mall")
    store.insert(session, place, system)
    job = store.insert(
        session,
        Job(
            branch_id=kiosk.id,
            location_id=place.id,
            name="Shift",
            recurrence="FREQ=DAILY",
            start_time="09:00",
            duration_minutes=720,
        ),
        system,
    )
    visit = Visit(
        branch_id=kiosk.id,
        job_id=job.id,
        location_id=place.id,
        date=at.date(),
        assigned_person_ids=[people["Ana"].id],
        planned_start=at.replace(hour=9),
        planned_end=at.replace(hour=21),
    )
    store.insert(session, visit, system)
    session.commit()
    due.run_due(session, at)
    assert len(_notes(session, people["Ana"])) == 1 and _notes(session, people["Liza"]) == []


@pytest.fixture
def quiet_sim(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The sim channel on, quiet hours 18:00 to 06:00 (undone before ferinos clears the cache)."""
    saved = dict(registry._adapters)
    registry._adapters.clear()
    registry.register(SimAdapter())
    org = OrgSettings(
        agents=[MANIFEST.id],
        channels={"sim": ChannelConfig(enabled=True)},
        quiet_hours=QuietHours(start=dt.time(18), end=dt.time(6)),
    )
    with monkeypatch.context() as m:
        m.setattr(orgconfig, "load", lambda org_name=None: org)
        yield
    registry._adapters.clear()
    registry._adapters.update(saved)


def test_reminder_waits_for_quiet_hours(
    session: Session, ferinos: Ferinos, manila_at: At, quiet_sim: None
) -> None:
    _, people = ferinos
    pao = people["Pao"]
    identity = ChannelIdentity(
        branch_id=pao.branch_id, person_id=pao.id, channel="sim", address="639171234567"
    )
    store.insert(session, identity, Actor.person(pao), action="channel.linked")
    session.commit()
    at = manila_at(18, 35)  # the stall closes 19:00
    assert due.run_due(session, at) > 0
    stmt = select(ChannelOutbox).where(ChannelOutbox.person_id == pao.id)
    (row,) = [r for r in session.exec(stmt) if r.status == "queued"]
    morning = (at + dt.timedelta(days=1)).replace(hour=6, minute=0)
    assert row.send_after == morning.astimezone(dt.UTC)


# ---- the missing list -----------------------------------------------------------------------


def test_missing_list_names_who_did_not_report(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    _, people = ferinos
    _report(session, people["Ana"])
    due.run_due(session, manila_at(21, 30))
    (note,) = _notes(session, people["Marites"])
    assert note.text == t("sales.missing", "fil", names=people["Liza"].name)
    assert _notes(session, people["Ana"]) == [] and _notes(session, people["Liza"]) == []


def test_no_missing_list_when_everyone_reported(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    _, people = ferinos
    _report(session, people["Ana"])
    _report(session, people["Liza"])
    due.run_due(session, manila_at(21, 30))
    assert _notes(session, people["Marites"]) == []


# ---- the owner's report ---------------------------------------------------------------------


def test_owner_report_compares_with_last_week_and_the_average(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    _, people = ferinos
    _report(session, people["Ana"], quantity=40)
    due.run_due(session, manila_at(22, 0))
    rosa = _notes(session, people["Rosa"])
    assert len(rosa) == 2  # one report per branch
    kiosk_report = next(n for n in rosa if "Mall kiosk" in n.text)
    assert "40 Special" in kiosk_report.text and "₱1,800.00" in kiosk_report.text
    assert "%" in kiosk_report.text and "4-week average" in kiosk_report.text
    stall_report = next(n for n in rosa if "Street stall" in n.text)
    assert stall_report.text == t("sales.today.empty", "en", branch="Street stall")
    assert due.run_due(session, manila_at(22, 30)) == 0


def test_report_reaches_every_owner_and_admin_once_in_their_language(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    _, people = ferinos
    stall = _stall(session)
    admin = add_person(
        session, Actor.system(stall.id), branch_id=stall.id, name="Mikko", roles=["admin"]
    )
    session.commit()
    _report(session, people["Ana"])
    due.run_due(session, manila_at(22, 0))
    finnish = [n.text for n in _notes(session, admin)]
    assert len(finnish) == 2 and any(
        text.startswith("Päivän päätös, Mall kiosk") for text in finnish
    )


# ---- the morning message --------------------------------------------------------------------


def test_morning_message_at_opening(session: Session, ferinos: Ferinos, manila_at: At) -> None:
    _, people = ferinos
    sent = due.run_due(session, manila_at(9, 5))
    kiosk_people = {people[n].id for n in ("Ana", "Liza", "Marites")}
    owners = {_owner(session, n) for n in _notes(session)}
    assert kiosk_people <= owners and people["Rosa"].id not in owners
    assert sent == 3  # the stall opened at 06:00, past its morning window
    (ana,) = _notes(session, people["Ana"])
    assert ana.text.startswith("Good morning") and "₱" in ana.text
    assert due.run_due(session, manila_at(9, 20)) == 0


# ---- the why question -----------------------------------------------------------------------


def test_why_question_after_beating_the_target(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    kiosk, people = ferinos
    today = manila_at(15, 0).date()
    rosa = deps_for(session, people["Rosa"])
    tools.set_target(rosa, SetTargetInput(period="day", starts_on=today, amount=10000), "t1")
    session.commit()
    _report(session, people["Ana"], quantity=3)  # 135.00 against 100.00
    due.run_due(session, manila_at(22, 0))
    why = t("sales.why", people["Ana"].language)
    assert [n.text for n in _notes(session, people["Ana"])] == [why]
    assert _notes(session, people["Liza"]) == []  # Liza did not report
    from mia.chat.service import _last_mia

    (ana_note,) = _notes(session, people["Ana"])
    thread = session.get(Thread, ana_note.thread_id)
    assert thread is not None and _last_mia(session, thread, questions=True) == ana_note
    marker = session.exec(select(Event).where(Event.action == "sales.why_asked")).one()
    assert marker.entity_id == kiosk.id and len(marker.after["message_ids"]) == 1
    assert due.run_due(session, manila_at(22, 30)) == 0


def test_no_why_question_below_the_target(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    _, people = ferinos
    _report(session, people["Ana"], quantity=1)  # 45.00, far below the month share
    due.run_due(session, manila_at(22, 0))
    why = t("sales.why", people["Ana"].language)
    assert why not in [n.text for n in _notes(session, people["Ana"])]
