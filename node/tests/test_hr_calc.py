import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.agents.hr_officer import calc
from mia.agents.hr_officer.models import Contract
from mia.agents.hr_officer.ph import Minutes
from mia.core import store
from mia.core.models import Actor, Branch, Person, Timesheet
from tests import test_hr_tools

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")
TODAY = test_hr_tools.TODAY
hr = test_hr_tools.hr  # the seed pinned to TODAY


def fortnight(session: Session, person: Person) -> list[Minutes]:
    contract = session.exec(select(Contract).where(Contract.person_id == person.id)).one()
    return calc.minutes_by_day(
        session,
        person.id,
        TODAY - dt.timedelta(days=14),
        TODAY - dt.timedelta(days=1),
        MNL,
        contract.rest_day,
        {},
    )


def test_the_night_shift_splits_into_overtime_and_night(session: Session, hr: Ferinos) -> None:
    _, people = hr
    days = fortnight(session, people["Liza"])
    late = [d for d in days if d.night]
    assert late == [Minutes(regular=480, overtime=150, night=90)]  # 13:00 to 23:30
    assert all(d == Minutes(regular=480) for d in days if not d.night)


def test_a_draft_timesheet_is_not_counted(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana = people["Ana"]
    before = fortnight(session, ana)
    sheet = session.exec(select(Timesheet).where(Timesheet.person_id == ana.id)).first()
    assert sheet is not None
    store.update(session, sheet, {"status": "draft"}, Actor.system(sheet.branch_id))
    assert len(fortnight(session, ana)) == len(before) - 1


def test_two_shifts_on_a_day_share_the_eight_hours() -> None:
    morning, evening = Minutes(regular=300), Minutes(regular=300, night=30)
    assert calc._sum([morning, evening]) == Minutes(regular=480, overtime=120, night=30)


def _cutoff_pay(session: Session, person: Person, holidays: dict[dt.date, str]) -> list[str]:
    contract = session.exec(select(Contract).where(Contract.person_id == person.id)).one()
    pay = calc.cutoff_pay(
        session, contract, dt.date(2026, 10, 1), dt.date(2026, 10, 15), MNL, holidays
    )
    assert pay is not None
    return [f"{line.kind} {line.minutes}" for line in pay.lines]


def test_the_cutoff_pays_approved_leave_days(session: Session, hr: Ferinos) -> None:
    """Liza's seeded vacation (Saturday 10 and Sunday 11 October) is two paid leave days."""
    _, people = hr
    assert _cutoff_pay(session, people["Liza"], {}) == ["regular 5280", "paid_leave 960"]


def test_an_unworked_regular_holiday_pays_when_the_day_before_was_worked(
    session: Session, hr: Ferinos
) -> None:
    """Pao (rest day Tuesday) is off sick on Wednesday 14 October; were it a regular holiday,
    it is no leave day but holiday pay, as he worked Monday the 12th; not after he missed it."""
    _, people = hr
    pao = people["Pao"]
    holiday = {dt.date(2026, 10, 14): "regular"}
    lines = _cutoff_pay(session, pao, holiday)
    assert "unworked_holiday 480" in lines and not any(x.startswith("paid_leave") for x in lines)
    stmt = select(Timesheet).where(Timesheet.person_id == pao.id)
    monday = session.exec(stmt.where(Timesheet.date == dt.date(2026, 10, 12))).one()
    store.update(session, monday, {"status": "draft"}, Actor.system(monday.branch_id))
    assert not any(x.startswith("unworked_holiday") for x in _cutoff_pay(session, pao, holiday))
