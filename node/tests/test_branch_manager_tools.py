"""The branch manager's data and tools: dated prices per branch, the tips and strategies seed,
the nine tools behind RBAC, the two money approvals with their handlers and the experiment tick
(on the bm seed, pinned to BM_TODAY; no wall clock)."""

import datetime as dt
from collections import Counter
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.branch_manager import MANIFEST, replies, tools
from mia.agents.branch_manager.models import Coaching, Experiment, Strategy, Tip
from mia.agents.branch_manager.tools import (
    ChangePriceInput,
    CoachingInput,
    DecideInput,
    HowToSellInput,
    MonthlyInput,
    ProposeExperimentInput,
    ScoreInput,
    SetShortCodeInput,
    WeeklyInput,
)
from mia.agents.sales_supervisor import tools as sales_tools
from mia.agents.sales_supervisor.tools import CountIn, RecordCountsInput
from mia.core import approvals, scheduling, store
from mia.core.models import Actor, Approval, Branch, Event, Message, Person, SalesNote, Thread
from mia.core.money import format_money
from mia.core.rbac import PermissionDenied, get_rbac
from mia.core.sales import live_counts
from mia.i18n import t
from mia.templates.retail import hours as retail_hours
from mia.templates.retail import items
from mia.templates.retail.models import RetailBranchHours, RetailItem, RetailItemPrice
from tests.conftest import BM_TODAY as TODAY
from tests.conftest import Pin, Shop
from tests.test_sales_tools import deps_for as sales_deps
from tests.test_sales_tools import stall

Ferinos = tuple[Branch, dict[str, Person]]
ONE_DAY = dt.timedelta(days=1)
MNL = ZoneInfo("Asia/Manila")
BINDING = {b.tool_id: b for b in tools.BINDINGS}


def item(session: Session, name: str) -> RetailItem:
    return session.exec(select(RetailItem).where(RetailItem.name == name)).one()


def test_counts_use_the_price_in_force_on_the_business_date(session: Session, bm: Ferinos) -> None:
    kiosk, people = bm
    special = item(session, "Special")
    items.schedule_price(session, special, kiosk.id, 5000, TODAY, Actor.system(kiosk.id))
    assert (
        items.price_on(session, special, kiosk.id, TODAY - 5 * ONE_DAY)  # the seeded test: -4
        == items.price_on(session, special, stall(session).id, TODAY)
        == 4500
    )
    args = RecordCountsInput(items=[CountIn(item_id=special.id, quantity=2)])
    out = sales_tools.record_counts(sales_deps(session, people["Ana"]), args, "c1")
    assert out.recorded[0].amount == 10000


def test_the_newest_row_wins_on_the_same_date(session: Session, bm: Ferinos) -> None:
    kiosk, _ = bm
    special, actor = item(session, "Special"), Actor.system(kiosk.id)
    items.schedule_price(session, special, kiosk.id, 5000, TODAY, actor)
    items.schedule_price(session, special, kiosk.id, 4900, TODAY, actor)
    items.schedule_price(session, special, kiosk.id, 5500, TODAY + 7 * ONE_DAY, actor)
    assert items.price_on(session, special, kiosk.id, TODAY + ONE_DAY) == 4900
    assert items.price_on(session, special, kiosk.id, TODAY + 7 * ONE_DAY) == 5500


def test_apply_due_stamps_each_due_row_once(session: Session, bm_shop: Shop) -> None:
    kiosk = bm_shop.kiosk
    special, actor = item(session, "Special"), Actor.system(kiosk.id)
    due = items.schedule_price(session, special, kiosk.id, 5000, TODAY, actor)
    items.schedule_price(session, special, kiosk.id, 5500, TODAY + ONE_DAY, actor)
    at = bm_shop.pin(9, 5)
    assert items.apply_due(session, kiosk, TODAY, actor) == [due]
    assert due.applied_at is not None and abs(due.applied_at - at) < dt.timedelta(minutes=1)
    assert items.apply_due(session, kiosk, TODAY, actor) == []
    changed = session.exec(select(Event).where(Event.action == "retail.item_price_changed")).all()
    dates = [e.after["effective_on"] for e in changed if e.after]
    assert dates.count(TODAY.isoformat()) == 1  # the others are the seeded experiments' rows
    assert session.exec(select(RetailItemPrice)).all()  # nothing removed


def test_set_short_codes_logs_the_change(session: Session, bm: Ferinos) -> None:
    kiosk, _ = bm
    classic = items.set_short_codes(
        session, item(session, "Classic"), ["cl", "bib"], Actor.system(kiosk.id), "t1"
    )
    assert classic.short_codes == ["cl", "bib"]
    event = session.exec(select(Event).where(Event.tool_call_id == "t1")).one()
    assert event.after and event.after["short_codes"] == ["cl", "bib"]


def test_seed_has_tips_with_sources_and_sourceless_encouragement(
    session: Session, bm: Ferinos
) -> None:
    rows = session.exec(select(Tip)).all()
    assert all(
        Counter(r.kind for r in rows if r.language == lang) == {"tip": 20, "cheer": 20}
        for lang in ("fil", "en")
    )
    assert all(r.source.strip() for r in rows if r.kind == "tip")
    assert all(r.source == "" for r in rows if r.kind == "cheer")
    general = [r for r in rows if r.kind == "tip" and r.language == "en" and r.item_id is None]
    assert len(general) == 10
    named = {item(session, n).id for n in ("Classic", "Puto bumbong", "Salted egg")}
    assert {r.item_id for r in rows if r.item_id} == named
    assert not [r.text for r in rows if r.kind == "tip" and any(c.isdigit() for c in r.text)]


