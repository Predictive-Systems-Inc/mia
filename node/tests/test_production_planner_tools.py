"""The production planner's data on the Ferino's seed (pp, PP_TODAY a Tuesday): the commissary
is a branch without retail hours with its head and driver, who is offered the planner, the
rights on the kiosks' counts, stock and orders (the agent alone reads across branches), and the
kiosk agents' due work skipping the commissary, and the nine tools behind rbac with their
prechecks (negative tests first; the clock pinned through pp_pin, never the wall clock)."""

import datetime as dt
from collections import Counter
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import BaseModel
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.bookkeeper import due as bk_due
from mia.agents.branch_manager import due as bm_due
from mia.agents.customer_service import due as cs_due
from mia.agents.inventory_manager import due as inventory_due
from mia.agents.production_planner import MANIFEST, capacity, forecast, tools
from mia.agents.production_planner.models import Batch, Dispatch, Plan, Recipe
from mia.agents.production_planner.tools import (
    BatchInput,
    BatchSheetInput,
    CapacityInput,
    ChangePlanInput,
    ConfirmPlanInput,
    DeliveredInput,
    DispatchInput,
    PlanInput,
    RecipeInput,
    RecipeLine,
)
from mia.agents.sales_supervisor import due as sales_due
from mia.chat.access import agents_for
from mia.core import orgconfig, people, store
from mia.core.models import Actor, Branch, Event, Message, Person, StockEvent, Thread
from mia.core.rbac import PermissionDenied, Rbac, Resource, get_rbac
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


# ---- the tools ----------------------------------------------------------------------------


def ing(session: Session, name: str) -> str:
    return session.exec(select(RetailIngredient).where(RetailIngredient.name == name)).one().id


def recipe(session: Session, item_id: str) -> Recipe:
    """The item's active recipe."""
    return next(r for r in tools.recipes(session, comm(session).id) if r.item_id == item_id)


def plan_row(session: Session) -> Plan:
    """Tomorrow's plan row, fresh from the database."""
    row = tools.plan_for(session, comm(session).id, PP_TOMORROW)
    assert row is not None
    session.refresh(row)
    return row


def plan_batches(session: Session, item_id: str) -> int:
    return int(next(x["batches"] for x in plan_row(session).lines if x["item_id"] == item_id))


REFUSED = {"denied", "invalid", "approval_required"}


def run(session: Session, person: Person, tool: str, args: BaseModel) -> dict[str, Any]:
    """The tool's JSON result through call_tool (the guard, the precheck, the log)."""
    return call_tool(deps_for(session, person), BINDING[f"{MANIFEST.id}.{tool}"], args, tool)


def outcome(out: dict[str, Any]) -> str:
    """A refusal's status, else ok (a plan or dispatch output carries its own status field)."""
    return str(out["status"]) if out.get("status") in REFUSED else "ok"


def caller(session: Session, pp: Ferinos) -> Callable[[str, str, BaseModel], str]:
    """call(who, tool, args): the outcome of the tool run as that person."""
    return lambda who, tool, args: outcome(run(session, pp[1][who], tool, args))


def packed(session: Session, people: dict[str, Person], pin: Pin) -> Plan:
    """Drafted at 14:05 on PP_TODAY, Classic set to 3 batches and confirmed by Nonoy, then at
    04:00 on PP_TOMORROW every batch recorded at full yield, which packs."""
    pin(at(PP_TODAY, 14, 5))
    draft(session)
    classic, head = item(session, "Classic").id, people["Nonoy"]
    change = ChangePlanInput(item_id=classic, batches=3)
    assert outcome(run(session, head, "change_plan", change)) == "ok"
    assert outcome(run(session, head, "confirm_plan", ConfirmPlanInput())) == "ok"
    pin(at(PP_TOMORROW, 4, 0))
    for line in plan_row(session).lines:
        full = recipe(session, line["item_id"]).batch_yield
        for n in range(1, line["batches"] + 1):
            args = BatchInput(item_id=line["item_id"], batch_no=n, good=full)
            assert outcome(run(session, head, "record_batch", args)) == "ok"
    return plan_row(session)


