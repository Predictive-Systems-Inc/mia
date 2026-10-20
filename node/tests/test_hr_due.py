"""The hr officer's due work on the tick at fixed clocks: payslips issued once per cutoff on
payday, head staff reminded to approve timesheets two days before the cutoff closes."""

import datetime as dt
import importlib
from collections.abc import Callable, Iterator
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, select

from mia.agents.hr_officer import MANIFEST, calc, due, ph, replies, tools
from mia.agents.shift_supervisor import timesheets
from mia.channels import registry
from mia.channels.simulator import SimAdapter
from mia.core import events, orgconfig, store
from mia.core.ids import new_id
from mia.core.models import (
    Actor,
    Branch,
    ChannelIdentity,
    ChannelOutbox,
    Contract,
    Event,
    Message,
    Payslip,
    Person,
    Thread,
    Timesheet,
)
from mia.core.money import format_money
from mia.core.orgconfig import ChannelConfig, OrgSettings, Payroll
from mia.i18n import t
from mia.settings import get_settings
from tests.conftest import CLOCK_USERS

Ferinos = tuple[Branch, dict[str, Person]]
Pin = Callable[[dt.datetime], dt.datetime]
MNL = ZoneInfo("Asia/Manila")
TODAY = dt.date(2026, 10, 19)  # the seed's day: approved timesheets 5 to 18 October
OCT_16 = dt.date(2026, 10, 16)  # the cutoff 16 to 31 October pays Thursday 5 November
PAYDAY = dt.datetime(2026, 11, 5, 9, 0, tzinfo=MNL)
REMIND = dt.datetime(2026, 10, 29, 9, 0, tzinfo=MNL)  # two days before 31 October


@pytest.fixture
def pin(monkeypatch: pytest.MonkeyPatch) -> Pin:
    """Pin the clock on CLOCK_USERS to a moment; returns it."""

    def set_at(at: dt.datetime) -> dt.datetime:
        for name in CLOCK_USERS:
            monkeypatch.setattr(importlib.import_module(name), "utcnow", lambda: at)
        return at

    return set_at


@pytest.fixture
def hr(monkeypatch: pytest.MonkeyPatch, session: Session, pin: Pin) -> Iterator[Ferinos]:
    """The Ferino's seed on TODAY at 10:00 Manila."""
    from mia.templates.retail import seed as retail_seed

    pin(dt.datetime.combine(TODAY, dt.time(10), MNL))
    with monkeypatch.context() as m:
        m.setenv("MIA_ORG", "ferinos")
        get_settings.cache_clear()
        orgconfig.load.cache_clear()
        kiosk = retail_seed.seed(session, today=TODAY)
        session.commit()
        yield kiosk, {p.name.split()[0]: p for p in session.exec(select(Person)).all()}
    get_settings.cache_clear()
    orgconfig.load.cache_clear()


def _tick(session: Session, pin: Pin, at: dt.datetime) -> int:
    return due.run_due(session, pin(at))


def _slips(session: Session, start: dt.date = OCT_16) -> dict[str, Payslip]:
    rows = session.exec(select(Payslip).where(Payslip.cutoff_start == start))
    return {r.person_id: r for r in rows}


def _notes(session: Session, person: Person) -> list[Message]:
    rows = session.exec(select(Message).where(Message.role == "notification"))
    return [
        m
        for m in rows
        if m.agent_id == MANIFEST.id
        and (th := session.get(Thread, m.thread_id))
        and th.person_id == person.id
    ]


def _markers(session: Session, action: str) -> list[Event]:
    return list(session.exec(select(Event).where(Event.action == action)))


def _to_draft(session: Session, people: dict[str, Person], day: dt.date) -> Timesheet:
    """Ana's approved timesheet of the day corrected by the owner (back to draft)."""
    stmt = select(Timesheet).where(Timesheet.person_id == people["Ana"].id)
    row = session.exec(stmt.where(Timesheet.date == day)).one()
    start = row.start - dt.timedelta(hours=2)
    out = timesheets.correct(session, Actor.person(people["Rosa"]), row, start, row.end, "early")
    session.commit()
    return out


