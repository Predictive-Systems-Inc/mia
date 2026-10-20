"""The production planner's data on the Ferino's seed (pp, PP_TODAY a Tuesday): the commissary
is a branch without retail hours with its head and driver, who is offered the planner, the
rights on the kiosks' counts, stock and orders (the agent alone reads across branches), and the
kiosk agents' due work skipping the commissary (negative tests first; the clock pinned through
pp_pin, never the wall clock)."""

import datetime as dt
from collections import Counter
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.agents.bookkeeper import due as bk_due
from mia.agents.branch_manager import due as bm_due
from mia.agents.customer_service import due as cs_due
from mia.agents.inventory_manager import due as inventory_due
from mia.agents.production_planner import MANIFEST, capacity, forecast, tools
from mia.agents.production_planner.models import Batch, Dispatch, Plan, Recipe
from mia.agents.sales_supervisor import due as sales_due
from mia.chat.access import agents_for
from mia.core import orgconfig, store
from mia.core.models import Actor, Branch, Event, Message, Person, StockEvent, Thread
from mia.core.rbac import get_rbac
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailIngredient, RetailItem
from tests.conftest import PP_TODAY, PP_TOMORROW, Pin

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")
ONE_DAY = dt.timedelta(days=1)
BINDING = {b.tool_id: b for b in tools.BINDINGS}


def _branch(session: Session, name: str) -> Branch:
    row = session.exec(select(Branch).where(Branch.name == name)).one()
    return row


def comm(session: Session) -> Branch:
    """The commissary, by the name in the planner's settings."""
    return _branch(session, orgconfig.load().production_planner.commissary)


def stall(session: Session) -> Branch:
    """The Street stall (the second served kiosk)."""
    return _branch(session, orgconfig.load().production_planner.serves[1])


def item(session: Session, name: str) -> RetailItem:
    return session.exec(select(RetailItem).where(RetailItem.name == name)).one()


def deps_for(session: Session, person: Person) -> AgentDeps:
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=PP_TODAY,
        lang=person.language or "en",
        manifest=MANIFEST,
    )


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), MNL)


def draft(session: Session) -> Plan:
    """Tomorrow's draft plan at the commissary (tools.draft_plan)."""
    return tools.draft_plan(session, comm(session), PP_TOMORROW)


def notifications(session: Session, person: Person) -> list[Message]:
    """Every notification any agent sent the person."""
    threads = select(Thread.id).where(Thread.person_id == person.id)
    stmt = select(Message).where(col(Message.thread_id).in_(threads))
    return list(session.exec(stmt.where(Message.role == "notification")).all())


def test_no_person_reads_another_branchs_counts_stock_or_orders() -> None:
    enforce = get_rbac().enforcer.enforce
    for table in ("sales_counts", "stock_events", "customer_orders"):
        people = ("customer", "staff", "clerk", "supervisor")
        assert [r for r in people if enforce(r, "B", f"data:{table}", "read_all")] == []
        assert enforce("agent.production_planner", "B", f"data:{table}", "read_all")


def test_kiosk_due_work_skips_the_commissary(session: Session, pp: Ferinos, pp_pin: Pin) -> None:
    for hour in (6, 9, 10, 14, 20, 22):
        now = pp_pin(at(PP_TODAY, hour, 5))
        for run in (
            sales_due.run_due,
            inventory_due.run_due,
            bm_due.run_due,
            cs_due.run_due,
            bk_due.run_due,
        ):
            run(session, now)
    assert notifications(session, pp[1]["Nonoy"]) == notifications(session, pp[1]["Berto"]) == []
    assert notifications(session, pp[1]["Marites"])  # the kiosk agents did run at the Mall


def test_the_commissary_is_a_branch_without_retail_hours(session: Session, pp: Ferinos) -> None:
    c = comm(session)
    here = {p.name for p in session.exec(select(Person).where(Person.branch_id == c.id))}
    assert (c.timezone, retail_hours.load(session, c.id), here) == (
        "Asia/Manila",
        [],
        {"Nonoy", "Berto"},
    )
    assert (pp[1]["Berto"].skills, pp[1]["Nonoy"].roles) == (["driver"], ["supervisor"])
    assert not retail_hours.is_shop(session, c.id)
    assert retail_hours.is_shop(session, pp[0].id) and retail_hours.is_shop(
        session, stall(session).id
    )


