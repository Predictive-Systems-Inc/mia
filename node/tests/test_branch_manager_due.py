"""The branch manager's due work on the tick at fixed clocks (bm_en, BM_TODAY a Monday): the
morning message with a tip and a quote, cheers and one kind nudge after the closing, the
experiment's result with Keep and Revert, the weekly summary and the monthly numbers letter."""

import datetime as dt
from collections.abc import Iterator
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, col, select

from mia.agents.branch_manager import MANIFEST, due, replies, tools, turn
from mia.agents.branch_manager.models import Coaching, Experiment, Tip
from mia.agents.branch_manager.tools import MonthlyInput, WeeklyInput, WeeklyOutput
from mia.agents.sales_supervisor import MANIFEST as SALES
from mia.agents.sales_supervisor import due as sales_due
from mia.agents.sales_supervisor import tools as sales_tools
from mia.agents.sales_supervisor.tools import CountIn, RecordCountsInput, SetTargetInput
from mia.channels import registry
from mia.channels.simulator import SimAdapter
from mia.core import orgconfig, store
from mia.core.models import (
    Actor,
    Branch,
    ChannelIdentity,
    ChannelOutbox,
    Event,
    Message,
    Person,
    Thread,
)
from mia.core.money import format_money
from mia.core.orgconfig import ChannelConfig, OrgSettings
from mia.i18n import t
from mia.templates.retail import hours as retail_hours
from mia.templates.retail import items
from mia.templates.retail.models import RetailBranchHours, RetailItem, RetailItemPrice
from tests.conftest import BM_TODAY as TODAY
from tests.conftest import Pin
from tests.test_branch_manager_tools import deps_for
from tests.test_sales_tools import deps_for as sales_deps

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")
EN = "en"
ONE_DAY = dt.timedelta(days=1)
YESTERDAY = TODAY - ONE_DAY


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), MNL)


def _tick(session: Session, pin: Pin, moment: dt.datetime) -> int:
    return due.run_due(session, pin(moment))


def notifications(session: Session, person: Person) -> list[Message]:
    threads = select(Thread.id).where(Thread.person_id == person.id)
    stmt = select(Message).where(col(Message.thread_id).in_(threads))
    rows = session.exec(stmt.where(Message.role == "notification")).all()
    return [m for m in rows if m.agent_id == MANIFEST.id]


def texts(session: Session, person: Person) -> list[str]:
    return [m.text for m in notifications(session, person)]


def given(session: Session, person: Person, kind: str) -> Tip:
    """The one tip or quote (Tip.kind) the person was given, through its Coaching row."""
    stmt = select(Coaching).where(Coaching.person_id == person.id).where(Coaching.kind == "tip")
    rows = [session.get(Tip, c.tip_id) for c in session.exec(stmt)]
    (row,) = [r for r in rows if r is not None and r.kind == kind]
    return row


def coached(session: Session, person: Person, kind: str) -> list[Coaching]:
    stmt = select(Coaching).where(Coaching.person_id == person.id).where(Coaching.kind == kind)
    return list(session.exec(stmt))


def money(amount: int | None) -> str:
    assert amount is not None
    return format_money(amount, "PHP", EN)


def kiosk_hours(session: Session, kiosk: Branch) -> list[RetailBranchHours]:
    return retail_hours.load(session, kiosk.id)


def day_total(session: Session, kiosk: Branch, day: dt.date) -> int:
    return sales_due._total(session, kiosk.id, day)


def share(session: Session, kiosk: Branch, day: dt.date) -> int | None:
    return sales_tools._share(session, kiosk.id, kiosk_hours(session, kiosk), day)


def count(
    session: Session, pin: Pin, person: Person, name: str, quantity: int, day: dt.date
) -> None:
    """The person's count of the item on day (reported at 15:00 that day)."""
    pin(at(day, 15))
    item = session.exec(select(RetailItem).where(RetailItem.name == name)).one()
    args = RecordCountsInput(items=[CountIn(item_id=item.id, quantity=quantity)])
    sales_tools.record_counts(sales_deps(session, person), args, "c1")
    session.commit()


