"""Inventory manager due work on the tick: the closing stock summary to head staff and owners,
the bake plan before opening, each once per branch and business date."""

import datetime as dt
from collections.abc import Callable, Iterator

import pytest
from sqlmodel import Session, select

from mia.agents.inventory_manager import MANIFEST, due, tools
from mia.agents.inventory_manager.models import StockEvent
from mia.agents.inventory_manager.tools import EventIn, RecordEventsInput
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
from mia.core.orgconfig import ChannelConfig, OrgSettings, QuietHours
from mia.i18n import t
from mia.templates.retail.models import RetailBranchHours
from tests.test_inventory_tools import deps_for, ingredient, item, stall

Ferinos = tuple[Branch, dict[str, Person]]
At = Callable[[int, int], dt.datetime]
DAY = dt.timedelta(days=1)


def _notes(session: Session, person: Person) -> list[Message]:
    stmt = select(Message).where(Message.role == "notification")
    rows = [m for m in session.exec(stmt) if m.agent_id == MANIFEST.id]
    return [
        m for m in rows if (th := session.get(Thread, m.thread_id)) and th.person_id == person.id
    ]


def _markers(session: Session, action: str) -> list[Event]:
    return list(session.exec(select(Event).where(Event.action == action)))


def _close_day(session: Session, people: dict[str, Person]) -> None:
    """Ana's day at the kiosk: a sell-out, a leftover, a waste with a reason, a low ingredient."""
    args = RecordEventsInput(
        events=[
            EventIn(kind="sold_out", item_id=item(session, "Special"), at="14:00"),
            EventIn(kind="leftover", item_id=item(session, "Ube"), quantity=3),
            EventIn(kind="waste", item_id=item(session, "Classic"), quantity=8, reason="too_dry"),
            EventIn(kind="low", ingredient_id=ingredient(session, "Rice flour")),
        ]
    )
    tools.record_events(deps_for(session, people["Ana"]), args, "c1")
    session.commit()


def _early_sell_outs(session: Session, branch: Branch, person: Person, day: dt.date) -> None:
    """Special sold out at 10:00 on the two same weekdays before `day`: the plan says more."""
    special = item(session, "Special")
    for weeks in (1, 2):
        d = day - dt.timedelta(weeks=weeks)
        at = dt.datetime.combine(d, dt.time(10), dt.timezone(dt.timedelta(hours=8)))
        row = StockEvent(
            branch_id=branch.id,
            kind="sold_out",
            item_id=special,
            at=at,
            reported_by=person.id,
            business_date=d,
        )
        store.insert(session, row, Actor.system(branch.id), action="stock.sold_out")
    session.commit()


# ---- the closing summary --------------------------------------------------------------------