def test_who_is_offered_the_planner(session: Session, pp: Ferinos) -> None:
    def offered(who: str) -> bool:
        return MANIFEST.id in [a.manifest.id for a in agents_for(session, pp[1][who])]

    assert [offered(w) for w in ("Nonoy", "Berto", "Marites", "Rosa", "Ana")] == [
        True,
        True,
        True,
        True,
        False,
    ]


def test_the_seeded_recipes(session: Session, pp: Ferinos) -> None:
    """Six recipes at the commissary: Classic and Puto bumbong 48 pieces, the others 36, every
    one 45 oven minutes; Classic's lines as given, the 36-piece base scaled exactly, plus the
    item's own ingredient; Kape and Box of 4 have none."""
    names = {i.id: i.name for i in session.exec(select(RetailItem))}
    ingredients = {i.id: i.name for i in session.exec(select(RetailIngredient))}
    rows = session.exec(select(Recipe)).all()
    got = {
        names[r.item_id]: (
            r.branch_id,
            r.batch_yield,
            r.oven_minutes,
            {ingredients[x["ingredient_id"]]: x["quantity_milli"] for x in r.lines},
        )
        for r in rows
    }
    c = comm(session).id
    base36 = {"Rice flour": 1500, "Eggs": 750, "Coconut": 4500, "Sugar": 750, "Banana leaves": 750}
    classic = {
        "Rice flour": 2000,
        "Eggs": 1000,
        "Coconut": 6000,
        "Sugar": 1000,
        "Banana leaves": 1000,
    }
    assert got == {
        "Classic": (c, 48, 45, classic),
        "Special": (c, 36, 45, base36),
        "Ube": (c, 36, 45, base36),
        "Salted egg": (c, 36, 45, base36 | {"Salted duck eggs": 12000}),
        "Cheese overload": (c, 36, 45, base36 | {"Cheese": 500}),
        "Puto bumbong": (c, 48, 45, classic),
    }
    assert all(not r.keeps_overnight and r.active for r in rows)


def test_the_seeded_day_comes_from_the_same_functions(session: Session, pp: Ferinos) -> None:
    plan = session.exec(select(Plan).where(Plan.production_date == PP_TODAY - ONE_DAY)).one()
    assert plan.status == "confirmed"
    assert all(k["forecast"] is None for line in plan.lines for k in line["kiosks"])
    sent = {
        d.branch_id: d for d in session.exec(select(Dispatch).where(Dispatch.plan_id == plan.id))
    }
    good: Counter[str] = Counter()
    for b in session.exec(select(Batch).where(Batch.plan_id == plan.id)):
        good[b.item_id] += b.good
    for line in plan.lines:
        want = forecast.dispatch_split(
            good[line["item_id"]], {k["branch_id"]: k["pieces"] for k in line["kiosks"]}
        )
        assert all(
            next((x["quantity"] for x in sent[k].lines if x["item_id"] == line["item_id"]), 0) == q
            for k, q in want.items()
        )
    assert sorted(d.status for d in sent.values()) == ["matched", "short"]
    classic = item(session, "Classic").id
    assert {x["item_id"]: x["batches"] for x in plan.lines}[classic] == 3
    burnt = session.exec(
        select(Batch).where(Batch.item_id == classic).where(Batch.batch_no == 3)
    ).one()
    assert (burnt.good, burnt.waste, burnt.reason, burnt.planned_yield) == (40, 8, "burnt", 48)
    short = sent[stall(session).id]
    got = {x["item_id"]: x["quantity"] for x in short.received or []}
    assert (short.status, got[classic]) == (
        "short",
        next(x["quantity"] for x in short.lines if x["item_id"] == classic) - 4,
    )


def test_the_draft_is_written_once_by_the_agent_alone(session: Session, pp: Ferinos) -> None:
    plan = draft(session)
    assert draft(session).id == plan.id and plan.status == "draft"
    drafted = session.exec(select(Event).where(Event.action == f"{MANIFEST.id}.plan_drafted")).all()
    assert [
        (e.entity_id, e.actor_id, e.on_behalf_of) for e in drafted if e.entity_id == plan.id
    ] == [(plan.id, MANIFEST.roles.agent_role, None)]
    assert [x["item_id"] for x in plan.lines] == [
        r.item_id for r in tools.recipes(session, comm(session).id)
    ]
    assert all(k["forecast"] is not None for x in plan.lines for k in x["kiosks"])  # two Wednesdays
    assert all(x["pieces"] == sum(k["pieces"] for k in x["kiosks"]) for x in plan.lines)
    with pytest.raises(LookupError, match="not_served"):
        tools.kiosk_data(session, comm(session), comm(session), PP_TOMORROW)