def test_a_supervisor_cannot_set_a_recipe(session: Session, pp: Ferinos) -> None:
    call = caller(session, pp)
    args = RecipeInput(
        item_id=item(session, "Classic").id,
        batch_yield=50,
        oven_minutes=45,
        lines=[RecipeLine(ingredient_id=ing(session, "Eggs"), quantity_milli=1000)],
    )
    assert [call(w, "set_recipe", args) for w in ("Nonoy", "Marites", "Berto")] == ["denied"] * 3
    assert recipe(session, args.item_id).batch_yield == 48


def test_a_kiosk_supervisor_cannot_change_the_plan(session: Session, pp: Ferinos) -> None:
    call = caller(session, pp)
    draft(session)
    before = plan_row(session).lines
    change = ChangePlanInput(
        item_id=item(session, "Classic").id, batches=9, production_date=PP_TOMORROW
    )
    assert call("Marites", "change_plan", change) == "denied"
    assert plan_row(session).lines == before
    assert call("Marites", "dispatch_list", DispatchInput(kiosk_id=stall(session).id)) == "denied"


def test_a_driver_only_confirms(session: Session, pp: Ferinos, pp_pin: Pin) -> None:
    call = caller(session, pp)
    packed(session, pp[1], pp_pin)
    classic = item(session, "Classic").id
    for tool, args in (
        ("plan", PlanInput()),
        ("change_plan", ChangePlanInput(item_id=classic, batches=1)),
        ("record_batch", BatchInput(item_id=classic, batch_no=1, good=48)),
        ("batch_sheet", BatchSheetInput(item_id=classic)),
        ("capacity", CapacityInput(day=PP_TOMORROW)),
    ):
        assert call("Berto", tool, args) == "denied"
    assert call("Berto", "confirm_delivery", DeliveredInput(kiosk_id=pp[0].id)) == "ok"


def test_a_staff_without_the_driver_skill_cannot_confirm(
    session: Session, pp: Ferinos, pp_pin: Pin
) -> None:
    call = caller(session, pp)
    packed(session, pp[1], pp_pin)
    helper = people.add_person(
        session,
        Actor.system(comm(session).id),
        branch_id=comm(session).id,
        name="Jojo",
        roles=["staff"],
        language="fil",
    )
    out = call_tool(
        deps_for(session, helper),
        BINDING[f"{MANIFEST.id}.confirm_delivery"],
        DeliveredInput(kiosk_id=pp[0].id),
        "d",
    )
    assert out["status"] == "invalid" and "not_driver" in out["message"]
    assert call("Marites", "confirm_delivery", DeliveredInput(kiosk_id=pp[0].id)) == "invalid"


def test_the_owner_confirms_a_delivery_from_any_branch(
    session: Session, pp: Ferinos, pp_pin: Pin
) -> None:
    call = caller(session, pp)
    packed(session, pp[1], pp_pin)
    assert pp[1]["Rosa"].branch_id != comm(session).id
    assert call("Marites", "confirm_delivery", DeliveredInput(kiosk_id=pp[0].id)) == "invalid"
    assert call("Rosa", "confirm_delivery", DeliveredInput(kiosk_id=pp[0].id)) == "ok"
    assert call("Berto", "confirm_delivery", DeliveredInput(kiosk_id=stall(session).id)) == "ok"
    rows = session.exec(select(Dispatch).where(Dispatch.business_date == PP_TOMORROW)).all()
    by = {d.branch_id: d.delivered_by for d in rows}
    assert by == {pp[0].id: pp[1]["Rosa"].id, stall(session).id: pp[1]["Berto"].id}


def test_a_plan_is_confirmed_once_and_never_in_the_past(session: Session, pp: Ferinos) -> None:
    call = caller(session, pp)
    draft(session)
    for _ in range(2):
        assert call("Nonoy", "confirm_plan", ConfirmPlanInput()) == "ok"
    confirmed = session.exec(
        select(Event)
        .where(Event.action == f"{MANIFEST.id}.plan_confirmed")
        .where(Event.entity_id == plan_row(session).id)
    ).all()
    assert len(confirmed) == 1 and plan_row(session).status == "confirmed"
    past = ConfirmPlanInput(production_date=PP_TODAY - ONE_DAY)
    assert call("Nonoy", "confirm_plan", past) == "invalid"


