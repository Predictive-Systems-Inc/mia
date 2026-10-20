"""The branch manager's data: dated prices per branch, the tips and strategies seed."""

import datetime as dt
from collections import Counter

from sqlmodel import Session, select

from mia.agents.branch_manager.models import Strategy, Tip
from mia.agents.sales_supervisor import tools as sales_tools
from mia.agents.sales_supervisor.tools import CountIn, RecordCountsInput
from mia.core.models import Actor, Branch, Event, Person
from mia.core.rbac import get_rbac
from mia.templates.retail import items
from mia.templates.retail.models import RetailItem, RetailItemPrice
from tests.conftest import BM_TODAY as TODAY
from tests.conftest import Shop
from tests.test_sales_tools import deps_for as sales_deps
from tests.test_sales_tools import stall

Ferinos = tuple[Branch, dict[str, Person]]
ONE_DAY = dt.timedelta(days=1)


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


def test_seed_has_tips_and_quotes_with_sources(session: Session, bm: Ferinos) -> None:
    rows = session.exec(select(Tip)).all()
    assert all(
        Counter(r.kind for r in rows if r.language == lang) == {"tip": 20, "quote": 20}
        for lang in ("fil", "en")
    )
    assert all(r.source.strip() for r in rows)
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
