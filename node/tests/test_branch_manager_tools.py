"""The branch manager's data: dated prices per branch, the tips and strategies seed."""

import datetime as dt

from sqlmodel import Session, select

from mia.agents.sales_supervisor import tools as sales_tools
from mia.agents.sales_supervisor.tools import CountIn, RecordCountsInput
from mia.core.models import Actor, Branch, Event, Person
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
        items.price_on(session, special, kiosk.id, TODAY - ONE_DAY)
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
    assert [e.after["effective_on"] for e in changed if e.after] == [TODAY.isoformat()]
    assert session.exec(select(RetailItemPrice)).all()  # nothing removed


def test_set_short_codes_logs_the_change(session: Session, bm: Ferinos) -> None:
    kiosk, _ = bm
    classic = items.set_short_codes(
        session, item(session, "Classic"), ["cl", "bib"], Actor.system(kiosk.id), "t1"
    )
    assert classic.short_codes == ["cl", "bib"]
    event = session.exec(select(Event).where(Event.tool_call_id == "t1")).one()
    assert event.after and event.after["short_codes"] == ["cl", "bib"]
