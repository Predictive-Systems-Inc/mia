import datetime as dt
from collections.abc import Callable
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.sales_supervisor import MANIFEST, tools
from mia.agents.sales_supervisor.models import SalesCount, SalesNote, SalesTarget
from mia.agents.sales_supervisor.tools import (
    CorrectCountInput,
    CountIn,
    PeriodReportInput,
    RecordCountsInput,
    RecordNoteInput,
    SetTargetInput,
    TodayInput,
)
from mia.agents.shift_supervisor import alerts
from mia.core import store
from mia.core.models import Actor, Branch, Event, Message, Person, Thread
from mia.core.rbac import PermissionDenied
from mia.templates.retail.models import RetailBranchHours, RetailItem

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")


@pytest.fixture(autouse=True)
def afternoon(manila_at: Callable[[int, int], dt.datetime]) -> dt.datetime:
    """Before closing, so the business date is never ambiguous unless a test says so."""
    return manila_at(15, 0)


def today() -> dt.date:
    return dt.datetime.now(MNL).date()


def deps_for(session: Session, person: Person) -> AgentDeps:
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=today(),
        lang=person.language or "en",
        manifest=MANIFEST,
    )


def item(session: Session, name: str) -> str:
    return session.exec(select(RetailItem).where(RetailItem.name == name)).one().id


def stall(session: Session) -> Branch:
    return session.exec(select(Branch).where(Branch.name == "Street stall")).one()


def counts(session: Session, person: Person, day: dt.date) -> list[SalesCount]:
    stmt = select(SalesCount).where(SalesCount.reported_by == person.id)
    return list(session.exec(stmt.where(SalesCount.business_date == day)).all())


