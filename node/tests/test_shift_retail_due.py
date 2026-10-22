"""The shift supervisor's retail due work (D39, scenarios 3, 8, 9): the weekly roster, the daily
plan only on a change, the late check-in, closed days and undecided swaps, at fixed Manila clocks
in the seed's languages (Filipino). Negative tests first."""

import datetime as dt
from typing import Any

import pytest
from sqlmodel import Session, col, select

from mia.agents.sales_supervisor import MANIFEST as sales_manifest
from mia.agents.sales_supervisor import due as sales_due
from mia.agents.shift_supervisor import MANIFEST, alerts, replies, rules, tools, turn
from mia.agents.shift_supervisor.tools import CheckInInput, CheckOutInput, CloseDayInput
from mia.chat.blocks import TextBlock
from mia.core import orgconfig, scheduling, store
from mia.core.models import Actor, Event, Message, Person, Thread, Visit
from mia.i18n import t
from mia.templates.retail.models import RetailClosure
from tests.conftest import RS_TODAY, Pin
from tests.test_data_standard_1_7 import (
    MNL,
    MONDAY,
    NOV_1,
    SATURDAY,
    TUESDAY,
    Ferinos,
    at,
    names_on,
    stall,
    visit_of,
)
from tests.test_shift_retail_tools import agree_swap, deps_for


def _tick(session: Session, rs_pin: Pin, moment: dt.datetime) -> int:
    return turn.SPEC.run_due(session, rs_pin(moment))


def sent(session: Session, person: Person, agent_id: str) -> list[Message]:
    threads = select(Thread.id).where(Thread.person_id == person.id)
    stmt = select(Message).where(col(Message.thread_id).in_(threads))
    rows = session.exec(stmt.where(Message.role == "notification")).all()
    return [m for m in rows if m.agent_id == agent_id]


def notifications(session: Session, person: Person) -> list[Message]:
    return sent(session, person, MANIFEST.id)


def texts(session: Session, person: Person) -> list[str]:
    return [m.text for m in notifications(session, person)]


