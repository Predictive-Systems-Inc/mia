"""Timesheets (Q20, agent-owned until the data standard decides): drafts from completed
visits, corrections, approval with separation of duties, the payroll export and the missing
check-out and overtime alerts."""

import csv
import datetime as dt
import io
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.agents.shift_supervisor import alerts, timesheets
from mia.api.main import app
from mia.cli import main
from mia.core import scheduling
from mia.core.models import Actor, Branch, Event, Job, Person, Timesheet, Visit
from mia.core.rbac import PermissionDenied
from tests.test_alerts import _notes


def _kamppi_today(session: Session) -> Visit:
    today = dt.datetime.now(ZoneInfo("Europe/Helsinki")).date()
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    return session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == today)
    ).one()


def _worked(session: Session, people: dict[str, Person], extra_minutes: int = 0) -> Visit:
    """Juha checks in and out of today's Kamppi visit, `extra_minutes` past the plan."""
    juha = people["Juha"]
    visit = _kamppi_today(session)
    scheduling.check_in(session, Actor.person(juha), visit, juha, visit.planned_start)
    end = visit.planned_end + dt.timedelta(minutes=extra_minutes)
    scheduling.check_out(session, Actor.person(juha), visit, juha, end)
    session.commit()
    return visit


def test_build_makes_one_draft_per_completed_visit_and_person_once(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    visit = _worked(session, people, extra_minutes=20)
    now = visit.planned_end + dt.timedelta(hours=1)
    made = timesheets.build_due(session, now)
    assert made > 0
    rows = session.exec(select(Timesheet)).all()
    done = session.exec(select(Visit).where(Visit.status == "completed")).all()
    assert {(r.visit_id, r.person_id) for r in rows} == {
        (v.id, pid) for v in done for pid in v.assigned_person_ids
    }
    mine = session.exec(select(Timesheet).where(Timesheet.visit_id == visit.id)).one()
    planned = int((visit.planned_end - visit.planned_start).total_seconds() // 60)
    assert (mine.minutes, mine.source, mine.status, mine.entered_by) == (
        planned + 20,
        "check_out",
        "draft",
        people["Juha"].id,
    )
    seeded = [r for r in rows if r.visit_id != visit.id]
    assert seeded and all(r.source == "planned" for r in seeded)  # no check-in: planned times
    assert timesheets.build_due(session, now) == 0  # idempotent
    assert session.exec(select(Event).where(Event.action == "timesheet.created")).all()


def test_correction_and_approval_with_separation_of_duties(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    juha, sanna, mikael = people["Juha"], people["Sanna"], people["Mikael"]
    visit = _worked(session, people)
    timesheets.build_due(session, visit.planned_end + dt.timedelta(hours=1))
    ts = session.exec(select(Timesheet).where(Timesheet.visit_id == visit.id)).one()
    with pytest.raises(PermissionDenied):  # staff never approve, their own least of all
        timesheets.approve(session, Actor.person(juha), ts)
    with pytest.raises(PermissionDenied):  # staff never approve, even someone else's
        other = session.exec(select(Timesheet).where(Timesheet.person_id == mikael.id)).first()
        assert other is not None
        timesheets.approve(session, Actor.person(juha), other)
    ts = timesheets.correct(
        session, Actor.person(sanna), ts, ts.start, ts.end + dt.timedelta(minutes=30), "late"
    )
    assert (ts.source, ts.entered_by, ts.status, ts.note) == (
        "correction",
        sanna.id,
        "draft",
        "late",
    )
    assert ts.minutes == int((ts.end - ts.start).total_seconds() // 60)
    with pytest.raises(timesheets.SeparationError):  # Sanna entered the correction
        timesheets.approve(session, Actor.person(sanna), ts)
    ts = timesheets.approve(session, Actor.person(people["Helena"]), ts)
    assert ts.status == "approved" and ts.approved_by == people["Helena"].id and ts.approved_at
    with pytest.raises(timesheets.TimesheetError):  # not twice
        timesheets.approve(session, Actor.person(people["Helena"]), ts)
    with pytest.raises(timesheets.TimesheetError):  # end before start
        timesheets.correct(session, Actor.person(sanna), ts, ts.end, ts.start, "")
    assert session.exec(select(Event).where(Event.action == "timesheet.approved")).one()


def test_api_lists_own_rows_for_staff_and_approves_for_the_office(
    session: Session,
    branch: Branch,
    people: dict[str, Person],
    login,  # type: ignore[no-untyped-def]
) -> None:
    juha, sanna = people["Juha"], people["Sanna"]
    visit = _worked(session, people)
    timesheets.build_due(session, visit.planned_end + dt.timedelta(hours=1))
    session.commit()
    staff = TestClient(app)
    login(staff, juha)
    rows = staff.get("/timesheets").json()
    assert rows and all(r["person_id"] == juha.id for r in rows)
    mine = next(r for r in rows if r["visit_id"] == visit.id)
    assert mine["location"] == "Kamppi shop" and mine["status"] == "draft"
    office = TestClient(app)
    login(office, sanna)
    assert len(office.get("/timesheets").json()) > len(rows)
    assert staff.post(f"/timesheets/{mine['id']}/approve").status_code == 403
    assert office.post(f"/timesheets/{mine['id']}/approve").status_code == 200
    other = next(r for r in office.get("/timesheets").json() if r["status"] == "draft")
    body = {"start": other["start"], "end": other["end"], "note": "ok"}
    assert office.post(f"/timesheets/{other['id']}/correct", json=body).status_code == 200
    assert office.post(f"/timesheets/{other['id']}/approve").status_code == 409  # own entry
    assert office.post("/timesheets/nope/approve").status_code == 404


def test_payroll_export_takes_approved_rows_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    session: Session,
    branch: Branch,
    people: dict[str, Person],
) -> None:
    visit = _worked(session, people)
    timesheets.build_due(session, visit.planned_end + dt.timedelta(hours=1))
    ts = session.exec(select(Timesheet).where(Timesheet.visit_id == visit.id)).one()
    timesheets.approve(session, Actor.person(people["Sanna"]), ts)
    session.commit()
    start, end = visit.date - dt.timedelta(days=30), visit.date
    rows = timesheets.payroll_rows(session, branch.id, start, end)
    assert [r.timesheet_id for r in rows] == [ts.id]
    out = io.StringIO()
    timesheets.write_csv(rows, out)
    reader = csv.DictReader(io.StringIO(out.getvalue()))
    assert reader.fieldnames == timesheets.COLUMNS
    (row,) = list(reader)
    assert row["person"] == people["Juha"].name and int(row["minutes"]) == ts.minutes
    path = tmp_path / "payroll.csv"
    args = [
        "payroll",
        "export",
        "--from",
        start.isoformat(),
        "--to",
        end.isoformat(),
        "--out",
        str(path),
    ]
    assert main(args) == 0
    assert "1 row(s)" in capsys.readouterr().out and path.read_text().startswith("timesheet_id,")
    session.expire_all()
    ev = session.exec(select(Event).where(Event.action == "payroll.exported")).one()
    assert ev.after == {"from": start.isoformat(), "to": end.isoformat(), "rows": 1}
    with pytest.raises(SystemExit):
        main(["payroll", "export", "--from", "2026-01-02", "--to", "2026-01-01"])


def test_missed_check_out_alerts_once_after_the_grace(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    juha, sanna = people["Juha"], people["Sanna"]
    visit = _kamppi_today(session)
    scheduling.check_in(session, Actor.person(juha), visit, juha, visit.planned_start)
    session.commit()
    assert alerts.missed_check_outs(session, visit.planned_end + dt.timedelta(minutes=10)) == 0
    late = (visit.planned_end + dt.timedelta(minutes=40)).astimezone(dt.UTC)
    assert alerts.missed_check_outs(session, late) == 1
    assert "Kamppi shop" in _notes(session, juha)[-1].text
    assert "Juha" in _notes(session, sanna)[-1].text
    assert alerts.missed_check_outs(session, late + dt.timedelta(hours=1)) == 0


def test_overtime_alerts_supervisors_once(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    sanna = people["Sanna"]
    visit = _worked(session, people, extra_minutes=60)
    now = visit.planned_end + dt.timedelta(hours=2)
    timesheets.build_due(session, now)
    assert alerts.overtime(session, now) == 1
    assert "Juha" in _notes(session, sanna)[-1].text and "60" in _notes(session, sanna)[-1].text
    assert alerts.overtime(session, now) == 0


def test_office_check_out_makes_the_office_the_enterer(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core.models import Principal

    juha, sanna, helena = people["Juha"], people["Sanna"], people["Helena"]
    visit = _kamppi_today(session)
    scheduling.check_in(session, Actor.person(juha), visit, juha, visit.planned_start)
    office = Actor(
        principal=Actor.person(sanna).principal,
        on_behalf_of=Principal(type="person", id=juha.id, roles=list(juha.roles)),
        branch_id=branch.id,
    )
    scheduling.check_out(session, office, visit, juha, visit.planned_end + dt.timedelta(hours=2))
    session.commit()
    timesheets.build_due(session, visit.planned_end + dt.timedelta(hours=3))
    ts = session.exec(select(Timesheet).where(Timesheet.visit_id == visit.id)).one()
    assert ts.entered_by == sanna.id  # she set the time, so she never approves it
    with pytest.raises(timesheets.SeparationError):
        timesheets.approve(session, Actor.person(sanna), ts)
    assert timesheets.approve(session, Actor.person(helena), ts).status == "approved"


def test_nobody_approves_their_own_hours_or_on_behalf_of_them(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core import store
    from mia.core.models import Principal

    juha, sanna, helena = people["Juha"], people["Sanna"], people["Helena"]
    visit = _worked(session, people)
    timesheets.build_due(session, visit.planned_end + dt.timedelta(hours=1))
    ts = session.exec(select(Timesheet).where(Timesheet.visit_id == visit.id)).one()
    ts = timesheets.correct(session, Actor.person(helena), ts, ts.start, ts.end, "")
    for_juha = Actor(
        principal=Actor.person(sanna).principal,
        on_behalf_of=Principal(type="person", id=juha.id, roles=list(juha.roles)),
        branch_id=branch.id,
    )
    with pytest.raises(PermissionDenied):  # acting for staff: both must be allowed (rule 5)
        timesheets.approve(session, for_juha, ts)
    done = session.exec(
        select(Visit).where(Visit.status == "completed").where(Visit.id != visit.id)
    ).first()
    assert done is not None
    store.update(session, done, {"assigned_person_ids": [sanna.id]}, Actor.person(helena))
    timesheets.build_due(session, visit.planned_end + dt.timedelta(hours=1))
    own = session.exec(
        select(Timesheet)
        .where(Timesheet.visit_id == done.id)
        .where(Timesheet.person_id == sanna.id)
    ).one()
    own = timesheets.correct(session, Actor.person(helena), own, own.start, own.end, "")
    with pytest.raises(timesheets.SeparationError):  # her own hours, entered by Helena
        timesheets.approve(session, Actor.person(sanna), own)
    for_sanna = Actor(
        principal=Actor.person(helena).principal,
        on_behalf_of=Principal(type="person", id=sanna.id, roles=list(sanna.roles)),
        branch_id=branch.id,
    )
    with pytest.raises(timesheets.SeparationError):  # Helena acting for Sanna: still hers
        timesheets.approve(session, for_sanna, own)
    assert (
        timesheets.approve(session, Actor.person(sanna), ts).status == "approved"
    )  # Juha's, entered by Helena


def test_an_approved_row_is_corrected_by_the_office_only(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    juha, sanna = people["Juha"], people["Sanna"]
    visit = _worked(session, people)
    timesheets.build_due(session, visit.planned_end + dt.timedelta(hours=1))
    ts = session.exec(select(Timesheet).where(Timesheet.visit_id == visit.id)).one()
    ts = timesheets.approve(session, Actor.person(sanna), ts)
    later = ts.end + dt.timedelta(hours=1)
    with pytest.raises(timesheets.TimesheetError):
        timesheets.correct(session, Actor.person(juha), ts, ts.start, later, "forgot")
    assert ts.status == "approved"
    ts = timesheets.correct(session, Actor.person(sanna), ts, ts.start, later, "late")
    assert ts.status == "draft" and ts.entered_by == sanna.id


def test_approve_checks_the_stored_row_not_a_stale_copy(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from sqlmodel import Session as Other

    from mia.core.db import get_engine

    sanna = people["Sanna"]
    visit = _worked(session, people)
    timesheets.build_due(session, visit.planned_end + dt.timedelta(hours=1))
    session.commit()
    ts = session.exec(select(Timesheet).where(Timesheet.visit_id == visit.id)).one()
    assert ts.entered_by == people["Juha"].id
    with Other(get_engine()) as other:  # a parallel request: Sanna corrects it meanwhile
        row = other.get(Timesheet, ts.id)
        assert row is not None
        timesheets.correct(other, Actor.person(sanna), row, row.start, row.end, "")
        other.commit()
    with pytest.raises(timesheets.SeparationError):  # the check reads the stored enterer
        timesheets.approve(session, Actor.person(sanna), ts)


def test_api_refuses_naive_times(
    session: Session,
    branch: Branch,
    people: dict[str, Person],
    login,  # type: ignore[no-untyped-def]
) -> None:
    visit = _worked(session, people)
    timesheets.build_due(session, visit.planned_end + dt.timedelta(hours=1))
    session.commit()
    ts = session.exec(select(Timesheet).where(Timesheet.visit_id == visit.id)).one()
    office = TestClient(app)
    login(office, people["Sanna"])
    body = {"start": "2026-10-12T08:00:00", "end": "2026-10-12T10:00:00", "note": ""}
    assert office.post(f"/timesheets/{ts.id}/correct", json=body).status_code == 422
