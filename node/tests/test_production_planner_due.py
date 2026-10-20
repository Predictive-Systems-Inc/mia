"""The production planner's due work on the tick at fixed clocks (pp, PP_TODAY a Tuesday): the
draft plan at plan_at, the dispatch list at dispatch_at, the receipt match an hour after the
kiosk opens and the closing yield, each once and nothing with nothing to say."""

import datetime as dt
from collections.abc import Iterator

import pytest
from sqlmodel import Session, col, select

from mia.agents.production_planner import MANIFEST, due, replies, tools
from mia.agents.production_planner.models import Dispatch, Plan
from mia.agents.production_planner.tools import ChangePlanInput, ConfirmPlanInput, DeliveredInput
from mia.agents.sales_supervisor import MANIFEST as SALES
from mia.agents.shift_supervisor import alerts
from mia.core import orgconfig, store
from mia.core.models import Actor, Branch, Message, Person, StockEvent, Thread
from mia.core.orgconfig import OrgSettings
from mia.i18n import t
from tests.conftest import PP_TODAY, PP_TOMORROW, Pin
from tests.test_production_planner_tools import (
    at,
    comm,
    draft,
    item,
    outcome,
    packed,
    plan_row,
    run,
)

Ferinos = tuple[Branch, dict[str, Person]]
EN = "en"
ONE_DAY = dt.timedelta(days=1)


def _tick(session: Session, pin: Pin, moment: dt.datetime) -> int:
    return due.run_due(session, pin(moment))


def notifications(session: Session, person: Person) -> list[Message]:
    """The planner's notifications to the person."""
    threads = select(Thread.id).where(Thread.person_id == person.id)
    stmt = select(Message).where(col(Message.thread_id).in_(threads))
    rows = session.exec(stmt.where(Message.role == "notification")).all()
    return [m for m in rows if m.agent_id == MANIFEST.id]


def texts(session: Session, person: Person) -> list[str]:
    return [m.text for m in notifications(session, person)]


def names(session: Session) -> dict[str, str]:
    return due.names(session, comm(session).organisation_id)


def confirmed(session: Session, people: dict[str, Person], pin: Pin) -> Plan:
    """Drafted at 14:05 on PP_TODAY, Classic set to 3 batches and confirmed by Nonoy (packed
    without the batches)."""
    pin(at(PP_TODAY, 14, 5))
    draft(session)
    head = people["Nonoy"]
    change = ChangePlanInput(item_id=item(session, "Classic").id, batches=3)
    assert outcome(run(session, head, "change_plan", change)) == "ok"
    assert outcome(run(session, head, "confirm_plan", ConfirmPlanInput())) == "ok"
    return plan_row(session)


def dispatches(session: Session) -> list[Dispatch]:
    stmt = select(Dispatch).where(Dispatch.business_date == PP_TOMORROW)
    return list(session.exec(stmt))


def delivered(session: Session, people: dict[str, Person], pin: Pin) -> Dispatch:
    """packed, then Berto's confirm_delivery for the Mall kiosk at 08:50 on PP_TOMORROW."""
    packed(session, people, pin)
    pin(at(PP_TOMORROW, 8, 50))
    mall = people["Marites"].branch_id
    args = DeliveredInput(kiosk_id=mall)
    assert outcome(run(session, people["Berto"], "confirm_delivery", args)) == "ok"
    (row,) = [d for d in dispatches(session) if d.branch_id == mall]
    assert row.status == "delivered"
    return row


def received(session: Session, kiosk_id: str, lines: dict[str, int], day: dt.date) -> None:
    """The kiosk's receipt at 09:30 as `received` stock events per item, written through
    store.insert as inventory_manager.receive_delivery will once it takes item lines."""
    for item_id, quantity in lines.items():
        row = StockEvent(
            branch_id=kiosk_id,
            kind="received",
            item_id=item_id,
            quantity=quantity,
            unit="pcs",
            at=at(day, 9, 30),
            reported_by=_someone(session, kiosk_id),
            business_date=day,
        )
        store.insert(session, row, Actor.system(kiosk_id))


def _someone(session: Session, branch_id: str) -> str:
    return session.exec(select(Person.id).where(Person.branch_id == branch_id)).first() or ""


def lines_of(dispatch: Dispatch) -> dict[str, int]:
    return {x["item_id"]: x["quantity"] for x in dispatch.lines}


