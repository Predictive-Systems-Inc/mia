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