def set_day_target(session: Session, bm: Ferinos, amount: int, days: int) -> None:
    """The owner's day target on each of the `days` days before TODAY."""
    deps = sales_deps(session, bm[1]["Rosa"])
    for k in range(1, days + 1):
        args = SetTargetInput(period="day", starts_on=TODAY - k * ONE_DAY, amount=amount)
        sales_tools.set_target(deps, args, f"t{k}")
    session.commit()


def running(session: Session) -> Experiment:
    return session.exec(select(Experiment).where(Experiment.status == "running")).one()


# ---- the windows (pure) ---------------------------------------------------------------------


def test_the_windows_follow_the_branch_hours(session: Session, bm_en: Ferinos) -> None:
    kiosk, _ = bm_en
    hours = kiosk_hours(session, kiosk)
    assert due.morning_message(kiosk, hours, at(TODAY, 9, 10)) == TODAY
    assert due.weekly(kiosk, hours, at(TODAY, 9, 10)) == TODAY  # a Monday
    assert due.weekly(kiosk, hours, at(TODAY + ONE_DAY, 9, 10)) is None
    assert due.monthly(kiosk, hours, at(dt.date(2026, 11, 1), 9, 10)) == dt.date(2026, 11, 1)
    assert due.monthly(kiosk, hours, at(dt.date(2026, 11, 2), 9, 10)) is None
    assert due.closing(kiosk, hours, at(TODAY, 21, 59)) is None
    assert due.closing(kiosk, hours, at(TODAY, 22, 0)) == TODAY


# ---- the morning message --------------------------------------------------------------------