# ---- what is due (pure) ---------------------------------------------------------------------


def test_payslips_are_due_from_nine_on_payday_until_the_next_payday() -> None:
    payroll, oct_1 = Payroll(pay_lag_days=5), (dt.date(2026, 10, 1), dt.date(2026, 10, 15))
    second = (OCT_16, dt.date(2026, 10, 31))

    def at(moment: dt.datetime) -> tuple[dt.date, dt.date]:
        return due.payslips_due(moment, "Asia/Manila", payroll, {})

    assert at(PAYDAY) == second and at(PAYDAY.replace(hour=8, minute=59)) == oct_1
    assert at(PAYDAY + dt.timedelta(days=14)) == second  # 19 November, still before the next
    assert due.paid_cutoffs(PAYDAY, "Asia/Manila", payroll, {}) == (
        (second, PAYDAY.date()),
        (oct_1, dt.date(2026, 10, 20)),
    )


def test_a_payday_on_a_sunday_pays_the_day_before() -> None:
    """1 to 15 December pays Sunday the 20th: moved back to Saturday the 19th, and to Friday
    the 18th when that Saturday is a holiday (calendar.payday, Q60)."""
    payroll, cutoff = Payroll(pay_lag_days=5), (dt.date(2026, 12, 1), dt.date(2026, 12, 15))
    november = (dt.date(2026, 11, 16), dt.date(2026, 11, 30))

    def at(day: int, holidays: dict[dt.date, str]) -> tuple[dt.date, dt.date]:
        moment = dt.datetime(2026, 12, day, 9, 0, tzinfo=MNL)
        return due.payslips_due(moment, "Asia/Manila", payroll, holidays)

    saturday_off = {dt.date(2026, 12, 19): "special"}
    assert at(17, saturday_off) == november and at(18, saturday_off) == cutoff
    assert at(18, {}) == november and at(19, {}) == cutoff


def test_the_reminder_is_due_two_days_before_the_cutoff_ends() -> None:
    assert due.approval_reminder(REMIND, "Asia/Manila") == (OCT_16, dt.date(2026, 10, 31))
    assert due.approval_reminder(REMIND.replace(hour=8), "Asia/Manila") is None
    assert due.approval_reminder(REMIND - dt.timedelta(days=1), "Asia/Manila") is None


# ---- payslips -------------------------------------------------------------------------------


def test_payslips_are_issued_once_per_cutoff(session: Session, hr: Ferinos, pin: Pin) -> None:
    _, people = hr
    assert _tick(session, pin, PAYDAY.replace(hour=8)) == 0 and _slips(session) == {}
    assert _tick(session, pin, PAYDAY) == 3  # the three clerks; the supervisors logged no time
    slips = _slips(session)
    assert set(slips) == {people[n].id for n in ("Ana", "Liza", "Pao")}
    ana = slips[people["Ana"].id]
    assert (ana.cutoff_end, ana.pay_date, ana.issued_at) == (
        dt.date(2026, 10, 31),
        PAYDAY.date(),
        PAYDAY,
    )
    assert ana.net == ana.gross - sum(d["amount"] for d in ana.deductions) and ana.gross > 0
    (note,) = _notes(session, people["Ana"])
    assert ana.message_id == note.id
    lang = people["Ana"].language
    assert note.text == "\n".join(b.text for b in replies.payslip_blocks(ana, lang))
    issued = [e for e in _markers(session, "hr.payslip_issued") if e.entity_id == ana.id]
    assert issued and issued[0].after and issued[0].after["gross"] == events.REDACTED
    (mall, stall) = sorted(_markers(session, due.ISSUED), key=lambda e: e.entity_id)
    assert {len(mall.after["message_ids"]), len(stall.after["message_ids"])} == {1, 2}  # type: ignore[index]
    assert _tick(session, pin, PAYDAY.replace(hour=15)) == 0
    assert len(_slips(session)) == 3 and len(_notes(session, people["Ana"])) == 1


def test_a_first_tick_late_on_payday_issues_them(session: Session, hr: Ferinos, pin: Pin) -> None:
    assert _tick(session, pin, PAYDAY.replace(hour=10, minute=37)) == 3
    assert len(_slips(session)) == 3