def test_the_capacity_precheck_refuses_a_change_past_the_ovens(
    session: Session, pp: Ferinos
) -> None:
    call = caller(session, pp)
    draft(session)
    ube = item(session, "Ube").id
    free = capacity.free(session, comm(session).id, PP_TOMORROW).minutes_free
    too_many = plan_batches(session, ube) + free // 45 + 1
    change = ChangePlanInput(item_id=ube, batches=too_many, production_date=PP_TOMORROW)
    assert call("Nonoy", "change_plan", change) == "invalid"
    assert capacity.free(session, comm(session).id, PP_TOMORROW).minutes_free == free


def test_a_past_plan_cannot_change(session: Session, pp: Ferinos) -> None:
    call = caller(session, pp)
    change = ChangePlanInput(
        item_id=item(session, "Classic").id, batches=1, production_date=PP_TODAY - ONE_DAY
    )
    assert call("Nonoy", "change_plan", change) == "invalid"


def test_a_batch_beyond_twice_the_yield_is_refused(
    session: Session, pp: Ferinos, pp_pin: Pin
) -> None:
    call = caller(session, pp)
    draft(session)
    pp_pin(at(PP_TOMORROW, 4, 0))
    classic = item(session, "Classic").id
    assert [
        call("Nonoy", "record_batch", BatchInput(item_id=classic, batch_no=1, good=g, waste=w))
        for g, w in ((90, 7), (90, 6))
    ] == ["invalid", "ok"]


def test_kiosk_counts_are_read_by_the_agent_alone(session: Session, pp: Ferinos) -> None:
    draft(session)
    reads = [
        e
        for e in session.exec(select(Event).where(Event.action == "rbac.allow"))
        if (e.after or {}).get("resource")
        in {"data:sales_counts", "data:stock_events", "data:customer_orders"}
    ]
    assert len({(e.after or {})["resource"] for e in reads}) == 3
    assert all((e.actor_id, e.on_behalf_of) == (MANIFEST.roles.agent_role, None) for e in reads)
    with pytest.raises(LookupError, match="not_served"):
        tools.kiosk_data(session, comm(session), comm(session), PP_TOMORROW)


def test_the_last_batch_packs_the_dispatch(session: Session, pp: Ferinos, pp_pin: Pin) -> None:
    plan = packed(session, pp[1], pp_pin)
    rows = session.exec(select(Dispatch).where(Dispatch.plan_id == plan.id)).all()
    assert {d.branch_id for d in rows} == {pp[0].id, stall(session).id}
    assert {d.status for d in rows} == {"packed"}
    assert {d.from_branch_id for d in rows} == {comm(session).id}
    for who in ("Nonoy", "Berto"):  # the head and the driver, urgent, one list per kiosk
        assert len(notifications(session, pp[1][who])) == 2
    assert notifications(session, pp[1]["Marites"]) == []


def test_the_driver_and_the_kiosk_see_their_own_dispatches(
    session: Session, pp: Ferinos, pp_pin: Pin
) -> None:
    packed(session, pp[1], pp_pin)
    mall = run(session, pp[1]["Marites"], "dispatch_list", DispatchInput())
    assert [d["branch_id"] for d in mall["dispatches"]] == [pp[0].id]
    sent = run(session, pp[1]["Berto"], "dispatch_list", DispatchInput())
    assert {d["branch_id"] for d in sent["dispatches"]} == {pp[0].id, stall(session).id}
    done = run(session, pp[1]["Berto"], "confirm_delivery", DeliveredInput(kiosk_id=pp[0].id))
    row = session.exec(select(Dispatch).where(Dispatch.branch_id == pp[0].id)).all()
    got = next(d for d in row if d.business_date == PP_TOMORROW)
    assert (done["status"], got.status, got.delivered_by) == (
        "delivered",
        "delivered",
        pp[1]["Berto"].id,
    )


