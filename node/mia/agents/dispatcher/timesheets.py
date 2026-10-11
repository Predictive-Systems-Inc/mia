"""Timesheets (plan Sprint 2, time and attendance chain; Q20): drafts built in code from
completed visits, corrections, approval with separation of duties (whoever entered a row
never approves it), and the payroll export from approved rows only.

Agent-owned (`dispatcher_timesheets`, rule 9) until Q20 places them in the data standard;
the shape is Q20's, so the move is a rename. All writes go through store (rule 1).
"""

import csv
import datetime as dt
import logging
from dataclasses import dataclass
from typing import TextIO

from sqlmodel import Session, col, select

from mia.agents.dispatcher.models import Timesheet
from mia.core import events, store
from mia.core.db import utcnow
from mia.core.models import Actor, Branch, Event, Location, Person, Visit
from mia.core.rbac import Resource, get_rbac

log = logging.getLogger(__name__)
LOOKBACK = dt.timedelta(days=14)  # completed visits older than this never get a draft
RESOURCE = "dispatcher_timesheets"


class TimesheetError(ValueError):
    """A correction or approval that the rules refuse (not a permission problem)."""


class SeparationError(TimesheetError):
    """The approver entered the row (the check-out or the correction)."""


def _minutes(start: dt.datetime, end: dt.datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def _checked_out_by(session: Session, visit: Visit) -> str | None:
    """The person who recorded the visit's check-out (the office when it acted for the
    cleaner), from the `visit.checked_out` event; None for a system actor."""
    row = session.exec(
        select(Event)
        .where(Event.action == "visit.checked_out")
        .where(Event.entity_id == visit.id)
        .order_by(col(Event.id).desc())
    ).first()
    return row.actor_id if row is not None and row.actor_type == "person" else None


def _build_in(session: Session, branch: Branch, now: dt.datetime) -> int:
    since = (now - LOOKBACK).date()
    visits = session.exec(
        select(Visit)
        .where(Visit.branch_id == branch.id)
        .where(Visit.status == "completed")
        .where(col(Visit.date) >= since)
        .order_by(col(Visit.id))
    ).all()
    have = {
        (t.visit_id, t.person_id)
        for t in session.exec(
            select(Timesheet)
            .where(Timesheet.branch_id == branch.id)
            .where(col(Timesheet.date) >= since)
        ).all()
    }
    count = 0
    for v in visits:
        timed = v.actual_start is not None and v.actual_end is not None
        enterer = _checked_out_by(session, v) if timed else None
        start = v.actual_start if timed and v.actual_start else v.planned_start
        end = v.actual_end if timed and v.actual_end else v.planned_end
        for pid in v.assigned_person_ids:
            if (v.id, pid) in have:
                continue
            row = Timesheet(
                branch_id=branch.id,
                visit_id=v.id,
                person_id=pid,
                date=v.date,
                start=start,
                end=end,
                minutes=_minutes(start, end),
                source="check_out" if timed else "planned",
                entered_by=enterer or pid,  # whoever recorded the check-out set the time
            )
            store.insert(session, row, Actor.system(branch.id), action="timesheet.created")
            have.add((v.id, pid))
            count += 1
    return count


def build_due(session: Session, now: dt.datetime) -> int:
    """One draft per completed visit and assigned person (the last 14 days), once: the visit's
    actual times when it was checked in and out, its planned times otherwise. Each branch
    commits its own work; a failing branch never silences the others. Returns how many."""
    count = 0
    for branch in session.exec(select(Branch)).all():
        try:
            count += _build_in(session, branch, now)
            session.commit()
        except Exception:
            session.rollback()
            log.exception("timesheets failed for branch %s", branch.id)
    return count


def _fresh(session: Session, row: Timesheet) -> None:
    """Take the write lock, then reread the row (rule 11): the checks decide on what is
    stored, not on a copy a parallel request may have changed."""
    events.write_lock(session)
    session.refresh(row)


def correct(
    session: Session, actor: Actor, row: Timesheet, start: dt.datetime, end: dt.datetime, note: str
) -> Timesheet:
    """Set the times (the person's own, or the office's); the row goes back to draft and the
    corrector becomes its enterer, so they cannot approve it. Raises TimesheetError when the
    end is not after the start."""
    get_rbac().require(
        actor,
        Resource(kind="data", name=RESOURCE, owner_id=row.person_id),
        "write",
        session=session,
    )
    _fresh(session, row)
    if row.status == "approved" and not get_rbac().check(
        actor, Resource(kind="data", name=RESOURCE), "write"
    ):
        raise TimesheetError("already approved; ask the office to correct it")
    if end <= start:
        raise TimesheetError("the end must be after the start")
    changes = {
        "start": start,
        "end": end,
        "minutes": _minutes(start, end),
        "source": "correction",
        "status": "draft",
        "entered_by": actor.principal.id,
        "note": note[:500],
        "approved_by": None,
        "approved_at": None,
    }
    return store.update(session, row, changes, actor, action="timesheet.corrected")


def approve(session: Session, actor: Actor, row: Timesheet) -> Timesheet:
    """Approve a draft (supervisors and up). Raises SeparationError when the approver entered
    it, TimesheetError when it is already approved."""
    get_rbac().require(actor, Resource(kind="data", name=RESOURCE), "write", session=session)
    _fresh(session, row)
    if row.status == "approved":
        raise TimesheetError("already approved")
    acting = {actor.principal.id} | ({actor.on_behalf_of.id} if actor.on_behalf_of else set())
    if acting & {row.entered_by, row.person_id}:
        raise SeparationError("whoever entered a timesheet, or whose time it is, never approves it")
    changes = {"status": "approved", "approved_by": actor.principal.id, "approved_at": utcnow()}
    return store.update(session, row, changes, actor, action="timesheet.approved")


# ---- payroll export -------------------------------------------------------------------------

COLUMNS = [
    "timesheet_id",
    "person_id",
    "person",
    "date",
    "location",
    "start",
    "end",
    "minutes",
    "source",
    "approved_by",
]


@dataclass
class PayrollRow:
    timesheet_id: str
    person_id: str
    person: str
    date: dt.date
    location: str
    start: str
    end: str
    minutes: int
    source: str
    approved_by: str


def payroll_rows(
    session: Session, branch_id: str, start: dt.date, end: dt.date
) -> list[PayrollRow]:
    """Approved timesheets of the period (inclusive), by person then date. Approved rows are
    the only source for payroll (plan Sprint 2); drafts never leave. Times are local ISO 8601."""
    from zoneinfo import ZoneInfo

    branch = session.get(Branch, branch_id)
    zone = ZoneInfo(branch.timezone if branch else "UTC")
    rows = session.exec(
        select(Timesheet)
        .where(Timesheet.branch_id == branch_id)
        .where(Timesheet.status == "approved")
        .where(col(Timesheet.date) >= start)
        .where(col(Timesheet.date) <= end)
    ).all()
    out = []
    for t in rows:
        person = session.get(Person, t.person_id)
        visit = session.get(Visit, t.visit_id)
        loc = session.get(Location, visit.location_id) if visit else None
        out.append(
            PayrollRow(
                timesheet_id=t.id,
                person_id=t.person_id,
                person=person.name if person else "?",
                date=t.date,
                location=loc.name if loc else "?",
                start=t.start.astimezone(zone).isoformat(),
                end=t.end.astimezone(zone).isoformat(),
                minutes=t.minutes,
                source=t.source,
                approved_by=t.approved_by or "",
            )
        )
    return sorted(out, key=lambda r: (r.person, r.date, r.start))


def write_csv(rows: list[PayrollRow], out: TextIO) -> None:
    """UTF-8 CSV with a header; the generic layout until Hype's payroll format is known (Q24)."""
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for r in rows:
        writer.writerow([getattr(r, c) if c != "date" else r.date.isoformat() for c in COLUMNS])