def test_seed_has_the_eight_strategies_with_sources(session: Session, bm: Ferinos) -> None:
    rows = session.exec(select(Strategy)).all()
    assert len(rows) == 8 and all(r.source.strip() and r.active for r in rows)
    assert {r.kind for r in rows} == {"price", "promo", "bundle"}
    assert len({r.name_key for r in rows}) == 8


def test_policy_grants_the_branch_manager_rights_by_role() -> None:
    def can(role: str, resource: str, action: str) -> bool:
        return bool(get_rbac().enforcer.enforce(role, "B", resource, action))

    tool = "tool:branch_manager."
    assert can("clerk", f"{tool}coaching", "execute")
    assert can("clerk", "data:branch_manager_coaching", "read_own")
    assert not can("clerk", "data:branch_manager_coaching", "read")
    assert not can("clerk", "data:branch_manager_experiments", "read")
    assert not can("clerk", f"{tool}propose_experiment", "request")
    assert not can("clerk", "data:retail_items", "write")
    assert can("supervisor", f"{tool}propose_experiment", "request")
    assert can("supervisor", f"{tool}change_price", "request")
    assert not can("supervisor", f"{tool}change_price", "execute")
    assert not can("supervisor", f"{tool}decide_experiment", "execute")
    assert not can("supervisor", "data:branch_manager_experiments", "read_all")
    assert can("owner", f"{tool}decide_experiment", "execute")
    assert can("owner", "data:branch_manager_experiments", "write_all")


# ---- tools --------------------------------------------------------------------------------


def deps_for(session: Session, person: Person) -> AgentDeps:
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=TODAY,
        lang=person.language or "en",
        manifest=MANIFEST,
    )


def strategy(session: Session, key: str) -> Strategy:
    return session.exec(select(Strategy).where(Strategy.name_key == key)).one()


def propose(
    session: Session,
    who: Person,
    price: int | None = 4400,
    call: str = "e1",
    key: str | None = "bm.strategy.charm",  # holds for Classic (a typed price, its rationale)
    name: str = "Classic",
) -> dict[str, Any]:
    args = ProposeExperimentInput(
        item_id=item(session, name).id,
        to_price=price,
        starts_on=TODAY + ONE_DAY,
        strategy_id=strategy(session, key).id if key else None,
    )
    return call_tool(
        deps_for(session, who), BINDING[f"{MANIFEST.id}.propose_experiment"], args, call
    )


def change(session: Session, who: Person, price: int, call: str = "p1") -> dict[str, Any]:
    args = ChangePriceInput(
        item_id=item(session, "Classic").id, price=price, effective_on=TODAY + 7 * ONE_DAY
    )
    return call_tool(deps_for(session, who), BINDING[f"{MANIFEST.id}.change_price"], args, call)


def decide(session: Session, approval_id: str, who: Person, outcome: str) -> Approval:
    return approvals.decide(
        session, approval_id, Actor.person(who), outcome, stepped_up_at=approvals.utcnow()
    )


def running(session: Session) -> Experiment:
    return session.exec(select(Experiment).where(Experiment.status == "running")).one()


def end_seeded_experiment(session: Session) -> None:
    store.update(
        session, running(session), {"status": "done"}, Actor.system(running(session).branch_id)
    )


def hours(session: Session, branch: Branch) -> list[RetailBranchHours]:
    return retail_hours.load(session, branch.id)


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), MNL)


def told(session: Session, person: Person) -> list[str]:
    threads = select(Thread.id).where(Thread.person_id == person.id)
    rows = session.exec(select(Message).where(col(Message.thread_id).in_(threads))).all()
    return [m.text for m in rows]


def proposals_asked(session: Session) -> list[Approval]:
    stmt = select(Approval).where(Approval.type == f"{MANIFEST.id}.propose_experiment")
    return list(session.exec(stmt))


def test_an_approved_experiment_changes_the_price_on_the_day(
    session: Session, bm: Ferinos, pin: Pin
) -> None:
    kiosk, people = bm
    end_seeded_experiment(session)
    decide(session, propose(session, people["Marites"])["approval_id"], people["Rosa"], "approved")
    classic = item(session, "Classic")
    assert items.price_on(session, classic, kiosk.id, TODAY) == 4000
    assert items.price_on(session, classic, kiosk.id, TODAY + ONE_DAY) == 4400
    assert items.price_on(session, classic, kiosk.id, TODAY + dt.timedelta(days=15)) == 4000
    started = tools.experiment_tick(
        session, kiosk, hours(session, kiosk), pin(at(TODAY + ONE_DAY, 9, 5))
    )
    assert [k for k, _ in started] == ["started"] and started[0][1].status == "running"
    row = started[0][1]
    assert row.baseline is not None and row.baseline["days"] >= 7
    assert (row.strategy_id, row.kind) == (strategy(session, "bm.strategy.charm").id, "price")
    assert (
        tools.experiment_tick(session, kiosk, hours(session, kiosk), at(TODAY + ONE_DAY, 9, 6))
        == []
    )