@pytest.fixture
def urgency(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Each alert's text to its urgent flag (alerts.notify spied, the real one still runs)."""
    seen: dict[str, bool] = {}
    real = alerts.notify

    def spy(session: Session, person: Person, *args: Any, **kwargs: Any) -> Message:
        text = "\n".join(b.text for b in args[0] if isinstance(b, TextBlock))
        seen[text] = bool(kwargs.get("urgent"))
        return real(session, person, *args, **kwargs)

    monkeypatch.setattr(alerts, "notify", spy)
    return seen


# ---- negative tests ------------------------------------------------------------------------


def test_the_weekly_roster_waits_for_the_retail_template(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleaning = orgconfig.load().model_copy(update={"template": "cleaning"})
    monkeypatch.setattr(orgconfig, "load", lambda org_name=None: cleaning)
    _tick(session, rs_pin, at(NOV_1, 17, 5))
    assert session.exec(select(Event).where(Event.action == alerts.ROSTER)).all() == []
    assert t("shift.roster.week_intro", "fil", count=6) not in texts(session, rs[1]["Ana"])


def test_the_shift_supervisor_sends_no_closing_reminders(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    ana, liza = rs[1]["Ana"], rs[1]["Liza"]
    for who, hour, tool, args in (
        (ana, 9, tools.check_in, CheckInInput()),
        (liza, 13, tools.check_in, CheckInInput()),
        (ana, 17, tools.check_out, CheckOutInput()),
        (liza, 21, tools.check_out, CheckOutInput()),
    ):
        rs_pin(at(RS_TODAY, hour))
        assert tool(deps_for(session, who), args, "c").status == "ok"  # type: ignore[operator]
        session.commit()
    _tick(session, rs_pin, at(RS_TODAY, 21, 35))  # counts, stock and cash stay with their agents
    assert (texts(session, ana), texts(session, liza)) == ([], [])


# ---- the due work ------------------------------------------------------------------------


def test_a_late_check_in_tells_head_staff(
    session: Session, rs: Ferinos, rs_pin: Pin, urgency: dict[str, bool]
) -> None:
    marites = rs[1]["Marites"]
    key = replies.word_key("alert.missed_check_in_supervisor")
    assert key == "retail.alert.missed_check_in_supervisor"
    line = t(key, "fil", name="Liza", location="Mall kiosk", time="13:00")
    _tick(session, rs_pin, at(RS_TODAY, 13, 10))
    assert line not in texts(session, marites)
    _tick(session, rs_pin, at(RS_TODAY, 13, 16))
    _tick(session, rs_pin, at(RS_TODAY, 13, 40))
    assert texts(session, marites).count(line) == 1
    assert urgency[line] is True


def test_a_late_notice_holds_the_missed_check_in_alert(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    """Liza sent a late notice at 12:50: nothing more at 13:15; Ana, silent, still gets it."""
    ana, liza, marites = (rs[1][n] for n in ("Ana", "Liza", "Marites"))
    rs_pin(at(RS_TODAY, 12, 50))
    notice = tools.RecordAbsenceInput(date=RS_TODAY, reason="late", arrive_at=dt.time(1, 30))
    out = tools.record_absence(deps_for(session, liza), notice, "c")
    assert isinstance(out, tools.RecordAbsenceOutput) and out.arrive_at == "13:30"
    session.commit()
    _tick(session, rs_pin, at(RS_TODAY, 13, 16))
    key = replies.word_key("alert.missed_check_in_supervisor")
    liza_missed = t(key, "fil", name=liza.name, location="Mall kiosk", time="13:00")
    ana_missed = t(key, "fil", name=ana.name, location="Mall kiosk", time="09:00")
    assert liza_missed not in texts(session, marites) and ana_missed in texts(session, marites)
    assert texts(session, liza) == []  # no "are you at the kiosk?" either


def test_a_missed_check_out_tells_head_staff_in_kiosk_words(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    ana, marites = rs[1]["Ana"], rs[1]["Marites"]
    assert tools.check_in(deps_for(session, ana), CheckInInput(), "c").status == "ok"
    session.commit()
    key = replies.word_key("alert.missed_check_out_supervisor")
    assert key == "retail.alert.missed_check_out_supervisor"
    line = t(key, "fil", name=ana.name, location="Mall kiosk", time="17:00")
    _tick(session, rs_pin, at(RS_TODAY, 17, 35))
    assert texts(session, marites).count(line) == 1


def test_the_weekly_roster_goes_out_once(
    session: Session, rs: Ferinos, rs_pin: Pin, urgency: dict[str, bool]
) -> None:
    ana, marites = rs[1]["Ana"], rs[1]["Marites"]
    intro = t("shift.roster.week_intro", "fil", count=6)
    _tick(session, rs_pin, at(NOV_1, 16, 55))
    assert intro not in texts(session, ana)
    _tick(session, rs_pin, at(NOV_1, 17, 5))
    _tick(session, rs_pin, at(NOV_1, 17, 40))
    before = texts(session, ana)
    branch = t("shift.roster.branch_intro", "fil", branch="Mall kiosk", count=12)
    assert before.count(intro) == 1 and texts(session, marites).count(branch) == 1
    card = next(m for m in notifications(session, ana) if m.text == intro).blocks[1]
    assert [f["label"] for f in card["fields"]] == ["Ana"]  # her own card, nobody else's
    assert (urgency[intro], urgency[branch]) == (False, False)
    _tick(session, rs_pin, at(MONDAY, 17, 5))
    assert texts(session, ana) == before  # tomorrow unchanged: no daily plan


def test_a_closed_day_cancels_its_shifts(session: Session, rs: Ferinos, rs_pin: Pin) -> None:
    marites = rs[1]["Marites"]
    args = CloseDayInput(date=NOV_1, reason="Undas")
    out = tools.close_day(deps_for(session, marites), args, "c")
    session.commit()
    day = session.exec(
        select(Visit).where(Visit.branch_id == rs[0].id).where(Visit.date == NOV_1)
    ).all()
    assert (out.cancelled, {v.status for v in day}) == (2, {"cancelled"})
    told = t(
        "shift.closed.told",
        "fil",
        location="Mall kiosk",
        date=rules.fmt_date(NOV_1.isoformat(), "fil"),
    )
    assert told in texts(session, rs[1]["Ana"]) and told in texts(session, rs[1]["Liza"])
    sales_due.run_due(session, rs_pin(at(NOV_1, 20, 40)))
    on_the_day = [
        m
        for m in sent(session, rs[1]["Ana"], sales_manifest.id)
        if m.created_at.astimezone(MNL).date() == NOV_1
    ]
    assert on_the_day == []


def test_a_generated_shift_on_a_closed_day_is_cancelled(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    where, pao, nov_30 = stall(session), rs[1]["Pao"], dt.date(2026, 11, 30)  # a Monday, Pao's
    closure = RetailClosure(branch_id=where.id, date=nov_30, reason="Bonifacio Day", set_by=pao.id)
    store.insert(session, closure, Actor.system(where.id), action="retail.closure_set")
    session.commit()
    scheduling.reset_generation()
    now = rs_pin(at(TUESDAY, 10))
    assert scheduling.generate_due(session, now) > 0
    session.commit()
    stmt = select(Visit).where(Visit.branch_id == where.id).where(Visit.date == nov_30)
    assert {v.status for v in session.exec(stmt).all()} == {"planned"}
    before = texts(session, pao)
    _tick(session, rs_pin, at(TUESDAY, 10))
    assert {v.status for v in session.exec(stmt).all()} == {"cancelled"}
    assert texts(session, pao) == before  # never announced, nobody told


def test_the_daily_plan_goes_only_when_tomorrow_changed(
    session: Session, rs: Ferinos, rs_pin: Pin, urgency: dict[str, bool]
) -> None:
    ana, liza, marites = rs[1]["Ana"], rs[1]["Liza"], rs[1]["Marites"]
    _tick(session, rs_pin, at(NOV_1, 17, 5))
    scheduling.unassign(session, Actor.person(marites), visit_of(session, liza, TUESDAY), liza)
    session.commit()
    before = texts(session, ana)
    _tick(session, rs_pin, at(MONDAY, 17, 5))
    _tick(session, rs_pin, at(MONDAY, 17, 30))
    assert texts(session, liza).count(t("shift.plan.off", "fil")) == 1
    assert texts(session, ana) == before
    assert urgency[t("shift.plan.off", "fil")] is False


def test_a_day_closed_after_the_roster_gets_no_plan(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    liza, marites = rs[1]["Liza"], rs[1]["Marites"]
    _tick(session, rs_pin, at(NOV_1, 17, 5))
    rs_pin(at(MONDAY, 10))
    out = tools.close_day(deps_for(session, marites, MONDAY), CloseDayInput(date=TUESDAY), "c")
    session.commit()
    assert out.status == "ok"
    _tick(session, rs_pin, at(MONDAY, 17, 5))
    told = texts(session, liza)
    assert t("shift.plan.off", "fil") not in told
    assert (
        told.count(
            t(
                "shift.closed.told",
                "fil",
                location="Mall kiosk",
                date=rules.fmt_date(TUESDAY.isoformat(), "fil"),
            )
        )
        == 1
    )


def test_an_undecided_swap_expires_at_the_shift_start(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    approval = agree_swap(session, rs)
    session.commit()
    mine = visit_of(session, rs[1]["Ana"], SATURDAY)
    _tick(session, rs_pin, at(SATURDAY, 8, 55))
    session.refresh(approval)
    assert approval.status == "pending"
    _tick(session, rs_pin, at(SATURDAY, 9, 5))
    session.refresh(approval)
    session.refresh(mine)
    assert (approval.status, names_on(session, mine)) == ("expired", ["Ana"])
    assert t("shift.swap.expired", "fil", name="Liza") in texts(session, rs[1]["Ana"])
    assert t("shift.swap.expired", "fil", name="Ana") in texts(session, rs[1]["Liza"])
