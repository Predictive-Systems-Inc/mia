"""Timesheet routes: the list (staff see their own), a correction and the approval. The
service holds the rules (separation of duties); every route checks RBAC (rule 4)."""

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime, BaseModel, Field
from sqlmodel import col, select

from mia.agents.dispatcher import timesheets
from mia.agents.dispatcher.models import Timesheet
from mia.api.deps import AuthContext, DbSession, PersonAuth
from mia.api.schedule import branch_of
from mia.core.models import Location, Person, Visit
from mia.core.rbac import PermissionDenied, Resource, get_rbac

router = APIRouter(tags=["timesheets"])
ALL = Resource(kind="data", name=timesheets.RESOURCE)


class TimesheetCard(BaseModel):
    id: str
    visit_id: str
    person_id: str
    person: str
    date: dt.date
    location: str
    start: str
    end: str
    minutes: int
    source: str
    status: str
    entered_by: str
    note: str
    approved_by: str | None


class CorrectIn(BaseModel):
    start: AwareDatetime  # rule 10: a zone on every time, else 422
    end: AwareDatetime
    note: str = Field(default="", max_length=500)


def _card(session: DbSession, row: Timesheet, zone: ZoneInfo) -> TimesheetCard:
    person = session.get(Person, row.person_id)
    visit = session.get(Visit, row.visit_id)
    loc = session.get(Location, visit.location_id) if visit else None
    return TimesheetCard(
        id=row.id,
        visit_id=row.visit_id,
        person_id=row.person_id,
        person=person.name if person else "?",
        date=row.date,
        location=loc.name if loc else "?",
        start=row.start.astimezone(zone).isoformat(),
        end=row.end.astimezone(zone).isoformat(),
        minutes=row.minutes,
        source=row.source,
        status=row.status,
        entered_by=row.entered_by,
        note=row.note,
        approved_by=row.approved_by,
    )


def _row(session: DbSession, ctx: AuthContext, timesheet_id: str) -> Timesheet:
    row = session.get(Timesheet, timesheet_id)
    if row is None or row.branch_id != ctx.actor.branch_id:
        raise HTTPException(404, "timesheet not found")
    return row


@router.get("/timesheets", response_model=list[TimesheetCard])
def list_timesheets(
    session: DbSession,
    ctx: PersonAuth,
    start: dt.date | None = None,
    end: dt.date | None = None,
    person_id: str | None = None,
) -> list[TimesheetCard]:
    """Timesheets of the period (default: the last 14 days). Staff see their own."""
    assert ctx.person is not None
    branch = branch_of(session, ctx)
    zone = ZoneInfo(branch.timezone)
    if person_id is None and not get_rbac().check(ctx.actor, ALL, "read"):
        person_id = ctx.person.id
    try:
        get_rbac().require(
            ctx.actor,
            Resource(kind="data", name=timesheets.RESOURCE, owner_id=person_id),
            "read",
            session=session,
        )
    except PermissionDenied as exc:
        raise HTTPException(403, "not allowed") from exc
    end = end or dt.datetime.now(zone).date()
    start = start or end - dt.timedelta(days=14)
    stmt = (
        select(Timesheet)
        .where(Timesheet.branch_id == branch.id)
        .where(col(Timesheet.date) >= start)
        .where(col(Timesheet.date) <= end)
        .order_by(col(Timesheet.date), col(Timesheet.start))
    )
    if person_id is not None:
        stmt = stmt.where(Timesheet.person_id == person_id)
    return [_card(session, r, zone) for r in session.exec(stmt).all()]


@router.post("/timesheets/{timesheet_id}/correct", response_model=TimesheetCard)
def correct(
    session: DbSession, ctx: PersonAuth, timesheet_id: str, body: CorrectIn
) -> TimesheetCard:
    """Set the times; the corrector becomes the enterer and cannot approve the row."""
    row = _row(session, ctx, timesheet_id)
    try:
        row = timesheets.correct(session, ctx.actor, row, body.start, body.end, body.note)
    except PermissionDenied as exc:
        raise HTTPException(403, "not allowed") from exc
    except timesheets.TimesheetError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _card(session, row, ZoneInfo(branch_of(session, ctx).timezone))


@router.post("/timesheets/{timesheet_id}/approve", response_model=TimesheetCard)
def approve(session: DbSession, ctx: PersonAuth, timesheet_id: str) -> TimesheetCard:
    """Approve a draft (supervisors and up, never the person who entered it: 409)."""
    row = _row(session, ctx, timesheet_id)
    try:
        row = timesheets.approve(session, ctx.actor, row)
    except PermissionDenied as exc:
        raise HTTPException(403, "not allowed") from exc
    except timesheets.TimesheetError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _card(session, row, ZoneInfo(branch_of(session, ctx).timezone))