def test_one_open_experiment_per_branch(session: Session, bm: Ferinos) -> None:
    assert propose(session, bm[1]["Marites"])["status"] == "invalid"  # the seeded one runs
    end_seeded_experiment(session)
    assert propose(session, bm[1]["Marites"], 4300, "e2")["status"] == "approval_required"
    out = propose(session, bm[1]["Marites"], 4200, "e3")
    assert (out["status"], out["message"]) == ("invalid", "open_experiment")  # one pending


def test_a_clerk_cannot_propose_an_experiment(session: Session, bm: Ferinos) -> None:
    end_seeded_experiment(session)
    assert propose(session, bm[1]["Ana"])["status"] == "denied" and proposals_asked(session) == []
    denied = session.exec(select(Event).where(Event.action == "rbac.deny")).all()
    assert denied and denied[-1].tool_call_id == "e1"


def test_a_request_matching_no_strategy_is_refused(session: Session, bm: Ferinos) -> None:
    end_seeded_experiment(session)
    out = propose(session, bm[1]["Marites"], key=None)
    assert (out["status"], out["message"]) == ("invalid", "no_strategy")
    assert proposals_asked(session) == []


def test_a_guard_rail_refuses_a_price_too_far(session: Session, bm: Ferinos) -> None:
    end_seeded_experiment(session)
    out = propose(session, bm[1]["Marites"], 5000)  # 25 percent above 40 pesos
    assert (out["status"], out["message"]) == ("invalid", "too_far")
    assert propose(session, bm[1]["Marites"], 4000, "e2")["message"] == "unchanged"


def test_a_picked_strategy_sizes_the_price_and_its_kind_wins(session: Session, bm: Ferinos) -> None:
    end_seeded_experiment(session)
    charm = strategy(session, "bm.strategy.charm")
    args = ProposeExperimentInput(
        item_id=item(session, "Classic").id,
        starts_on=TODAY + ONE_DAY,
        kind="bundle",  # Jev's pick; the strategy row says price
        strategy_id=charm.id,
    )
    out = call_tool(deps_for(session, bm[1]["Marites"]), BINDING[tools.PROPOSE], args, "e1")
    approval = session.get(Approval, out["approval_id"])
    assert approval is not None
    asked = approval.evidence["input"]
    assert (asked["to_price"], asked["kind"], asked["strategy_id"]) == (3900, "price", charm.id)
    assert asked["rationale"] == {"price": 4000, "units": asked["rationale"]["units"]}


def test_the_owners_own_proposal_is_decided_with_step_up(session: Session, bm: Ferinos) -> None:
    _, people = bm
    end_seeded_experiment(session)
    approval_id = propose(session, people["Rosa"])["approval_id"]
    decide(session, approval_id, people["Rosa"], "approved")
    row = session.exec(select(Experiment).where(Experiment.approval_id == approval_id)).one()
    assert (row.status, row.proposed_by, row.decided_by) == (
        "approved",
        people["Rosa"].id,
        people["Rosa"].id,
    )


def test_a_rejected_experiment_is_recorded_and_the_requester_told(
    session: Session, bm_en: Ferinos
) -> None:
    _, people = bm_en
    end_seeded_experiment(session)
    approval_id = propose(session, people["Marites"])["approval_id"]
    decide(session, approval_id, people["Rosa"], "rejected")
    row = session.exec(select(Experiment).where(Experiment.approval_id == approval_id)).one()
    assert (row.status, row.to_price, row.decided_by) == ("rejected", 4400, people["Rosa"].id)
    prices = select(RetailItemPrice).where(RetailItemPrice.approval_id == approval_id)
    assert session.exec(prices).all() == []
    text = t("bm.experiment_rejected", "en", item="Classic", price=format_money(4400, "PHP", "en"))
    assert text in told(session, people["Marites"])
    assert propose(session, people["Marites"], 4300, "e2")["status"] == "approval_required"


def test_an_engine_new_item_is_created_never_a_reprice(
    session: Session, bm: Ferinos, pin: Pin
) -> None:
    kiosk, people = bm
    end_seeded_experiment(session)
    ube = item(session, "Ube")
    out = propose(session, people["Marites"], None, key="bm.strategy.anchor", name="Ube")
    decide(session, out["approval_id"], people["Rosa"], "approved")
    row = session.exec(select(Experiment).where(Experiment.approval_id == out["approval_id"])).one()
    premium = session.get(RetailItem, row.rationale["new_item"]["item_id"])
    assert premium is not None and premium.name == "Ube Premium"
    assert (premium.price, premium.active, premium.branch_id) == (5400, False, kiosk.id)
    assert (row.from_price, row.to_price) == (4500, 5400)
    assert items.price_on(session, ube, kiosk.id, TODAY + ONE_DAY) == 4500  # Ube untouched
    tools.experiment_tick(session, kiosk, hours(session, kiosk), pin(at(TODAY + ONE_DAY, 9, 5)))
    session.refresh(premium)
    assert premium.active
    end = at(row.ends_on, 22, 5)
    assert [k for k, _ in tools.experiment_tick(session, kiosk, hours(session, kiosk), end)] == [
        "ended"
    ]
    tools.experiment_tick(session, kiosk, hours(session, kiosk), at(row.ends_on + ONE_DAY, 9, 5))
    session.refresh(premium)
    assert not premium.active  # not kept: off the menu after the end


