"""The production planner's data on the Ferino's seed (pp, PP_TODAY a Tuesday): the commissary
is a branch without retail hours with its head and driver, who is offered the planner, the
rights on the kiosks' counts, stock and orders (the agent alone reads across branches), and the
kiosk agents' due work skipping the commissary (negative tests first; the clock pinned through
pp_pin, never the wall clock)."""

import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.agents.bookkeeper import due as bk_due
from mia.agents.branch_manager import due as bm_due
from mia.agents.customer_service import due as cs_due
from mia.agents.inventory_manager import due as inventory_due
from mia.agents.production_planner import MANIFEST, tools
from mia.agents.production_planner.models import Recipe
from mia.agents.sales_supervisor import due as sales_due
from mia.chat.access import agents_for
from mia.core import orgconfig
from mia.core.models import Actor, Branch, Message, Person, Thread
from mia.core.rbac import get_rbac
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailIngredient, RetailItem
from tests.conftest import PP_TODAY, Pin

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")
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