def test_confirmed_orders_of_the_pickup_date_count(session: Session, pp: Ferinos) -> None:
    """The seed's confirmed pickup of 10 Classic today at the Mall kiosk counts for today's
    production; the picked-up order of yesterday does not."""
    data = tools.kiosk_data(session, comm(session), pp[0], PP_TODAY)
    classic = item(session, "Classic").id
    assert (
        data.orders,
        tools.kiosk_data(session, comm(session), pp[0], PP_TODAY - ONE_DAY).orders,
    ) == ({classic: 10}, {})
    assert data.leftovers == {}  # no recipe keeps overnight (Q93)


def test_a_change_splits_again_and_capacity_counts_it(session: Session, pp: Ferinos) -> None:
    plan, ube = draft(session), item(session, "Ube").id
    before = capacity.free(session, comm(session).id, PP_TOMORROW).minutes_free
    old = next(x for x in plan.lines if x["item_id"] == ube)["batches"]
    head = Actor.person(pp[1]["Nonoy"]).as_agent(MANIFEST.roles.agent_role)
    plan = tools.set_batches(session, plan, ube, old + 2, head, note="fiesta")
    line = next(x for x in plan.lines if x["item_id"] == ube)
    assert (line["batches"], line["pieces"], line["changed_by"], line["change_note"]) == (
        old + 2,
        (old + 2) * 36,
        pp[1]["Nonoy"].id,
        "fiesta",
    )
    assert sum(k["pieces"] for k in line["kiosks"]) == line["pieces"]
    assert capacity.free(session, comm(session).id, PP_TOMORROW).minutes_free == max(0, before - 90)
    assert session.get(Plan, plan.id).lines == plan.lines  # stored
    with pytest.raises(LookupError, match="not_planned"):
        tools.set_batches(session, plan, item(session, "Kape").id, 1, head)


def test_a_repeated_batch_corrects_and_pack_and_match_are_once(
    session: Session, pp: Ferinos
) -> None:
    plan, classic, head = draft(session), item(session, "Classic").id, pp[1]["Nonoy"]
    plan = tools.set_batches(session, plan, classic, 2, Actor.person(head))
    first = tools.save_batch(
        session,
        plan,
        tools.BatchInput(item_id=classic, batch_no=1, good=30),
        head,
        Actor.person(head),
        at=at(PP_TOMORROW, 4),
    )
    again = tools.save_batch(
        session,
        plan,
        tools.BatchInput(item_id=classic, batch_no=1, good=44, waste=4, reason="dropped"),
        head,
        Actor.person(head),
        at=at(PP_TOMORROW, 4, 10),
    )
    assert again.id == first.id and (again.good, again.waste) == (44, 4)
    assert tools.good_pieces(session, plan)[classic] == 44 + 48  # batch 2 counts its planned yield
    with pytest.raises(LookupError, match="not_planned"):
        tools.save_batch(
            session,
            plan,
            tools.BatchInput(item_id=item(session, "Kape").id, batch_no=1, good=1),
            head,
            Actor.person(head),
        )
    agent = tools.agent_actor(comm(session).id)
    packed = tools.pack(session, plan, agent)
    assert {d.id for d in tools.pack(session, plan, agent)} == {d.id for d in packed}
    mall = next(d for d in packed if d.branch_id == pp[0].id)
    sent = {x["item_id"]: x["quantity"] for x in mall.lines}
    assert (
        tools.match(session, mall, at(PP_TOMORROW, 10), tools.agent_actor(mall.branch_id))
        == "short"
    )  # no receipt
    for item_id, quantity in sent.items():
        row = StockEvent(
            branch_id=mall.branch_id,
            kind="received",
            item_id=item_id,
            quantity=quantity,
            unit="pcs",
            at=at(PP_TOMORROW, 9),
            reported_by=pp[1]["Marites"].id,
            business_date=PP_TOMORROW,
        )
        store.insert(session, row, Actor.system(mall.branch_id))
    assert (
        tools.match(session, mall, at(PP_TOMORROW, 8), tools.agent_actor(mall.branch_id)) == "short"
    )  # not yet
    assert (
        tools.match(session, mall, at(PP_TOMORROW, 10), tools.agent_actor(mall.branch_id))
        == "matched"
    )
    assert {x["item_id"]: x["quantity"] for x in mall.received or []} == sent