def test_the_tick_ends_and_scores_after_the_close(session: Session, bm: Ferinos) -> None:
    kiosk, _ = bm
    row = running(session)
    before = at(row.ends_on, 21, 30)
    assert tools.experiment_tick(session, kiosk, hours(session, kiosk), before) == []
    ended = tools.experiment_tick(session, kiosk, hours(session, kiosk), at(row.ends_on, 22, 5))
    assert [k for k, _ in ended] == ["ended"] and ended[0][1].status == "done"
    assert ended[0][1].result is not None and ended[0][1].result["days"] == 4  # counts to 25 Oct
    actions = {e.action for e in session.exec(select(Event).where(Event.entity_id == row.id))}
    assert {f"{MANIFEST.id}.experiment_ended", f"{MANIFEST.id}.experiment_scored"} <= actions


def test_keeping_before_the_revert_keeps_the_tested_price(session: Session, bm: Ferinos) -> None:
    kiosk, people = bm
    row, special = running(session), item(session, "Special")
    deps = deps_for(session, people["Rosa"])
    out = tools.decide_experiment(deps, DecideInput(experiment_id=row.id, keep=True), "k1")
    assert out.status == "kept"
    assert items.price_on(session, special, kiosk.id, row.ends_on + ONE_DAY) == 4950
    done = session.exec(select(Experiment).where(Experiment.status == "done")).one()
    with pytest.raises(LookupError, match="too_late"):  # its revert was applied last month
        tools.decide_experiment(deps, DecideInput(experiment_id=done.id, keep=True), "k2")


def test_a_supervisor_cannot_decide_an_experiment(session: Session, bm: Ferinos) -> None:
    args = DecideInput(experiment_id=running(session).id, keep=True)
    deps = deps_for(session, bm[1]["Marites"])
    out = call_tool(deps, BINDING[f"{MANIFEST.id}.decide_experiment"], args, "k1")
    assert out["status"] == "denied" and running(session).status == "running"


def test_score_experiment_reads_the_running_one(session: Session, bm: Ferinos) -> None:
    out = tools.score_experiment(deps_for(session, bm[1]["Marites"]), ScoreInput(), "s1")
    row = running(session)
    assert (out.experiment_id, out.status, out.enough, out.days) == (row.id, "running", True, 4)
    assert out.units_pct is not None and out.amount_pct is not None


def test_a_requester_cannot_approve_their_own_price_change(session: Session, bm: Ferinos) -> None:
    out = change(session, bm[1]["Marites"], 4800)  # a supervisor (D37: not an owner)
    with pytest.raises(approvals.ApprovalError):
        decide(session, out["approval_id"], bm[1]["Marites"], "approved")


def test_an_owners_own_price_change_is_decided_by_the_owner_with_step_up(
    session: Session, bm: Ferinos
) -> None:
    out = change(session, bm[1]["Rosa"], 4800)
    decide(session, out["approval_id"], bm[1]["Rosa"], "approved")
    stmt = select(RetailItemPrice).where(RetailItemPrice.approval_id == out["approval_id"])
    assert session.exec(stmt).one().price == 4800


def test_the_approved_price_is_the_one_requested(session: Session, bm_en: Ferinos) -> None:
    kiosk, people = bm_en
    out = change(session, people["Marites"], 4800)
    decide(session, out["approval_id"], people["Rosa"], "approved")
    stmt = select(RetailItemPrice).where(RetailItemPrice.approval_id == out["approval_id"])
    (row,) = session.exec(stmt)
    assert (row.price, row.effective_on) == (4800, TODAY + dt.timedelta(days=7))
    assert items.price_on(session, item(session, "Classic"), kiosk.id, row.effective_on) == 4800
    text = t(
        "bm.price_approved",
        "en",
        item="Classic",
        price=format_money(4800, "PHP", "en"),
        date=row.effective_on.isoformat(),
    )
    assert text in told(session, people["Marites"])


def test_a_rejected_price_change_writes_no_price(session: Session, bm: Ferinos) -> None:
    out = change(session, bm[1]["Marites"], 4800)
    decide(session, out["approval_id"], bm[1]["Rosa"], "rejected")
    stmt = select(RetailItemPrice).where(RetailItemPrice.approval_id == out["approval_id"])
    assert session.exec(stmt).all() == []
    events = session.exec(select(Event).where(Event.action == f"{MANIFEST.id}.price_rejected"))
    assert [e.after for e in events] == [
        {"item_id": item(session, "Classic").id, "price": 4800, "effective_on": "2026-11-02"}
    ]


def test_a_price_change_in_the_past_or_unchanged_is_refused(session: Session, bm: Ferinos) -> None:
    deps, binding = deps_for(session, bm[1]["Marites"]), BINDING[tools.CHANGE_PRICE]
    classic = item(session, "Classic").id
    past = ChangePriceInput(item_id=classic, price=4800, effective_on=TODAY - ONE_DAY)
    same = ChangePriceInput(item_id=classic, price=4000, effective_on=TODAY + ONE_DAY)
    assert call_tool(deps, binding, past, "p1")["message"] == "in_the_past"
    assert call_tool(deps, binding, same, "p2")["message"] == "unchanged"
    assert session.exec(select(Approval).where(Approval.type == tools.CHANGE_PRICE)).all() == []


def test_a_supervisor_reads_their_kiosks_only(session: Session, bm: Ferinos) -> None:
    """D50: Marites is assigned to the Street stall in the seed; Nonoy (the commissary) is
    assigned to no kiosk."""
    with pytest.raises(PermissionDenied):
        tools.weekly_summary(
            deps_for(session, bm[1]["Nonoy"]), WeeklyInput(branch_id=bm[0].id), "w1"
        )
    out = tools.weekly_summary(
        deps_for(session, bm[1]["Marites"]), WeeklyInput(branch_id=stall(session).id), "w2"
    )
    assert [b.branch_id for b in out.branches] == [stall(session).id]