def test_a_kiosk_supervisor_reads_the_plan_of_their_kiosk_only(
    session: Session, pp: Ferinos
) -> None:
    assert run(session, pp[1]["Nonoy"], "plan", PlanInput())["status"] == "invalid"  # no_plan
    draft(session)
    out = run(session, pp[1]["Marites"], "plan", PlanInput())
    kiosks = {k["branch_id"] for x in out["lines"] for k in x["kiosks"]}
    assert kiosks == {pp[0].id}
    full = run(session, pp[1]["Nonoy"], "plan", PlanInput())
    assert {k["branch_id"] for x in full["lines"] for k in x["kiosks"]} == {
        pp[0].id,
        stall(session).id,
    }


def test_the_owner_sets_a_recipe_and_the_old_one_retires(session: Session, pp: Ferinos) -> None:
    classic = item(session, "Classic").id
    args = RecipeInput(
        item_id=classic,
        batch_yield=50,
        oven_minutes=40,
        lines=[RecipeLine(ingredient_id=ing(session, "Eggs"), quantity_milli=1000)],
    )
    box = args.model_copy(update={"item_id": item(session, "Box of 4").id})
    assert run(session, pp[1]["Rosa"], "set_recipe", box)["status"] == "invalid"  # a bundle
    assert outcome(run(session, pp[1]["Rosa"], "set_recipe", args)) == "ok"
    rows = session.exec(select(Recipe).where(Recipe.item_id == classic)).all()
    assert sorted((r.active, r.batch_yield) for r in rows) == [(False, 48), (True, 50)]


def test_the_batch_sheet_and_capacity(session: Session, pp: Ferinos) -> None:
    draft(session)
    classic = item(session, "Classic").id
    sheet = run(session, pp[1]["Nonoy"], "batch_sheet", BatchSheetInput(item_id=classic))
    batches = plan_batches(session, classic)
    eggs = next(x for x in sheet["lines"] if x["ingredient_id"] == ing(session, "Eggs"))
    assert (sheet["batches"], eggs["quantity_milli"]) == (batches, 1000 * batches)
    free = capacity.free(session, comm(session).id, PP_TOMORROW)
    out = run(
        session,
        pp[1]["Nonoy"],
        "capacity",
        CapacityInput(day=PP_TOMORROW, item_id=classic, pieces=free.per_item[classic] + 1),
    )
    assert (out["minutes_free"], out["fits"]) == (free.minutes_free, False)
    kape = CapacityInput(day=PP_TOMORROW, item_id=item(session, "Kape").id)
    assert run(session, pp[1]["Nonoy"], "capacity", kape)["status"] == "invalid"  # no_recipe


def test_a_batch_number_beyond_the_plan_is_not_planned(session: Session, pp: Ferinos) -> None:
    plan, classic, head = draft(session), item(session, "Classic").id, pp[1]["Nonoy"]
    over = plan_batches(session, classic) + 1
    with pytest.raises(LookupError, match="not_planned"):
        tools.save_batch(
            session,
            plan,
            BatchInput(item_id=classic, batch_no=over, good=1),
            head,
            Actor.person(head),
        )


def test_only_the_commissary_drafts_and_the_leftover_is_the_day_befores(
    session: Session, pp: Ferinos
) -> None:
    with pytest.raises(LookupError, match="not_commissary"):
        tools.draft_plan(session, pp[0], PP_TOMORROW)
    classic = item(session, "Classic").id
    old = recipe(session, classic)
    keeps = RecipeInput(
        item_id=classic,
        batch_yield=old.batch_yield,
        oven_minutes=old.oven_minutes,
        lines=[RecipeLine.model_validate(x) for x in old.lines],
        keeps_overnight=True,
    )
    assert outcome(run(session, pp[1]["Rosa"], "set_recipe", keeps)) == "ok"
    for day, quantity in ((PP_TODAY - ONE_DAY, 7), (PP_TODAY, 5)):
        row = StockEvent(
            branch_id=pp[0].id,
            kind="leftover",
            item_id=classic,
            quantity=quantity,
            unit="pcs",
            at=at(day, 21),
            reported_by=pp[1]["Marites"].id,
            business_date=day,
        )
        store.insert(session, row, Actor.system(pp[0].id))
    left = tools.kiosk_data(session, comm(session), pp[0], PP_TOMORROW).leftovers
    assert left == {classic: 5}
    assert tools.kiosk_data(session, comm(session), pp[0], PP_TODAY + 2 * ONE_DAY).leftovers == {}