def test_a_node_down_on_payday_issues_on_its_first_tick_after(
    session: Session, hr: Ferinos, pin: Pin
) -> None:
    assert _tick(session, pin, (PAYDAY + dt.timedelta(days=1)).replace(hour=10, minute=37)) == 3
    assert len(_slips(session)) == 3 and len(_markers(session, due.ISSUED)) == 2


def test_a_cutoff_missed_past_the_next_payday_is_reported_not_issued(
    session: Session, hr: Ferinos, pin: Pin
) -> None:
    """Down from before 5 November to after 20 November (the next payday): 16 to 31 October
    is reported to head staff, never issued."""
    _, people = hr
    late = dt.datetime(2026, 11, 21, 10, 37, tzinfo=MNL)
    assert _tick(session, pin, late) == 2  # one note to each branch's supervisor
    assert _slips(session) == {}
    for name, count in (("Marites", 2), ("Jun", 1)):
        (note,) = _notes(session, people[name])
        lang = people[name].language
        assert note.text == t(due.MISSED, lang, count=count, start="2026-10-16", end="2026-10-31")
    assert len(_markers(session, due.MISSED)) == 2
    assert _tick(session, pin, late + dt.timedelta(hours=1)) == 0


def test_a_branch_pays_from_its_own_contract_only(session: Session, hr: Ferinos, pin: Pin) -> None:
    """Pao (the stall) has a newer contract at the mall: the stall's payslip uses the stall's."""
    branch, people = hr
    pao = people["Pao"]
    stall = session.get(Branch, pao.branch_id)
    assert stall is not None and stall.id != branch.id
    own = tools._contract(session, pao.id, TODAY)
    other = own.model_copy(
        update={"id": new_id(), "branch_id": branch.id, "daily_rate": 99_999, "start_date": OCT_16}
    )
    store.insert(session, Contract.model_validate(other.model_dump()), Actor.system(branch.id))
    session.commit()
    assert tools._contract(session, pao.id, dt.date(2026, 10, 31)).daily_rate == 99_999
    (_,) = due.issue_payslips(
        session, stall, ((OCT_16, dt.date(2026, 10, 31)), PAYDAY.date()), PAYDAY
    )
    slip = _slips(session)[pao.id]
    days = calc.minutes_by_day(
        session, pao.id, OCT_16, dt.date(2026, 10, 31), MNL, own.rest_day, calc.holidays()
    )
    expected = ph.payslip(days, own.daily_rate, ph.monthly_basic(own.daily_rate))
    assert (slip.branch_id, slip.gross, slip.net) == (stall.id, expected.gross, expected.net)


def test_an_issued_payslip_is_not_recomputed(session: Session, hr: Ferinos, pin: Pin) -> None:
    _, people = hr
    _tick(session, pin, PAYDAY)
    before = _slips(session)[people["Ana"].id].model_dump()
    draft = _to_draft(session, people, dt.date(2026, 10, 17))  # two hours more on the 17th
    timesheets.approve(session, Actor.person(people["Marites"]), draft)
    session.commit()
    assert _tick(session, pin, PAYDAY.replace(hour=16)) == 0
    ana_branch = session.get(Branch, people["Ana"].branch_id)
    assert ana_branch is not None
    assert (
        due.issue_payslips(
            session, ana_branch, ((OCT_16, dt.date(2026, 10, 31)), PAYDAY.date()), PAYDAY
        )
        == []
    )
    assert _slips(session)[people["Ana"].id].model_dump() == before


def test_the_payslip_amounts_stay_off_the_event_log(
    session: Session, hr: Ferinos, pin: Pin
) -> None:
    """The notification row keeps the payslip (the person reads it in the app); its
    notification.sent event does not."""
    _, people = hr
    _tick(session, pin, PAYDAY)
    ana = _slips(session)[people["Ana"].id]
    (note,) = _notes(session, people["Ana"])
    lang = people["Ana"].language
    amounts = [format_money(ana.net, ana.currency, lang)]
    amounts += [format_money(int(line["amount"]), ana.currency, lang) for line in ana.lines]
    assert all(a in note.text for a in amounts)
    logged = [str(e.after) for e in _markers(session, "notification.sent")]
    assert logged and not any(a in text for a in amounts for text in logged)
    (event,) = [e for e in _markers(session, "notification.sent") if e.entity_id == note.id]
    assert event.after and event.after["text"] == events.REDACTED