def test_the_weekly_summary_reads_sales_and_stock(session: Session, bm: Ferinos) -> None:
    kiosk, people = bm
    out = tools.weekly_summary(deps_for(session, people["Rosa"]), WeeklyInput(), "w1")
    assert (out.start, out.end) == (dt.date(2026, 10, 19), dt.date(2026, 10, 25))
    by_branch = {b.branch_id: b for b in out.branches}
    assert set(by_branch) == {kiosk.id, stall(session).id}  # the owner sees every branch
    week = by_branch[kiosk.id]
    counts = live_counts(session, [kiosk.id], out.start, out.end)
    assert week.amount == sum(c.amount for c in counts) and week.target is not None
    assert week.waste == {item(session, "Ube").id: 8}
    assert week.experiment is not None and week.experiment.experiment_id == running(session).id
    mine = tools.weekly_summary(deps_for(session, people["Marites"]), WeeklyInput(), "w2")
    assert [b.branch_id for b in mine.branches] == [kiosk.id]


def test_the_weekly_target_is_seven_days_of_the_owners_month_target(
    session: Session, bm: Ferinos
) -> None:
    """Smoke test 21 Oct: a weekly target of PHP 1,083.88 against PHP 28,718.50 in sales was
    the seed's month target at a hundredth of its scale (PHP 4,800 a month). The owner's month
    target is PHP 120,000; a week of October (31 open days) is seven day shares of it."""
    from mia.core.models import SalesTarget

    kiosk, people = bm
    (row,) = session.exec(select(SalesTarget).where(SalesTarget.branch_id == kiosk.id)).all()
    assert (row.period, row.amount, row.set_by) == ("month", 12_000_000, people["Rosa"].id)
    out = tools.weekly_summary(deps_for(session, people["Rosa"]), WeeklyInput(), "w1")
    week = next(b for b in out.branches if b.branch_id == kiosk.id)
    assert week.target == 7 * ((12_000_000 + 15) // 31)  # PHP 27,096.79
    assert week.amount / 2 < week.target < week.amount * 2  # on the scale of the seeded sales


def test_the_monthly_letter_is_numbers(session: Session, bm: Ferinos) -> None:
    kiosk, people = bm
    deps = deps_for(session, people["Rosa"])
    october = tools.monthly_letter(deps, MonthlyInput(month=TODAY), "m1")
    counts = live_counts(session, [kiosk.id], october.start, october.end)
    assert october.amount == sum(c.amount for c in counts)
    assert october.clerks == {people["Ana"].id: october.amount}
    assert len(october.best_days) == 3 and october.best_days[0][1] >= october.best_days[1][1]
    september = tools.monthly_letter(deps, MonthlyInput(), "m2")  # the month before
    assert september.start == dt.date(2026, 9, 1) and september.amount == 0
    assert [e.strategy for e in september.decided] == ["bm.strategy.charm"]
    supervisor = call_tool(
        deps_for(session, people["Marites"]),
        BINDING[f"{MANIFEST.id}.monthly_letter"],
        MonthlyInput(),
        "m3",
    )
    assert supervisor["status"] == "denied"


def test_a_clerk_sees_only_their_own_coaching_rows(session: Session, bm: Ferinos) -> None:
    _, people = bm
    ana = tools.coaching(deps_for(session, people["Ana"]), CoachingInput(), "c1")
    assert [r.person_id for r in ana.rows] == [people["Ana"].id]
    assert ana.rows[0].units > 0 and ana.pairing is not None
    with pytest.raises(PermissionDenied):
        tools.coaching(
            deps_for(session, people["Ana"]), CoachingInput(person_id=people["Liza"].id), "c2"
        )
    egg = item(session, "Salted egg").id
    lead = tools.coaching(deps_for(session, people["Marites"]), CoachingInput(item_id=egg), "c3")
    counts = live_counts(session, [bm[0].id], lead.start, lead.end, egg)
    assert [(r.person_id, r.units) for r in lead.rows] == [
        (people["Ana"].id, sum(c.quantity for c in counts))
    ]
    assert lead.rows[0].before_units == 0 and lead.rows[0].improved  # no counts before 12 Oct


def test_how_to_sell_gives_the_notes_then_two_tips(session: Session, bm: Ferinos) -> None:
    kiosk, people = bm
    egg = item(session, "Salted egg")
    daily = tools.daily(session, kiosk.id, egg.id, TODAY - dt.timedelta(days=60), TODAY)
    best = max((d for d in daily if d > min(daily)), key=lambda d: daily[d][0])
    for day, themes in ((best, ["display", "sampling"]), (min(daily), ["weather"])):
        note = SalesNote(
            branch_id=kiosk.id,
            business_date=day,
            person_id=people["Ana"].id,
            text="x",
            themes=themes,
        )
        store.insert(session, note, Actor.person(people["Ana"]))
    deps = deps_for(session, people["Ana"])
    first = tools.how_to_sell(deps, HowToSellInput(item_id=egg.id), "h1")
    assert first.themes == ["display", "sampling"]  # the first day has no mean before it
    rows = {r.id: r for r in session.exec(select(Tip))}
    assert len(first.tips) == 2 and rows[first.tips[0].tip_id].item_id == egg.id
    assert all(rows[tip.tip_id].language == "fil" for tip in first.tips)
    again = tools.how_to_sell(deps, HowToSellInput(item_id=egg.id), "h2")
    assert not {tip.tip_id for tip in again.tips} & {tip.tip_id for tip in first.tips}
    given = session.exec(select(Coaching).where(Coaching.person_id == people["Ana"].id)).all()
    assert Counter(c.kind for c in given) == {"tip": 4}


def test_a_short_code_needs_no_approval_and_never_clashes(session: Session, bm: Ferinos) -> None:
    deps = deps_for(session, bm[1]["Marites"])
    out = tools.set_short_code(
        deps, SetShortCodeInput(item_id=item(session, "Salted egg").id, codes=["sx"]), "s1"
    )
    assert "sx" in out.codes and "se" in out.codes
    with pytest.raises(LookupError):
        BINDING[f"{MANIFEST.id}.set_short_code"].precheck(  # type: ignore[misc]
            deps, SetShortCodeInput(item_id=item(session, "Ube").id, codes=["itlog"]), "s2"
        )
    with pytest.raises(LookupError):  # another item's code
        tools.set_short_code(
            deps, SetShortCodeInput(item_id=item(session, "Ube").id, codes=["SX"]), "s3"
        )
    clerk = call_tool(
        deps_for(session, bm[1]["Ana"]),
        BINDING[f"{MANIFEST.id}.set_short_code"],
        SetShortCodeInput(item_id=item(session, "Ube").id, codes=["uu"]),
        "s4",
    )
    assert clerk["status"] == "denied"


# ---- fix round 1: trust boundaries ----------------------------------------------------------


def test_a_typed_price_under_a_strategy_that_does_not_hold_is_refused(
    session: Session, bm: Ferinos
) -> None:
    """Every proposal names its rationale: the increase strategy needs sell-outs, which Classic
    has none of, so a typed 44 under it is refused rather than carrying an empty rationale."""
    end_seeded_experiment(session)
    out = propose(session, bm[1]["Marites"], 4400, key="bm.strategy.increase")
    assert (out["status"], out["message"]) == ("invalid", "no_strategy")
    assert proposals_asked(session) == []


def test_a_forged_rationale_is_ignored(session: Session, bm: Ferinos) -> None:
    end_seeded_experiment(session)
    menu = len(session.exec(select(RetailItem)).all())
    args = ProposeExperimentInput(
        item_id=item(session, "Classic").id,
        to_price=9000,
        starts_on=TODAY + ONE_DAY,
        strategy_id=strategy(session, "bm.strategy.charm").id,
        rationale={"new_item": {"components": [], "from_price": 9000}},
    )
    out = call_tool(deps_for(session, bm[1]["Marites"]), BINDING[tools.PROPOSE], args, "e1")
    assert (out["status"], out["message"]) == ("invalid", "too_far")
    assert proposals_asked(session) == [] and len(session.exec(select(RetailItem)).all()) == menu
    assert "rationale" not in ProposeExperimentInput.model_json_schema()["properties"]


def test_a_price_change_on_an_item_in_an_experiment_is_refused(
    session: Session, bm: Ferinos
) -> None:
    deps, binding = deps_for(session, bm[1]["Rosa"]), BINDING[tools.CHANGE_PRICE]
    special = ChangePriceInput(
        item_id=item(session, "Special").id, price=4800, effective_on=TODAY + ONE_DAY
    )
    assert call_tool(deps, binding, special, "p1")["message"] == "open_experiment"  # running
    end_seeded_experiment(session)
    assert propose(session, bm[1]["Marites"])["status"] == "approval_required"
    assert change(session, bm[1]["Rosa"], 4800, "p2")["message"] == "open_experiment"  # pending
    # done, but its revert (5 Nov) has not taken effect: a price set now would be undone
    assert call_tool(deps, binding, special, "p3")["message"] == "open_experiment"


def test_an_experiment_approved_after_its_price_moved_is_refused(
    session: Session, bm: Ferinos
) -> None:
    kiosk, people = bm
    end_seeded_experiment(session)
    approval_id = propose(session, people["Marites"])["approval_id"]
    classic = item(session, "Classic")
    items.schedule_price(session, classic, kiosk.id, 3500, TODAY, Actor.system(kiosk.id))
    with pytest.raises(LookupError, match="too_far"):  # 44 pesos is 26 percent above 35
        decide(session, approval_id, people["Rosa"], "approved")
    assert session.exec(select(Experiment).where(Experiment.approval_id == approval_id)).all() == []


def test_an_experiment_approved_after_its_start_is_refused(
    session: Session, bm: Ferinos, pin: Pin
) -> None:
    end_seeded_experiment(session)
    approval_id = propose(session, bm[1]["Marites"])["approval_id"]
    pin(at(TODAY + ONE_DAY, 9, 30))  # the start is today now
    with pytest.raises(LookupError, match="starts_too_soon"):
        decide(session, approval_id, bm[1]["Rosa"], "approved")
    stmt = select(RetailItemPrice).where(RetailItemPrice.approval_id == approval_id)
    assert session.exec(stmt).all() == []


def test_a_price_approved_after_its_date_is_refused(
    session: Session, bm: Ferinos, pin: Pin
) -> None:
    args = ChangePriceInput(item_id=item(session, "Classic").id, price=4200, effective_on=TODAY)
    deps = deps_for(session, bm[1]["Marites"])
    approval_id = call_tool(deps, BINDING[tools.CHANGE_PRICE], args, "p1")["approval_id"]
    pin(at(TODAY + ONE_DAY, 9, 30))
    with pytest.raises(LookupError, match="in_the_past"):
        decide(session, approval_id, bm[1]["Rosa"], "approved")


def test_a_new_item_costs_the_sum_of_its_parts(session: Session, bm: Ferinos) -> None:
    kiosk, _ = bm
    classic, ube, actor = item(session, "Classic"), item(session, "Ube"), Actor.system(kiosk.id)
    box = items.create_variant(session, classic, "Classic x8", 30000, [classic.id] * 8, actor, "v1")
    assert box.cost == 8 * 2400
    assert (
        items.create_variant(
            session, classic, "C + U", 8000, [classic.id, ube.id], actor, "v2"
        ).cost
        is None
    )
    assert (
        items.create_variant(session, classic, "Classic Premium", 4800, [], actor, "v3").cost
        == 2400
    )


def test_a_clerk_calling_the_lead_tools_directly_is_denied(session: Session, bm: Ferinos) -> None:
    _, people = bm
    deps = deps_for(session, people["Ana"])
    with pytest.raises(PermissionDenied):
        tools.weekly_summary(deps, WeeklyInput(), "d1")
    with pytest.raises(PermissionDenied):
        tools.monthly_letter(deps, MonthlyInput(), "d2")
    with pytest.raises(PermissionDenied):
        tools.coaching(deps, CoachingInput(person_id=people["Liza"].id), "d3")


def test_the_owner_sees_her_own_price_change_in_her_inbox(session: Session, bm: Ferinos) -> None:
    _, people = bm
    own = change(session, people["Rosa"], 4800)["approval_id"]
    assert own in {a.id for a in scheduling.inbox(session, Actor.person(people["Rosa"]))}


def test_a_handler_finds_the_agent_role_after_startup(
    session: Session, bm: Ferinos, fresh_rbac: None
) -> None:
    from fastapi.testclient import TestClient

    from mia.api.main import app

    _, people = bm
    roles = MANIFEST.roles
    get_rbac().load_agent_role(roles.agent_role, roles.grants, roles.denies)  # for the request
    approval_id = change(session, people["Marites"], 4800)["approval_id"]
    get_rbac.cache_clear()  # a node that ran no turn: no agent role loaded
    url, rosa = f"/approvals/{approval_id}/decide", {"X-Mia-Actor": people["Rosa"].id}
    res = TestClient(app).post(url, json={"outcome": "approved"}, headers=rosa)
    assert res.status_code == 403, res.text
    with TestClient(app) as client:  # the lifespan loads every built agent's roles
        res = client.post(url, json={"outcome": "approved"}, headers=rosa)
    assert res.status_code == 200, res.text
    session.expire_all()
    stmt = select(RetailItemPrice).where(RetailItemPrice.approval_id == approval_id)
    assert session.exec(stmt).one().price == 4800


# ---- fix round 2: refusals at approval time ---------------------------------------------------


def test_a_new_item_is_guarded_against_the_base_price_at_approval(
    session: Session, bm: Ferinos
) -> None:
    kiosk, people = bm
    end_seeded_experiment(session)
    approval_id = propose(session, people["Marites"], None, key="bm.strategy.anchor", name="Ube")[
        "approval_id"
    ]
    items.schedule_price(
        session, item(session, "Ube"), kiosk.id, 4400, TODAY, Actor.system(kiosk.id)
    )
    with pytest.raises(LookupError, match="too_far"):  # 54 pesos is 23 percent above 44
        decide(session, approval_id, people["Rosa"], "approved")


def test_a_refused_approval_is_closed_with_its_reason(session: Session, bm: Ferinos) -> None:
    from fastapi.testclient import TestClient

    from mia.api.main import app

    kiosk, people = bm
    end_seeded_experiment(session)
    menu = len(session.exec(select(RetailItem)).all())
    approval_id = propose(session, people["Marites"], None, key="bm.strategy.anchor", name="Ube")[
        "approval_id"
    ]
    items.schedule_price(
        session, item(session, "Ube"), kiosk.id, 4400, TODAY, Actor.system(kiosk.id)
    )
    session.commit()
    url, rosa = f"/approvals/{approval_id}/decide", {"X-Mia-Actor": people["Rosa"].id}
    res = TestClient(app).post(url, json={"outcome": "approved"}, headers=rosa)
    assert (res.status_code, res.json()["detail"]) == (409, "too_far")
    session.expire_all()
    approval = session.get(Approval, approval_id)
    assert approval is not None and (approval.status, approval.reason) == ("expired", "too_far")
    assert len(session.exec(select(RetailItem)).all()) == menu
    assert session.exec(select(Experiment).where(Experiment.approval_id == approval_id)).all() == []
    stmt = select(RetailItemPrice).where(RetailItemPrice.approval_id == approval_id)
    assert session.exec(stmt).all() == []
    chain = session.exec(
        select(Event.action).where(Event.entity_id == approval_id).order_by(col(Event.id))
    ).all()
    assert [a for a in chain if a.startswith("approval.")][-2:] == [
        "approval.refused",  # no approval.approved: nothing was approved
        "approval.expired",
    ]
    said = t("bm.experiment_refused.too_far", "fil", **tools.WORDED)
    assert said in told(session, people["Marites"]) and "20%" in said  # the constant, worded
    res = TestClient(app).post(url, json={"outcome": "approved"}, headers=rosa)
    assert res.status_code == 403  # closed: no retry loop


def test_the_cli_says_refused_and_closes_the_request(
    session: Session, bm: Ferinos, pin: Pin, capsys: pytest.CaptureFixture[str]
) -> None:
    from mia.cli import main

    args = ChangePriceInput(item_id=item(session, "Classic").id, price=4200, effective_on=TODAY)
    deps = deps_for(session, bm[1]["Marites"])
    approval_id = call_tool(deps, BINDING[tools.CHANGE_PRICE], args, "p1")["approval_id"]
    pin(at(TODAY + ONE_DAY, 9, 30))
    assert main(["decide", approval_id, "approved", "--as", "Rosa"]) == 1
    assert "refused: in_the_past" in capsys.readouterr().out
    session.expire_all()
    approval = session.get(Approval, approval_id)
    assert approval is not None and (approval.status, approval.reason) == ("expired", "in_the_past")
    assert t("bm.price_refused.in_the_past", "fil") in told(session, bm[1]["Marites"])


# ---- fix wave: dated prices never undone, every refusal worded ------------------------------


def test_an_experiment_over_a_scheduled_price_is_refused(session: Session, bm: Ferinos) -> None:
    kiosk, people = bm
    end_seeded_experiment(session)
    decide(
        session, change(session, people["Rosa"], 4200)["approval_id"], people["Rosa"], "approved"
    )
    out = propose(session, people["Marites"])  # its revert row would undo the owner's 42
    assert (out["status"], out["message"]) == ("invalid", "price_scheduled")
    assert replies.refusal_key("price_scheduled") == "bm.refused.price_scheduled"  # worded
    assert items.price_on(session, item(session, "Classic"), kiosk.id, TODAY + 30 * ONE_DAY) == 4200


def test_a_price_scheduled_while_an_experiment_waits_refuses_its_approval(
    session: Session, bm: Ferinos
) -> None:
    kiosk, people = bm
    end_seeded_experiment(session)
    approval_id = propose(session, people["Marites"])["approval_id"]
    classic = item(session, "Classic")
    items.schedule_price(
        session, classic, kiosk.id, 4200, TODAY + 7 * ONE_DAY, Actor.system(kiosk.id)
    )
    with pytest.raises(LookupError, match="price_scheduled"):
        decide(session, approval_id, people["Rosa"], "approved")


def test_a_price_dated_inside_a_done_experiment_waits_for_its_revert(
    session: Session, bm: Ferinos, pin: Pin
) -> None:
    kiosk, people = bm
    end_seeded_experiment(session)
    decide(session, propose(session, people["Marites"])["approval_id"], people["Rosa"], "approved")
    tools.experiment_tick(session, kiosk, hours(session, kiosk), pin(at(TODAY + ONE_DAY, 9, 5)))
    row = session.exec(select(Experiment).where(Experiment.status == "running")).one()
    tools.experiment_tick(session, kiosk, hours(session, kiosk), pin(at(row.ends_on, 22, 30)))
    session.refresh(row)
    assert row.status == "done"
    deps, binding = deps_for(session, people["Rosa"]), BINDING[tools.CHANGE_PRICE]
    classic = item(session, "Classic").id
    for on, call in ((row.ends_on, "p1"), (row.ends_on + ONE_DAY, "p2")):
        args = ChangePriceInput(item_id=classic, price=4600, effective_on=on)
        assert call_tool(deps, binding, args, call)["message"] == "open_experiment"
    tools.experiment_tick(
        session, kiosk, hours(session, kiosk), pin(at(row.ends_on + ONE_DAY, 9, 5))
    )
    args = ChangePriceInput(item_id=classic, price=4600, effective_on=row.ends_on + 2 * ONE_DAY)
    assert call_tool(deps, binding, args, "p3")["status"] == "approval_required"


def test_an_unknown_refusal_reason_is_told_in_plain_words(session: Session, bm: Ferinos) -> None:
    _, people = bm
    end_seeded_experiment(session)
    approval_id = propose(session, people["Marites"])["approval_id"]
    approvals.close_refused(session, approval_id, Actor.person(people["Rosa"]), "the requester")
    said = told(session, people["Marites"])
    assert t("bm.experiment_refused.other", "fil") in said
    assert not [m for m in said if "bm.experiment_refused" in m]  # never a raw key
    price_id = change(session, people["Marites"], 4800)["approval_id"]
    approvals.close_refused(session, price_id, Actor.person(people["Rosa"]), "no input")
    assert t("bm.price_refused.other", "fil") in told(session, people["Marites"])


def test_the_cli_never_decides_an_owners_own_request(
    session: Session, bm: Ferinos, capsys: pytest.CaptureFixture[str]
) -> None:
    """D37 needs the PIN step-up; the shell takes none, so from the shell an owner's own money
    request waits for another approver (another's request the shell still decides, ADR 011)."""
    from mia.cli import main

    approval_id = change(session, bm[1]["Rosa"], 4800)["approval_id"]
    session.commit()
    assert main(["decide", approval_id, "approved", "--as", "Rosa"]) == 1
    assert "refused: nobody approves a request they made or triggered" in capsys.readouterr().out
    session.expire_all()
    approval = session.get(Approval, approval_id)
    assert approval is not None and approval.status == "pending"