def test_the_morning_message_has_result_tip_and_quote(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    kiosk, people = bm_en
    assert _tick(session, pin, at(TODAY, 9, 10)) >= 2
    (note,) = notifications(session, people["Ana"])
    tip, quote = given(session, people["Ana"], "tip"), given(session, people["Ana"], "quote")
    assert note.text == t(
        "bm.morning",
        EN,
        yesterday=money(day_total(session, kiosk, YESTERDAY)),
        target=money(share(session, kiosk, TODAY)),
        tip=tip.text,
        quote=quote.text,
        source=quote.source,
    )
    assert tip.item_id is None and [
        c.message_id for c in coached(session, people["Ana"], "morning")
    ] == [note.id]


def test_the_morning_message_is_sent_once_per_person_and_day(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    _tick(session, pin, at(TODAY, 9, 10))
    assert _tick(session, pin, at(TODAY, 9, 40)) == 0


def test_a_clerk_with_every_tip_used_gets_no_tip_line(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    kiosk, people = bm_en
    ana = people["Ana"]
    actor = Actor.system(kiosk.id)
    for tip in tools._tips(session, EN, "tip"):
        row = Coaching(
            branch_id=kiosk.id, person_id=ana.id, kind="tip", sent_on=YESTERDAY, tip_id=tip.id
        )
        store.insert(session, row, actor)
    session.commit()
    _tick(session, pin, at(TODAY, 9, 10))
    (note,) = notifications(session, ana)
    quote = given(session, ana, "quote")
    assert note.text == t(
        "bm.morning.no_tip",
        EN,
        yesterday=money(day_total(session, kiosk, YESTERDAY)),
        target=money(share(session, kiosk, TODAY)),
        quote=quote.text,
        source=quote.source,
    )


def test_the_morning_text_says_nothing_with_nothing_to_say() -> None:
    assert due.morning_text(EN, None, None, None, None) is None
    assert due.morning_text(EN, None, "₱1.00", None, None) == t(
        "bm.morning.result", EN, yesterday=t("bm.morning.no_counts", EN), target="₱1.00"
    )


# ---- cheers and nudges ----------------------------------------------------------------------


def test_a_met_target_is_cheered(session: Session, bm_en: Ferinos, pin: Pin) -> None:
    count(session, pin, bm_en[1]["Ana"], "Box of 4", 30, TODAY)  # well over the day share
    _tick(session, pin, at(TODAY, 22, 10))
    assert t("bm.cheer.target", EN) in texts(session, bm_en[1]["Ana"])
    assert _tick(session, pin, at(TODAY, 22, 40)) == 0  # once per person and day


def test_cheers_are_not_held_by_quiet_hours(
    session: Session, bm_en: Ferinos, pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    ana = bm_en[1]["Ana"]
    count(session, pin, ana, "Box of 4", 30, TODAY)
    saved = dict(registry._adapters)
    registry._adapters.clear()
    registry.register(SimAdapter())
    org = OrgSettings(agents=[MANIFEST.id], channels={"sim": ChannelConfig(enabled=True)})
    try:
        with monkeypatch.context() as m:
            m.setattr(orgconfig, "load", lambda org_name=None: org)
            identity = ChannelIdentity(
                branch_id=ana.branch_id, person_id=ana.id, channel="sim", address="639170000001"
            )
            store.insert(session, identity, Actor.person(ana), action="channel.linked")
            session.commit()
            assert _tick(session, pin, at(TODAY, 22, 10)) >= 1  # quiet since 21:00
        rows = list(session.exec(select(ChannelOutbox).where(ChannelOutbox.person_id == ana.id)))
        assert rows and all(r.send_after is None for r in rows)
    finally:
        registry._adapters.clear()
        registry._adapters.update(saved)


def test_cheers_after_a_late_close_keep_their_business_date(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    kiosk, people = bm_en
    monday = next(h for h in kiosk_hours(session, kiosk) if h.weekday == TODAY.weekday())
    store.update(session, monday, {"closes": "23:00"}, Actor.system(kiosk.id))
    count(session, pin, people["Ana"], "Box of 4", 30, TODAY)
    _tick(session, pin, at(TODAY + ONE_DAY, 0, 30))  # after the 23:00 close
    assert [c.sent_on for c in coached(session, people["Ana"], "cheer")] == [TODAY]


def test_a_day_without_counts_or_target_cheers_nobody(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    ana = bm_en[1]["Ana"]
    assert _tick(session, pin, at(TODAY, 22, 10)) == 0  # no counts today
    november = dt.date(2026, 11, 3)  # the month target is October's
    count(session, pin, ana, "Classic", 1, november)
    _tick(session, pin, at(november, 22, 10))
    assert coached(session, ana, "cheer") == []


def test_three_misses_earn_one_nudge(session: Session, bm_en: Ferinos, pin: Pin) -> None:
    set_day_target(session, bm_en, 10_000_000, days=3)  # the last three days missed it
    _tick(session, pin, at(TODAY - ONE_DAY, 22, 10))
    _tick(session, pin, at(TODAY, 22, 10))
    assert texts(session, bm_en[1]["Ana"]).count(t("bm.nudge", EN)) == 1


def test_no_nudge_while_the_target_is_met(session: Session, bm_en: Ferinos, pin: Pin) -> None:
    _tick(session, pin, at(TODAY - ONE_DAY, 22, 10))
    assert t("bm.nudge", EN) not in texts(session, bm_en[1]["Ana"])


# ---- experiments ----------------------------------------------------------------------------


def test_the_tick_scores_and_reports_an_ended_experiment(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    kiosk, people = bm_en
    row = running(session)
    _tick(session, pin, at(row.ends_on, 22, 10))
    session.refresh(row)
    result = row.result or {}
    text = replies.score_text(
        result["units_pct"],
        result["amount_pct"],
        result["days"],
        True,
        t("bm.strategy.increase", EN),
        "Special",
        EN,
    )
    rosa, marites = people["Rosa"], people["Marites"]
    assert text in texts(session, marites) and text in "\n".join(texts(session, rosa))
    (note,) = [m for m in notifications(session, rosa) if text in m.text]
    (buttons,) = [b for b in note.blocks if b["type"] == "quick_replies"]
    keep = t("bm.experiment.keep", EN, price=money(row.to_price))
    assert buttons["options"] == [keep, t("bm.experiment.revert", EN, price=money(row.from_price))]
    thread = session.get(Thread, note.thread_id)
    assert thread is not None
    tapped = turn._tapped(session, due._deps(session, rosa, kiosk, row.ends_on), thread, keep)
    assert tapped is not None and tapped.action == "decide_experiment_result"
    assert tapped.args == {"experiment_id": row.id, "keep": True}
    assert all(
        not m.blocks[1:] for m in notifications(session, marites)
    )  # a supervisor: no buttons


def test_an_unkept_experiment_reverts_at_the_next_opening(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    kiosk, _ = bm_en
    row = running(session)
    _tick(session, pin, at(row.ends_on, 22, 10))
    assert not tools._reverted(session, row)
    _tick(session, pin, at(row.ends_on + ONE_DAY, 9, 10))
    assert tools._reverted(session, row)
    special = session.get(RetailItem, row.item_id)
    assert special is not None
    assert items.price_on(session, special, kiosk.id, row.ends_on + ONE_DAY) == row.from_price
    stmt = select(RetailItemPrice).where(RetailItemPrice.effective_on == row.ends_on + ONE_DAY)
    assert all(r.applied_at is not None for r in session.exec(stmt))


# ---- the weekly summary and the monthly letter ----------------------------------------------


def test_the_weekly_summary_reads_sales_and_stock(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    _, people = bm_en
    _tick(session, pin, at(TODAY, 9, 10))
    out = tools.weekly_summary(
        deps_for(session, people["Rosa"]), WeeklyInput(week_start=TODAY - dt.timedelta(days=7)), "w"
    )
    week = WeeklyOutput(start=out.start, end=out.end, branches=[out.branches[0]])
    text = replies.weekly(week, due._names(session), "PHP", EN)[0].text
    assert text in texts(session, people["Rosa"]) and out.branches[0].waste
    assert text in texts(session, people["Marites"])
    assert _tick(session, pin, at(TODAY, 9, 40)) == 0  # once per branch and Monday


def test_the_monthly_letter_is_numbers(session: Session, bm_en: Ferinos, pin: Pin) -> None:
    _, people = bm_en
    _tick(session, pin, at(dt.date(2026, 11, 1), 9, 10))
    out = tools.monthly_letter(
        deps_for(session, people["Rosa"]), MonthlyInput(month=dt.date(2026, 10, 1)), "m"
    )
    text = replies.monthly(out, due._names(session), EN)[0].text
    assert text in texts(session, people["Rosa"])
    assert _tick(session, pin, at(dt.date(2026, 11, 1), 9, 40)) == 0


# ---- the organisation gate ------------------------------------------------------------------


@pytest.fixture
def without_branch_manager(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    org = OrgSettings(agents=[SALES.id])
    with monkeypatch.context() as m:
        m.setattr(orgconfig, "load", lambda org_name=None: org)
        yield


def test_nothing_runs_for_an_organisation_without_the_branch_manager(
    session: Session, bm_en: Ferinos, pin: Pin, without_branch_manager: None
) -> None:
    assert _tick(session, pin, at(TODAY, 9, 10)) == 0
    assert notifications(session, bm_en[1]["Ana"]) == []


def actions_of(session: Session, person: Person) -> set[str]:
    rows = session.exec(select(Event).where(Event.entity_type == Coaching.__tablename__))
    ids = {c.id for c in session.exec(select(Coaching).where(Coaching.person_id == person.id))}
    return {e.action for e in rows if e.entity_id in ids}


def test_coaching_sends_log_the_spec_event_names(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    ana = bm_en[1]["Ana"]
    _tick(session, pin, at(TODAY, 9, 10))
    assert actions_of(session, ana) == {f"{MANIFEST.id}.morning_sent", f"{MANIFEST.id}.tip_given"}
    set_day_target(session, bm_en, 10_000_000, days=3)
    _tick(session, pin, at(TODAY - ONE_DAY, 22, 10))
    count(session, pin, ana, "Box of 4", 30, TODAY)
    _tick(session, pin, at(TODAY, 22, 10))
    assert {f"{MANIFEST.id}.cheered", f"{MANIFEST.id}.nudged"} <= actions_of(session, ana)


def test_a_personal_best_is_cheered_when_the_branch_misses(
    session: Session, bm_en: Ferinos, pin: Pin
) -> None:
    kiosk, people = bm_en
    ana = people["Ana"]
    deps = sales_deps(session, people["Rosa"])
    args = SetTargetInput(period="day", starts_on=TODAY, amount=10_000_000)
    sales_tools.set_target(deps, args, "t0")
    count(session, pin, ana, "Box of 4", 60, TODAY)  # above her best seeded day
    _tick(session, pin, at(TODAY, 22, 10))
    best = sum(c.amount for c in sales_tools._live_counts(session, [kiosk.id], TODAY, TODAY))
    assert day_total(session, kiosk, TODAY) < (share(session, kiosk, TODAY) or 0)
    assert t("bm.cheer.best", EN, amount=money(best)) in texts(session, ana)
    assert t("bm.cheer.target", EN) not in texts(session, ana)