def deny(monkeypatch: pytest.MonkeyPatch, role: str, resource: Resource, action: str) -> None:
    """Rbac.require raises for that role, resource and action; every other check is real."""
    real = Rbac.require

    def require(self: Rbac, actor: Actor, res: Resource, act: str, **kw: Any) -> None:
        if (actor.principal.id, res.obj, act) == (role, resource.obj, action):
            raise PermissionDenied(role, f"{res.obj}:{act}")
        real(self, actor, res, act, **kw)

    monkeypatch.setattr(Rbac, "require", require)


def test_an_admin_confirms_a_delivery_from_a_kiosk(
    session: Session, pp: Ferinos, pp_pin: Pin
) -> None:
    call = caller(session, pp)
    packed(session, pp[1], pp_pin)
    pp[1]["Lea"] = people.add_person(
        session, Actor.system(pp[0].id), branch_id=stall(session).id, name="Lea", roles=["admin"]
    )
    assert call("Lea", "confirm_delivery", DeliveredInput(kiosk_id=pp[0].id)) == "ok"
    row = session.exec(
        select(Dispatch)
        .where(Dispatch.branch_id == pp[0].id)
        .where(Dispatch.business_date == PP_TOMORROW)
    ).one()
    assert (row.status, row.delivered_by) == ("delivered", pp[1]["Lea"].id)


def test_the_last_batch_reads_no_dispatch_before_the_agents_check(
    session: Session, pp: Ferinos, pp_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    call = caller(session, pp)
    draft(session)
    classic = item(session, "Classic").id
    for line in plan_row(session).lines:  # one batch left in the plan: Classic batch 1
        n = 1 if line["item_id"] == classic else 0
        args = ChangePlanInput(item_id=line["item_id"], batches=n, production_date=PP_TOMORROW)
        assert call("Nonoy", "change_plan", args) == "ok"
    pp_pin(at(PP_TOMORROW, 4, 0))
    deny(monkeypatch, MANIFEST.roles.agent_role, tools.DISPATCHES, "write_all")
    reads: list[str] = []
    real_exec = session.exec

    def spy(statement: Any, *a: Any, **kw: Any) -> Any:
        if Dispatch.__tablename__ in str(statement):
            reads.append(str(statement))
        return real_exec(statement, *a, **kw)

    monkeypatch.setattr(session, "exec", spy)
    assert call("Nonoy", "record_batch", BatchInput(item_id=classic, batch_no=1, good=48)) == (
        "denied"
    )
    assert reads == []
    monkeypatch.undo()
    assert session.exec(select(Dispatch).where(Dispatch.business_date == PP_TOMORROW)).all() == []


def test_a_kiosk_supervisors_recipe_is_refused_before_the_item_is_read(
    session: Session, pp: Ferinos
) -> None:
    """The guard already refuses Marites the tool; the precheck itself also puts the rights
    before the item: an unknown item is PermissionDenied for her, `item` for the owner."""
    args = RecipeInput(
        item_id="no-such-item",
        batch_yield=50,
        oven_minutes=45,
        lines=[RecipeLine(ingredient_id=ing(session, "Eggs"), quantity_milli=1000)],
    )
    with pytest.raises(PermissionDenied):
        tools.check_recipe(deps_for(session, pp[1]["Marites"]), args, "r")
    with pytest.raises(LookupError, match="item"):
        tools.check_recipe(deps_for(session, pp[1]["Rosa"]), args, "r")


def test_plan_for_refuses_without_the_agents_plans_read(
    session: Session, pp: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert tools.plan_for(session, comm(session).id, PP_TODAY - ONE_DAY) is not None
    deny(monkeypatch, MANIFEST.roles.agent_role, tools.PLANS, "read")
    with pytest.raises(PermissionDenied):
        tools.plan_for(session, comm(session).id, PP_TODAY - ONE_DAY)