def test_closing_summary_goes_to_head_staff_once(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    kiosk, people = ferinos
    manila_at(15, 0)
    _close_day(session, people)
    assert due.run_due(session, manila_at(21, 44)) == 2  # the stall's (closed 19:00): Jun, Rosa
    assert _notes(session, people["Marites"]) == []  # the kiosk closes 21:00
    assert due.run_due(session, manila_at(21, 45)) == 2  # Marites and Rosa
    (note,) = _notes(session, people["Marites"])
    lang = people["Marites"].language
    assert note.text.startswith(t("stock.summary", lang, branch="Mall kiosk"))
    for said in (
        t("stock.sold_out", lang, item="Special", time="14:00"),
        t("stock.leftover", lang, item="Ube", quantity="3"),
        t(
            "stock.waste",
            lang,
            item="Classic",
            quantity="8",
            reason=t("stock.reason.too_dry", lang),
        ),
    ):
        assert said in note.text
    low = t("stock.summary.line", lang, ingredients="")[:-1]
    assert any(line.startswith(low) and "Rice flour" in line for line in note.text.splitlines())
    rosa = [n.text for n in _notes(session, people["Rosa"])]
    assert note.text in rosa and len(rosa) == 2  # one summary per branch
    assert any(text.startswith(t("stock.summary", lang, branch="Street stall")) for text in rosa)
    (empty,) = due._summary_blocks(kiosk, [], [], "en")
    assert empty.text == t("stock.summary.empty", "en", branch="Mall kiosk")
    assert _notes(session, people["Ana"]) == []
    assert due.run_due(session, manila_at(22, 30)) == 0
    marker = next(m for m in _markers(session, due.SUMMARY) if m.entity_id == kiosk.id)
    assert marker.after is not None and len(marker.after["message_ids"]) == 2


def test_summary_crosses_midnight_under_the_closing_day(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    kiosk, people = ferinos
    for row in session.exec(
        select(RetailBranchHours).where(RetailBranchHours.branch_id == kiosk.id)
    ):
        store.update(session, row, {"closes": "23:00"}, Actor.system(kiosk.id))
    session.commit()
    today = manila_at(15, 0).date()
    _close_day(session, people)
    due.run_due(session, manila_at(23, 30))
    assert _notes(session, people["Marites"]) == []
    after_midnight = manila_at(0, 10) + DAY
    due.run_due(session, after_midnight)
    (note,) = _notes(session, people["Marites"])
    assert "Special" in note.text
    kiosk_dates = [
        m.after["date"] for m in _markers(session, due.SUMMARY) if m.entity_id == kiosk.id
    ]
    assert kiosk_dates == [today.isoformat()]
    assert due.run_due(session, after_midnight + dt.timedelta(minutes=30)) == 0


# ---- the bake plan --------------------------------------------------------------------------


def test_bake_plan_message_before_opening(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    kiosk, people = ferinos
    today = manila_at(15, 0).date()
    _early_sell_outs(session, kiosk, people["Ana"], today)
    due.run_due(session, manila_at(7, 59))
    assert _notes(session, people["Ana"]) == []  # the kiosk opens 09:00
    due.run_due(session, manila_at(8, 0))
    for name in ("Ana", "Liza", "Marites"):
        lang = people[name].language
        plans = [
            n for n in _notes(session, people[name]) if t("stock.plan.heuristic", lang) in n.text
        ]
        assert len(plans) == 1, name
        assert t("stock.plan.more", lang, item="Special") in plans[0].text
        assert t("stock.plan.same", lang, item="Ube") in plans[0].text
    heuristic = t("stock.plan.heuristic", people["Rosa"].language)
    assert all(heuristic not in n.text for n in _notes(session, people["Rosa"]))  # summary only
    (marker,) = _markers(session, due.PLAN)
    assert marker.after is not None and marker.after["date"] == today.isoformat()
    due.run_due(session, manila_at(8, 30))
    assert len(_markers(session, due.PLAN)) == 1


def test_no_bake_plan_when_every_item_stays_the_same(
    session: Session, ferinos: Ferinos, manila_at: At
) -> None:
    _, people = ferinos
    due.run_due(session, manila_at(8, 0))
    assert _notes(session, people["Ana"]) == [] and _markers(session, due.PLAN) == []


# ---- the organisation gate and quiet hours --------------------------------------------------


def test_nothing_runs_for_an_organisation_without_the_inventory_manager(
    session: Session, ferinos: Ferinos, manila_at: At, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, people = ferinos
    _close_day(session, people)
    org = OrgSettings(agents=["sales_supervisor"])
    with monkeypatch.context() as m:
        m.setattr(orgconfig, "load", lambda org_name=None: org)
        assert due.run_due(session, manila_at(21, 45)) == 0
    assert _notes(session, people["Marites"]) == []


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


def _link(session: Session, person: Person, address: str) -> None:
    identity = ChannelIdentity(
        branch_id=person.branch_id, person_id=person.id, channel="sim", address=address
    )
    store.insert(session, identity, Actor.person(person), action="channel.linked")
    session.commit()


def _queued(session: Session, person: Person) -> list[ChannelOutbox]:
    stmt = select(ChannelOutbox).where(ChannelOutbox.person_id == person.id)
    return [r for r in session.exec(stmt) if r.status == "queued"]


def test_summary_goes_at_once_in_quiet_hours_and_the_plan_waits(
    session: Session, ferinos: Ferinos, manila_at: At, quiet_sim: None
) -> None:
    _, people = ferinos
    the_stall = stall(session)
    _link(session, people["Jun"], "639170000001")
    _link(session, people["Pao"], "639170000002")
    at = manila_at(5, 30)  # the stall opens 06:00: yesterday's summary and today's plan are due
    _early_sell_outs(session, the_stall, people["Pao"], at.date())
    assert due.run_due(session, at) > 0
    jun = sorted(r.send_after is None for r in _queued(session, people["Jun"]))
    assert jun == [False, True]  # the summary is urgent (the end of the shift), the plan waits
    (plan,) = _queued(session, people["Pao"])
    assert plan.send_after == at.replace(hour=6, minute=0).astimezone(dt.UTC)