def test_record_counts_writes_rows_and_events(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    special, classic = item(session, "Special"), item(session, "Classic")
    args = RecordCountsInput(
        items=[CountIn(item_id=special, quantity=3), CountIn(item_id=classic, quantity=5)]
    )
    out = tools.record_counts(deps_for(session, people["Ana"]), args, "c1")
    assert out.day_total == 3 * 4500 + 5 * 4000 and out.currency == "PHP"
    assert out.business_date == today() and out.target_share is not None
    rows = counts(session, people["Ana"], today())
    assert {(r.item_id, r.quantity, r.amount) for r in rows} == {
        (special, 3, 13500),
        (classic, 5, 20000),
    }
    assert len(session.exec(select(Event).where(Event.action == "sales.counted")).all()) == 2


def test_an_unknown_item_is_refused(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = RecordCountsInput(items=[CountIn(item_id="nope", quantity=1)])
    with pytest.raises(LookupError):
        tools.record_counts(deps_for(session, people["Ana"]), args, "c1")


def test_a_correction_supersedes_only_the_reporters_last_count(
    session: Session, ferinos: Ferinos
) -> None:
    _, people = ferinos
    ana, liza = people["Ana"], people["Liza"]
    special = item(session, "Special")
    for person, quantity in ((ana, 3), (liza, 2)):
        args = RecordCountsInput(items=[CountIn(item_id=special, quantity=quantity)])
        tools.record_counts(deps_for(session, person), args, "c1")
    out = tools.correct_count(
        deps_for(session, ana), CorrectCountInput(item_id=special, quantity=4), "c2"
    )
    assert (out.previous_quantity, out.corrected.quantity) == (3, 4)
    stmt = select(SalesCount).where(SalesCount.item_id == special)
    rows = session.exec(stmt.where(SalesCount.business_date == today())).all()
    live = [r for r in rows if r.superseded_by is None]
    assert {(r.reported_by, r.quantity) for r in live} == {(ana.id, 4), (liza.id, 2)}
    assert session.exec(select(Event).where(Event.action == "sales.corrected")).one()
    (shown,) = tools.today(deps_for(session, ana), TodayInput(), "c3").branches
    assert [(i.quantity, i.amount) for i in shown.items if i.item_id == special] == [(6, 27000)]


def test_a_correction_without_a_count_is_refused(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = CorrectCountInput(item_id=item(session, "Kape"), quantity=1)
    with pytest.raises(LookupError):
        tools.correct_count(deps_for(session, people["Liza"]), args, "c1")


def test_a_clerk_reads_only_their_branch(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    with pytest.raises(PermissionDenied):
        tools.today(deps_for(session, people["Ana"]), TodayInput(branch_id=stall(session).id), "c")


def test_the_owner_reads_another_branch(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    (out,) = tools.today(
        deps_for(session, people["Rosa"]), TodayInput(branch_id=stall(session).id), "c"
    ).branches
    assert out.branch == "Street stall" and out.total == 0 and out.target_share is not None


def test_a_clerk_cannot_set_a_target(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = SetTargetInput(period="day", starts_on=today(), amount=350000)
    with pytest.raises(PermissionDenied):
        tools.set_target(deps_for(session, people["Ana"]), args, "c4")


def test_call_tool_refuses_a_clerk_the_report(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    binding = next(b for b in tools.BINDINGS if b.tool_id.endswith(".period_report"))
    args = PeriodReportInput(start=today(), end=today())
    out = call_tool(deps_for(session, people["Ana"]), binding, args, "c1")
    assert out["status"] == "denied"


def test_a_supervisor_sets_their_branch_target_and_today_compares(
    session: Session, ferinos: Ferinos
) -> None:
    _, people = ferinos
    args = SetTargetInput(period="day", starts_on=today(), amount=350000)
    out = tools.set_target(deps_for(session, people["Marites"]), args, "c5")
    assert (out.period, out.amount, out.currency) == ("day", 350000, "PHP")
    assert [session.get(SalesTarget, i) is not None for i in out.target_ids] == [True]
    assert session.exec(select(Event).where(Event.action == "sales.target_set")).one()
    count = RecordCountsInput(items=[CountIn(item_id=item(session, "Box of 4"), quantity=10)])
    tools.record_counts(deps_for(session, people["Ana"]), count, "c6")
    (shown,) = tools.today(deps_for(session, people["Ana"]), TodayInput(), "c7").branches
    assert shown.target_share == 350000 and shown.total == 160000
    assert shown.percent == round((160000 - 350000) * 100 / 350000)


def test_an_owners_day_target_wins_over_a_supervisors(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    rosa = deps_for(session, people["Rosa"])
    tools.set_target(rosa, SetTargetInput(period="day", starts_on=today(), amount=500000), "c1")
    marites = deps_for(session, people["Marites"])
    tools.set_target(marites, SetTargetInput(period="day", starts_on=today(), amount=1000), "c2")
    assert tools.today(marites, TodayInput(), "c3").branches[0].target_share == 500000


def test_a_supervisor_cannot_set_another_branchs_target(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = SetTargetInput(period="day", starts_on=today(), amount=1, branch_id=stall(session).id)
    with pytest.raises(PermissionDenied):
        tools.set_target(deps_for(session, people["Marites"]), args, "c1")


def test_period_report_best_day(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    start = today() - dt.timedelta(days=13)
    args = PeriodReportInput(start=start, end=today())
    out = tools.period_report(deps_for(session, people["Rosa"]), args, "c7")
    stmt = select(SalesCount).where(col(SalesCount.business_date) >= start)
    kiosk = people["Rosa"].branch_id
    rows = [r for r in session.exec(stmt) if r.branch_id == kiosk]
    by_day: dict[dt.date, int] = {}
    for r in rows:
        by_day[r.business_date] = by_day.get(r.business_date, 0) + r.amount
    assert out.total == sum(by_day.values()) and out.currency == "PHP"
    assert out.best_day == max(by_day, key=lambda d: by_day[d])
    assert {r.branch for r in out.rows} == {"Mall kiosk"} and len(out.rows) == 8


def test_period_report_for_all_branches_and_one_item(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = PeriodReportInput(
        start=today() - dt.timedelta(days=13),
        end=today(),
        branch_id="all",
        item_id=item(session, "Ube"),
    )
    out = tools.period_report(deps_for(session, people["Rosa"]), args, "c1")
    assert {r.branch for r in out.rows} == {"Mall kiosk", "Street stall"}
    assert {r.item for r in out.rows} == {"Ube"}


def test_a_supervisor_cannot_report_all_branches(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = PeriodReportInput(start=today(), end=today(), branch_id="all")
    with pytest.raises(PermissionDenied):
        tools.period_report(deps_for(session, people["Marites"]), args, "c1")


def test_record_note_stores_the_answer(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = RecordNoteInput(text="maraming tao sa mall", themes=["event"])
    out = tools.record_note(deps_for(session, people["Ana"]), args, "c8")
    note = session.get(SalesNote, out.note_id)
    assert note is not None and note.text == "maraming tao sa mall" and note.themes == ["event"]
    assert note.person_id == people["Ana"].id and out.business_date == today()
    assert session.exec(select(Event).where(Event.action == "sales.note_recorded")).one()


def test_bindings_match_the_manifest() -> None:
    assert {b.tool_id for b in tools.BINDINGS} == {t.id for t in MANIFEST.tools}


def test_a_correction_today_does_not_touch_yesterday(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    ana = people["Ana"]
    yesterday = today() - dt.timedelta(days=1)
    special = item(session, "Special")
    before = [r for r in counts(session, ana, yesterday) if r.item_id == special]
    assert before and not counts(session, ana, today())
    args = CorrectCountInput(item_id=special, quantity=4)
    with pytest.raises(LookupError, match="count"):
        tools.correct_count(deps_for(session, ana), args, "c1")
    after = [r for r in counts(session, ana, yesterday) if r.item_id == special]
    assert [r.superseded_by for r in after] == [None]


def test_a_correction_for_a_named_day(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    yesterday = today() - dt.timedelta(days=1)
    args = CorrectCountInput(item_id=item(session, "Special"), quantity=4, business_date=yesterday)
    out = tools.correct_count(deps_for(session, people["Ana"]), args, "c1")
    assert out.business_date == yesterday and out.corrected.quantity == 4


def test_a_supervisor_reading_another_branch_is_an_rbac_deny(
    session: Session, ferinos: Ferinos
) -> None:
    _, people = ferinos
    with pytest.raises(PermissionDenied):
        tools.today(
            deps_for(session, people["Marites"]), TodayInput(branch_id=stall(session).id), "c"
        )
    denies = session.exec(select(Event).where(Event.action == "rbac.deny")).all()
    assert any((e.after or {}).get("action") == "read_all" for e in denies)


def test_call_tool_refuses_a_clerk_another_branch(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    binding = next(b for b in tools.BINDINGS if b.tool_id.endswith(".today"))
    out = call_tool(
        deps_for(session, people["Ana"]), binding, TodayInput(branch_id=stall(session).id), "c9"
    )
    assert out["status"] == "denied"
    called = session.exec(select(Event).where(Event.action == "tool.called")).all()
    assert [e.tool_call_id for e in called] == ["c9"]


# ---- the business date (C1, M1, M12, M14) ---------------------------------------------------


def late_close_yesterday(session: Session, kiosk: Branch, closes: str = "23:00") -> None:
    """Yesterday's closing at the kiosk moved to `closes`."""
    yesterday = (today() - dt.timedelta(days=1)).weekday()
    stmt = select(RetailBranchHours).where(RetailBranchHours.branch_id == kiosk.id)
    hours = session.exec(stmt.where(RetailBranchHours.weekday == yesterday)).one()
    store.update(session, hours, {"closes": closes}, Actor.system(kiosk.id))


def three_special(session: Session, **extra: object) -> RecordCountsInput:
    return RecordCountsInput(
        items=[CountIn(item_id=item(session, "Special"), quantity=3)],
        **extra,  # type: ignore[arg-type]
    )


def test_the_evening_after_closing_counts_on_today_without_asking(
    session: Session, ferinos: Ferinos, manila_evening: dt.datetime
) -> None:
    _, people = ferinos  # Ana counted yesterday (seed); the kiosk closed at 21:00
    out = tools.record_counts(deps_for(session, people["Ana"]), three_special(session), "c1")
    assert out.business_date == today()


def test_after_midnight_a_late_closing_counts_on_yesterday(
    session: Session, ferinos: Ferinos, manila_at: Callable[[int, int], dt.datetime]
) -> None:
    kiosk, people = ferinos
    late_close_yesterday(session, kiosk)
    manila_at(0, 30)
    out = tools.record_counts(deps_for(session, people["Liza"]), three_special(session), "c1")
    assert out.business_date == today() - dt.timedelta(days=1)


def test_before_opening_but_two_hours_after_a_late_closing_is_today(
    session: Session, ferinos: Ferinos, manila_at: Callable[[int, int], dt.datetime]
) -> None:
    kiosk, people = ferinos
    late_close_yesterday(session, kiosk)
    manila_at(8, 0)
    out = tools.record_counts(deps_for(session, people["Ana"]), three_special(session), "c1")
    assert out.business_date == today()


def test_a_correction_after_midnight_corrects_yesterdays_count(
    session: Session, ferinos: Ferinos, manila_at: Callable[[int, int], dt.datetime]
) -> None:
    kiosk, people = ferinos
    late_close_yesterday(session, kiosk)
    manila_at(0, 30)
    ana, special = people["Ana"], item(session, "Special")
    out = tools.correct_count(
        deps_for(session, ana), CorrectCountInput(item_id=special, quantity=9), "c1"
    )
    yesterday = today() - dt.timedelta(days=1)
    assert out.business_date == yesterday and out.corrected.quantity == 9
    live = [r for r in counts(session, ana, yesterday) if r.item_id == special]
    assert [r.quantity for r in live if r.superseded_by is None] == [9]


def test_a_named_day_is_only_today_or_yesterday(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    deps = deps_for(session, people["Ana"])
    yesterday = today() - dt.timedelta(days=1)
    out = tools.record_counts(deps, three_special(session, business_date=yesterday), "c1")
    assert out.business_date == yesterday
    with pytest.raises(LookupError, match="business_date"):
        tools.record_counts(
            deps, three_special(session, business_date=today() - dt.timedelta(days=2)), "c2"
        )
    with pytest.raises(LookupError, match="business_date"):
        tools.correct_count(
            deps,
            CorrectCountInput(
                item_id=item(session, "Special"),
                quantity=1,
                business_date=today() + dt.timedelta(days=1),
            ),
            "c3",
        )


def test_a_resumed_turn_counts_on_the_day_its_message_was_sent(
    session: Session, ferinos: Ferinos, manila_at: Callable[[int, int], dt.datetime]
) -> None:
    kiosk, people = ferinos
    late_close_yesterday(session, kiosk)
    ana = people["Ana"]
    sent = manila_at(0, 30)
    system = Actor.system(kiosk.id)
    thread = store.insert(session, Thread(branch_id=kiosk.id, person_id=ana.id), system)
    message = Message(
        branch_id=kiosk.id, thread_id=thread.id, role="user", sender_id=ana.id, text="3 sp"
    )
    message.created_at = sent.astimezone(dt.UTC)
    store.insert(session, message, system)
    manila_at(10, 0)  # Jev was down; the turn resumes at ten
    deps = deps_for(session, ana)
    args = three_special(session, source_message_id=message.id)
    assert tools.record_counts(deps, args, "c1").business_date == today()  # not resumed: now
    deps.resumed = True
    out = tools.record_counts(deps, args, "c2")
    assert out.business_date == today() - dt.timedelta(days=1)


def test_today_after_midnight_shows_the_business_date(
    session: Session, ferinos: Ferinos, manila_at: Callable[[int, int], dt.datetime]
) -> None:
    kiosk, people = ferinos
    late_close_yesterday(session, kiosk)
    manila_at(0, 30)
    (shown,) = tools.today(deps_for(session, people["Ana"]), TodayInput(), "c1").branches
    yesterday = today() - dt.timedelta(days=1)
    rows = [r for r in session.exec(select(SalesCount)) if r.business_date == yesterday]
    assert shown.total == sum(r.amount for r in rows if r.branch_id == kiosk.id) > 0


# ---- the running total (I1) -----------------------------------------------------------------


def test_day_total_is_the_branchs_running_total(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    ana, liza = deps_for(session, people["Ana"]), deps_for(session, people["Liza"])
    tools.record_counts(ana, three_special(session), "c1")  # 135.00
    classic = RecordCountsInput(items=[CountIn(item_id=item(session, "Classic"), quantity=2)])
    tools.record_counts(liza, classic, "c2")  # 80.00
    out = tools.record_counts(ana, three_special(session, total=99999), "c3")  # 135.00
    assert out.day_total == 13500 + 8000 + 13500
    assert out.target_share is not None


# ---- every branch (I2) ----------------------------------------------------------------------


def test_the_owner_sees_every_branch_without_naming_one(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    rosa = deps_for(session, people["Rosa"])
    shown = tools.today(rosa, TodayInput(), "c1").branches
    assert [b.branch for b in shown] == ["Mall kiosk", "Street stall"]
    assert [b.branch for b in tools.today(rosa, TodayInput(branch_id="all"), "c2").branches] == [
        "Mall kiosk",
        "Street stall",
    ]


def test_a_supervisor_without_a_branch_named_sees_their_own(
    session: Session, ferinos: Ferinos
) -> None:
    _, people = ferinos
    shown = tools.today(deps_for(session, people["Marites"]), TodayInput(), "c1").branches
    assert [b.branch for b in shown] == ["Mall kiosk"]
    with pytest.raises(PermissionDenied):
        tools.today(deps_for(session, people["Ana"]), TodayInput(branch_id="all"), "c2")


def test_the_owner_sets_one_target_on_every_branch(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = SetTargetInput(period="day", starts_on=today(), amount=350000, branch_id="all")
    out = tools.set_target(deps_for(session, people["Rosa"]), args, "c1")
    rows = [session.get(SalesTarget, i) for i in out.target_ids]
    assert sorted(r.branch_id for r in rows if r) == sorted(
        b.id for b in session.exec(select(Branch))
    )
    assert len(session.exec(select(Event).where(Event.action == "sales.target_set")).all()) == 2


def test_a_supervisor_cannot_set_every_branchs_target(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = SetTargetInput(period="day", starts_on=today(), amount=1, branch_id="all")
    with pytest.raises(PermissionDenied):
        tools.set_target(deps_for(session, people["Marites"]), args, "c1")
    assert not session.exec(select(Event).where(Event.action == "sales.target_set")).all()


# ---- the why note's date (I5) ---------------------------------------------------------------


def test_a_why_answer_takes_the_questions_business_date(session: Session, ferinos: Ferinos) -> None:
    kiosk, people = ferinos
    yesterday = today() - dt.timedelta(days=1)
    data = {"date": yesterday.isoformat(), "message_ids": ["m-why"]}
    alerts._mark(session, kiosk.id, "sales.why_asked", ("branch", kiosk.id), data)
    deps = deps_for(session, people["Ana"])
    args = RecordNoteInput(text="payday", asked_message_id="m-why", themes=["other"])
    out = tools.record_note(deps, args, "c1")
    note = session.get(SalesNote, out.note_id)
    assert out.business_date == yesterday and note is not None
    assert note.asked_message_id == "m-why"