def test_the_seeded_cutoff_is_not_issued_again(session: Session, hr: Ferinos, pin: Pin) -> None:
    """1 to 15 October already has the seed's payslips: payday 20 October issues none."""
    _, people = hr
    before = {k: v.model_dump() for k, v in _slips(session, dt.date(2026, 10, 1)).items()}
    assert _tick(session, pin, dt.datetime(2026, 10, 20, 9, tzinfo=MNL)) == 0
    after = {k: v.model_dump() for k, v in _slips(session, dt.date(2026, 10, 1)).items()}
    assert after == before and _notes(session, people["Ana"]) == []


def test_a_branch_without_contracts_issues_nothing(
    session: Session, branch: Branch, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = OrgSettings(agents=[MANIFEST.id])
    monkeypatch.setattr(orgconfig, "load", lambda org_name=None: org)
    at = dt.datetime(2026, 11, 5, 9, tzinfo=ZoneInfo(branch.timezone))
    assert due._branch_due(session, branch, at) == 0
    assert due.run_due(session, at) == 0


# ---- the approval reminder ------------------------------------------------------------------


def test_head_staff_are_reminded_to_approve_timesheets(
    session: Session, hr: Ferinos, pin: Pin
) -> None:
    _, people = hr
    _to_draft(session, people, dt.date(2026, 10, 17))
    assert _tick(session, pin, REMIND - dt.timedelta(days=1)) == 0
    assert _tick(session, pin, REMIND) == 1  # the mall's supervisor; the stall has no draft
    (note,) = _notes(session, people["Marites"])
    lang = people["Marites"].language
    assert note.text == t("hr.approval_reminder", lang, count=1, end="2026-10-31")
    assert _notes(session, people["Jun"]) == [] and _notes(session, people["Ana"]) == []
    (marker,) = _markers(session, due.REMINDED)
    assert marker.after and marker.after["message_ids"] == [note.id]
    assert _tick(session, pin, REMIND.replace(hour=17)) == 0


def test_no_reminder_without_drafts(session: Session, hr: Ferinos, pin: Pin) -> None:
    assert _tick(session, pin, REMIND) == 0 and _markers(session, due.REMINDED) == []


# ---- the organisation gate and quiet hours --------------------------------------------------


def test_nothing_runs_for_an_organisation_without_the_hr_officer(
    session: Session, hr: Ferinos, pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = OrgSettings(agents=["sales_supervisor"])
    with monkeypatch.context() as m:
        m.setattr(orgconfig, "load", lambda org_name=None: org)
        assert _tick(session, pin, PAYDAY) == 0
    assert _slips(session) == {}


def test_payslips_at_nine_are_not_held_for_quiet_hours(
    session: Session, hr: Ferinos, pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, people = hr
    saved = dict(registry._adapters)
    registry._adapters.clear()
    registry.register(SimAdapter())
    org = OrgSettings(agents=[MANIFEST.id], channels={"sim": ChannelConfig(enabled=True)})
    try:
        with monkeypatch.context() as m:
            m.setattr(orgconfig, "load", lambda org_name=None: org)
            ana = people["Ana"]
            identity = ChannelIdentity(
                branch_id=ana.branch_id, person_id=ana.id, channel="sim", address="639170000001"
            )
            store.insert(session, identity, Actor.person(ana), action="channel.linked")
            session.commit()
            assert _tick(session, pin, PAYDAY) == 3
        stmt = select(ChannelOutbox).where(ChannelOutbox.person_id == ana.id)
        rows = list(session.exec(stmt))
        assert rows and all(r.send_after is None for r in rows)
    finally:
        registry._adapters.clear()
        registry._adapters.update(saved)
