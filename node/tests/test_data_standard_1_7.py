"""Data standard 1.7 (D39): the incident kinds of a kiosk, and the retail seed's shift data (the
closures table, the staff role graph, availability, limits, one Job per clerk, generated
shifts). The shared constants and helpers here are imported by the retail shift tests."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from mia.agents.shift_supervisor import MANIFEST
from mia.agents.shift_supervisor.tools import ReportProblemInput
from mia.core import scheduling
from mia.core.models import (
    INCIDENT_KINDS,
    STANDARD_VERSION,
    Availability,
    Branch,
    Job,
    Person,
    Visit,
    WorkLimit,
)
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailClosure
from tests.conftest import RS_TODAY

Ferinos = tuple[Branch, dict[str, Person]]
SATURDAY, NOV_1, MONDAY, TUESDAY = (RS_TODAY + dt.timedelta(days=n) for n in (3, 4, 5, 6))
TU_SU = "TU,WE,TH,FR,SA,SU"
MNL = ZoneInfo("Asia/Manila")


def at(day: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    """hh:mm on the day in Manila."""
    return dt.datetime.combine(day, dt.time(hh, mm), MNL)


def stall(session: Session) -> Branch:
    """The Street stall."""
    return session.exec(select(Branch).where(Branch.name == "Street stall")).one()


def visit_of(session: Session, who: Person, day: dt.date) -> Visit:
    """The person's visit that day at their branch (scheduling.week)."""
    week = scheduling.week(session, who.branch_id, day, person_id=who.id)
    return next(v for v in week if v.date == day)


def names_on(session: Session, v: Visit) -> list[str]:
    """The first names assigned to the visit, in assignment order."""
    return [p.name.split()[0] for i in v.assigned_person_ids if (p := session.get(Person, i))]


def test_an_unknown_incident_kind_is_refused() -> None:
    with pytest.raises(ValidationError):
        ReportProblemInput(kind="fire", text="x")  # type: ignore[arg-type]


def test_incident_kinds_are_the_code_list_of_1_7() -> None:
    kinds = ("cannot_access", "site_problem", "equipment", "no_delivery", "customer")
    assert (STANDARD_VERSION, INCIDENT_KINDS, MANIFEST.standard_version) == ("1.7", kinds, "1.7")


def test_a_clerk_is_staff_by_inheritance(session: Session, rs: Ferinos) -> None:
    names = ("Ana", "Pao", "Marites", "Rosa")
    assert [scheduling.is_staff(rs[1][n]) for n in names] == [True, True, False, False]


def test_retail_clerks_have_availability_and_limits(session: Session, rs: Ferinos) -> None:
    def rows(p: Person) -> list[Availability]:
        return list(session.exec(select(Availability).where(Availability.person_id == p.id)))

    days = [sorted(a.weekday for a in rows(rs[1][n])) for n in ("Ana", "Liza", "Pao")]
    assert days == [[1, 2, 3, 4, 5, 6]] * 2 + [[0, 2, 3, 4, 5, 6]]
    limit = session.exec(select(WorkLimit).where(WorkLimit.person_id == rs[1]["Ana"].id)).one()
    pao = rows(rs[1]["Pao"])[0]
    assert ((pao.start, pao.end), limit.max_daily_minutes, limit.max_weekly_minutes) == (
        ("06:00", "19:00"),
        600,
        3240,
    )


def test_the_seed_plans_each_clerks_shift_from_today(session: Session, rs: Ferinos) -> None:
    jobs = {
        j.name: (j.recurrence, j.start_time, j.duration_minutes) for j in session.exec(select(Job))
    }
    assert jobs == {
        "Opening Ana": (f"FREQ=WEEKLY;BYDAY={TU_SU}", "09:00", 480),
        "Closing Liza": (f"FREQ=WEEKLY;BYDAY={TU_SU}", "13:00", 480),
        "Opening Pao": ("FREQ=WEEKLY;BYDAY=MO,WE,TH,FR,SA,SU", "06:00", 540),
    }
    sat = [v for v in scheduling.week(session, rs[0].id, SATURDAY) if v.date == SATURDAY]
    assert sorted(names_on(session, v) for v in sat) == [["Ana"], ["Liza"]]
    assert {v.status for v in sat} == {"planned"}


def test_the_seeded_closure_cancels_the_stalls_holiday(session: Session, rs: Ferinos) -> None:
    (row,) = session.exec(select(RetailClosure)).all()
    assert (row.branch_id, row.date) == (stall(session).id, NOV_1)
    that_day = select(Visit).where(Visit.branch_id == row.branch_id).where(Visit.date == NOV_1)
    assert [v.status for v in session.exec(that_day)] == ["cancelled"]
    is_open = retail_hours.open_days(
        retail_hours.load(session, row.branch_id), retail_hours.closed(session, row.branch_id)
    )
    assert is_open(NOV_1) is False and is_open(MONDAY) is True


def test_the_seed_opens_one_equipment_incident_on_paos_next_shift(
    session: Session, rs: Ferinos
) -> None:
    from mia.core.models import Incident

    (row,) = session.exec(select(Incident)).all()
    assert (row.kind, row.status, row.person_id) == ("equipment", "open", rs[1]["Pao"].id)
    assert row.visit_id == visit_of(session, rs[1]["Pao"], RS_TODAY).id


def test_cancel_day_leaves_a_shift_in_progress(session: Session, rs: Ferinos) -> None:
    from mia.core.models import Actor

    kiosk, ana = rs[0], rs[1]["Ana"]
    started = visit_of(session, ana, SATURDAY)
    scheduling.check_in(session, Actor.system(kiosk.id), started, ana, at(SATURDAY, 9))
    cancelled = scheduling.cancel_day(session, Actor.system(kiosk.id), kiosk.id, SATURDAY)
    assert [names_on(session, v) for v in cancelled] == [["Liza"]]
    assert started.status == "in_progress"
