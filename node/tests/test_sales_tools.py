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
from mia.core.models import Actor, Branch, Event, Person
from mia.core.rbac import PermissionDenied
from mia.templates.retail.models import RetailItem

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


def test_a_stated_total_close_to_the_sum_is_reported(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = RecordCountsInput(items=[CountIn(item_id=item(session, "Special"), quantity=3)])
    deps = deps_for(session, people["Ana"])
    close = tools.record_counts(deps, args.model_copy(update={"total": 13600}), "c1")
    far = tools.record_counts(deps, args.model_copy(update={"total": 20000}), "c2")
    assert (close.day_total, far.day_total) == (13600, 13500)


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
    shown = tools.today(deps_for(session, ana), TodayInput(), "c3")
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
    out = tools.today(
        deps_for(session, people["Rosa"]), TodayInput(branch_id=stall(session).id), "c"
    )
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
    assert session.get(SalesTarget, out.target_id) is not None
    assert session.exec(select(Event).where(Event.action == "sales.target_set")).one()
    count = RecordCountsInput(items=[CountIn(item_id=item(session, "Box of 4"), quantity=10)])
    tools.record_counts(deps_for(session, people["Ana"]), count, "c6")
    shown = tools.today(deps_for(session, people["Ana"]), TodayInput(), "c7")
    assert shown.target_share == 350000 and shown.total == 160000
    assert shown.percent == round((160000 - 350000) * 100 / 350000)


def test_an_owners_day_target_wins_over_a_supervisors(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    rosa = deps_for(session, people["Rosa"])
    tools.set_target(rosa, SetTargetInput(period="day", starts_on=today(), amount=500000), "c1")
    marites = deps_for(session, people["Marites"])
    tools.set_target(marites, SetTargetInput(period="day", starts_on=today(), amount=1000), "c2")
    assert tools.today(marites, TodayInput(), "c3").target_share == 500000


def test_a_supervisor_cannot_set_another_branchs_target(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = SetTargetInput(period="day", starts_on=today(), amount=1, branch_id=stall(session).id)
    with pytest.raises(PermissionDenied):
        tools.set_target(deps_for(session, people["Marites"]), args, "c1")


def test_a_count_after_closing_with_yesterdays_counts_asks(
    session: Session, ferinos: Ferinos, manila_evening: dt.datetime
) -> None:
    _, people = ferinos
    args = RecordCountsInput(items=[CountIn(item_id=item(session, "Special"), quantity=3)])
    with pytest.raises(LookupError, match="business_date"):
        tools.record_counts(deps_for(session, people["Ana"]), args, "c1")
    stated = args.model_copy(update={"business_date": today()})
    assert tools.record_counts(deps_for(session, people["Ana"]), stated, "c2").recorded


def test_a_count_after_closing_without_yesterdays_counts_is_today(
    session: Session, ferinos: Ferinos, manila_evening: dt.datetime
) -> None:
    _, people = ferinos
    args = RecordCountsInput(items=[CountIn(item_id=item(session, "Special"), quantity=3)])
    out = tools.record_counts(deps_for(session, people["Liza"]), args, "c1")
    assert out.business_date == today()


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
    args = RecordNoteInput(text="maraming tao sa mall")
    out = tools.record_note(deps_for(session, people["Ana"]), args, "c8")
    note = session.get(SalesNote, out.note_id)
    assert note is not None and note.text == "maraming tao sa mall"
    assert note.person_id == people["Ana"].id and out.business_date == today()
    assert session.exec(select(Event).where(Event.action == "sales.note_recorded")).one()


def test_bindings_match_the_manifest() -> None:
    assert {b.tool_id for b in tools.BINDINGS} == {t.id for t in MANIFEST.tools}