@pytest.fixture
def without_planner(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    org = OrgSettings(agents=[SALES.id])
    with monkeypatch.context() as m:
        m.setattr(orgconfig, "load", lambda org_name=None: org)
        yield


def test_the_draft_plan_reaches_the_head_once(
    session: Session, pp_en: Ferinos, pp_pin: Pin
) -> None:
    _tick(session, pp_pin, at(PP_TODAY, 13, 55))
    assert notifications(session, pp_en[1]["Nonoy"]) == []
    _tick(session, pp_pin, at(PP_TODAY, 14, 5))
    _tick(session, pp_pin, at(PP_TODAY, 14, 40))
    (note,) = notifications(session, pp_en[1]["Nonoy"])
    plan = session.exec(select(Plan).where(Plan.production_date == PP_TOMORROW)).one()
    want = replies.plan_text(tools.plan_out(session, plan), names(session), EN)
    assert (note.text, plan.status) == (want, "draft")


def test_a_draft_after_midnight_is_for_that_mornings_production(
    session: Session, pp: Ferinos, pp_pin: Pin
) -> None:
    _tick(session, pp_pin, at(PP_TOMORROW, 1, 0))
    stmt = select(Plan).where(Plan.production_date == PP_TOMORROW)
    assert session.exec(stmt).one().status == "draft"
    _tick(session, pp_pin, at(PP_TOMORROW + ONE_DAY, 3, 10))
    later = select(Plan).where(Plan.production_date == PP_TOMORROW + ONE_DAY)
    assert session.exec(later).all() == []


def test_the_dispatch_list_splits_by_kiosk(session: Session, pp_en: Ferinos, pp_pin: Pin) -> None:
    plan = confirmed(session, pp_en[1], pp_pin)
    classic = item(session, "Classic").id
    _tick(session, pp_pin, at(PP_TOMORROW, 8, 25))
    assert dispatches(session) == []
    _tick(session, pp_pin, at(PP_TOMORROW, 8, 35))
    _tick(session, pp_pin, at(PP_TOMORROW, 8, 50))
    by = {d.branch_id: d for d in dispatches(session)}
    want = {
        k["branch_id"]: k["pieces"]
        for x in plan.lines
        if x["item_id"] == classic
        for k in x["kiosks"]
    }
    assert {b: lines_of(d)[classic] for b, d in by.items()} == want  # no batch: the planned split
    assert {d.status for d in by.values()} == {"packed"}
    text = replies.dispatch_text(tools.dispatch_out(by[pp_en[0].id]), names(session), EN)
    sent = [m for m in notifications(session, pp_en[1]["Berto"]) if m.text == text]
    assert len(sent) == 1


def test_a_short_receipt_is_flagged(session: Session, pp_en: Ferinos, pp_pin: Pin) -> None:
    mall = delivered(session, pp_en[1], pp_pin)
    classic = item(session, "Classic").id
    sent = lines_of(mall)[classic]
    received(session, mall.branch_id, {**lines_of(mall), classic: sent - 5}, PP_TOMORROW)
    _tick(session, pp_pin, at(PP_TOMORROW, 9, 55))
    assert session.get(Dispatch, mall.id).status == "delivered"
    _tick(session, pp_pin, at(PP_TOMORROW, 10, 5))
    line = t("pp.short.line", EN, kiosk="Mall kiosk", item="Classic", sent=sent, received=sent - 5)
    assert session.get(Dispatch, mall.id).status == "short"
    assert all(line in "\n".join(texts(session, pp_en[1][w])) for w in ("Nonoy", "Rosa"))


def test_a_full_receipt_is_quiet(session: Session, pp_en: Ferinos, pp_pin: Pin) -> None:
    mall = delivered(session, pp_en[1], pp_pin)
    received(session, mall.branch_id, lines_of(mall), PP_TOMORROW)
    before = len(notifications(session, pp_en[1]["Rosa"]))
    _tick(session, pp_pin, at(PP_TOMORROW, 10, 5))
    assert session.get(Dispatch, mall.id).status == "matched"
    later = notifications(session, pp_en[1]["Rosa"])[before:]
    assert not any("Mall kiosk" in m.text for m in later)


def test_the_closing_yield_reaches_the_head_once(
    session: Session, pp_en: Ferinos, pp_pin: Pin
) -> None:
    packed(session, pp_en[1], pp_pin)
    for hm in ((9, 55), (10, 5), (10, 40)):
        _tick(session, pp_pin, at(PP_TOMORROW, *hm))
    out = tools.day_yield(session, comm(session), PP_TOMORROW)
    assert [x.percent for x in out.items] == [100] * len(out.items) and out.items
    want = replies.yield_text(out, names(session), EN)
    assert texts(session, pp_en[1]["Nonoy"]).count(want) == 1


def test_no_batch_no_closing_yield(session: Session, pp_en: Ferinos, pp_pin: Pin) -> None:
    confirmed(session, pp_en[1], pp_pin)
    _tick(session, pp_pin, at(PP_TOMORROW, 10, 5))
    assert not alerts._marked(session, due.YIELD_SENT, comm(session).id, PP_TOMORROW)


def test_the_draft_plan_in_filipino(session: Session, pp: Ferinos, pp_pin: Pin) -> None:
    _tick(session, pp_pin, at(PP_TODAY, 14, 5))
    (note,) = notifications(session, pp[1]["Nonoy"])
    plan = session.exec(select(Plan)).all()[-1]
    assert note.text == replies.plan_text(tools.plan_out(session, plan), names(session), "fil")


def test_nothing_runs_when_the_org_does_not_use_the_planner(
    session: Session, pp_en: Ferinos, pp_pin: Pin, without_planner: None
) -> None:
    for hm in ((1, 0), (8, 35), (10, 5), (14, 5)):
        assert _tick(session, pp_pin, at(PP_TODAY, *hm)) == 0
    assert notifications(session, pp_en[1]["Nonoy"]) == []
    assert session.exec(select(Plan).where(Plan.production_date >= PP_TODAY)).all() == []


def test_the_tick_drafts_the_plan_through_the_agent_spec(
    session: Session, pp_en: Ferinos, pp_pin: Pin
) -> None:
    from mia.api import main as api_main

    pp_pin(at(PP_TODAY, 14, 5))
    session.commit()
    assert api_main.tick() >= 1  # every agent's due work, the planner's through SPEC.run_due
    session.expire_all()
    assert len(notifications(session, pp_en[1]["Nonoy"])) == 1
