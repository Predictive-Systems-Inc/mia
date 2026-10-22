"""Schedule routes (plan item 4): the week view, assignment, check-in and check-out, and the
approvals inbox. Every route takes the signed-in person and checks RBAC (rule 4)."""

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from mia.api.deps import AuthContext, DbSession, PersonAuth
from mia.core import scheduling
from mia.core.db import utcnow
from mia.core.models import Actor, Branch, Job, Location, Person, Principal, Visit
from mia.core.rbac import PermissionDenied, Resource, get_rbac

router = APIRouter(tags=["schedule"])
VISIT = Resource(kind="data", name="core.visit")


class AssignIn(BaseModel):
    person_id: str = Field(max_length=26)
    add: bool = False


class UnassignIn(BaseModel):
    person_id: str = Field(max_length=26)


class PersonIn(BaseModel):
    person_id: str | None = Field(default=None, max_length=26)


class Assignee(BaseModel):
    id: str
    name: str


class VisitCard(BaseModel):
    id: str
    date: dt.date
    start: str
    end: str
    job: str
    location: str
    address: str
    assignees: list[Assignee]
    status: str


class PersonCard(BaseModel):
    id: str
    name: str
    roles: list[str]
    skills: list[str]
    language: str


class AssignOut(BaseModel):
    visit: VisitCard
    approval_id: str | None
    reasons: list[str]


class ApprovalCard(BaseModel):
    id: str
    type: str
    summary: str
    evidence: dict[str, object]
    requester_id: str
    created_at: dt.datetime
    expires_at: dt.datetime | None
    status: str
    channel: str


def _person(ctx: AuthContext) -> Person:
    assert ctx.person is not None  # PersonAuth guarantees it
    return ctx.person


def require_visit(session: Session, ctx: AuthContext, action: str, owner_id: str | None) -> None:
    resource = Resource(kind="data", name="core.visit", owner_id=owner_id)
    try:
        get_rbac().require(ctx.actor, resource, action, session=session)
    except PermissionDenied as exc:
        raise HTTPException(403, "not allowed") from exc


def visit_card(session: Session, visit: Visit, tz: str) -> VisitCard:
    zone = ZoneInfo(tz)
    job = session.get(Job, visit.job_id)
    loc = session.get(Location, visit.location_id)
    people = [session.get(Person, pid) for pid in visit.assigned_person_ids]
    return VisitCard(
        id=visit.id,
        date=visit.date,
        start=visit.planned_start.astimezone(zone).isoformat(),
        end=visit.planned_end.astimezone(zone).isoformat(),
        job=job.name if job else "?",
        location=loc.name if loc else "?",
        address=loc.address if loc else "",
        assignees=[Assignee(id=p.id, name=p.name) for p in people if p is not None],
        status=visit.status,
    )


def branch_of(session: Session, ctx: AuthContext) -> Branch:
    branch = session.get(Branch, ctx.actor.branch_id)
    assert branch is not None
    return branch


def _visit(session: Session, ctx: AuthContext, visit_id: str) -> Visit:
    visit = session.get(Visit, visit_id)
    if visit is None or visit.branch_id != ctx.actor.branch_id:
        raise HTTPException(404, "visit not found")
    return visit


def _target(session: Session, ctx: AuthContext, person_id: str) -> Person:
    person = session.get(Person, person_id)
    if person is None or person.branch_id != ctx.actor.branch_id:
        raise HTTPException(404, "person not found")
    return person


@router.get("/schedule", response_model=list[VisitCard])
def schedule(
    session: DbSession,
    ctx: PersonAuth,
    start: dt.date | None = None,
    person_id: str | None = None,
    location_id: str | None = None,
) -> list[VisitCard]:
    """Seven days of visits from `start` (today). Staff see their own; the office sees the
    branch, one person or one site."""
    me = _person(ctx)
    branch = branch_of(session, ctx)
    start = start or utcnow().astimezone(ZoneInfo(branch.timezone)).date()
    if person_id is None and location_id is None and not get_rbac().check(ctx.actor, VISIT, "read"):
        person_id = me.id
    require_visit(session, ctx, "read", person_id)
    rows = scheduling.week(session, branch.id, start, person_id=person_id, location_id=location_id)
    return [visit_card(session, v, branch.timezone) for v in rows]


@router.get("/schedule/people", response_model=list[PersonCard])
def people(session: DbSession, ctx: PersonAuth) -> list[PersonCard]:
    """The branch's active people for the board's assignment controls (office roles: staff
    read only their own person, so they get 403)."""
    try:
        get_rbac().require(
            ctx.actor, Resource(kind="data", name="core.person"), "read", session=session
        )
    except PermissionDenied as exc:
        raise HTTPException(403, "not allowed") from exc
    rows = session.exec(
        select(Person)
        .where(Person.branch_id == ctx.actor.branch_id)
        .where(Person.status == "active")
        .order_by(col(Person.name))
    ).all()
    return [
        PersonCard(id=p.id, name=p.name, roles=p.roles, skills=p.skills, language=p.language)
        for p in rows
    ]


@router.post("/visits/{visit_id}/assign", response_model=AssignOut)
def assign(session: DbSession, ctx: PersonAuth, visit_id: str, body: AssignIn) -> AssignOut:
    """Assign a person; an override approval comes back when a rule breaks (409 otherwise)."""
    require_visit(session, ctx, "write", None)  # before the lookup: no visit ids to probe
    visit = _visit(session, ctx, visit_id)
    person = _target(session, ctx, body.person_id)
    try:
        out = scheduling.assign(session, ctx.actor, visit, person, add=body.add)
    except scheduling.ScheduleError as exc:
        raise HTTPException(409, str(exc)) from exc
    tz = branch_of(session, ctx).timezone
    return AssignOut(
        visit=visit_card(session, out.visit, tz), approval_id=out.approval_id, reasons=out.reasons
    )


@router.post("/visits/{visit_id}/unassign", response_model=VisitCard)
def unassign(session: DbSession, ctx: PersonAuth, visit_id: str, body: UnassignIn) -> VisitCard:
    """Take a person off a visit."""
    require_visit(session, ctx, "write", None)
    visit = _visit(session, ctx, visit_id)
    person = _target(session, ctx, body.person_id)
    try:
        row = scheduling.unassign(session, ctx.actor, visit, person)
    except scheduling.ScheduleError as exc:
        raise HTTPException(409, str(exc)) from exc
    return visit_card(session, row, branch_of(session, ctx).timezone)


def _attendance(
    session: Session, ctx: AuthContext, visit_id: str, body: PersonIn | None, fn: str
) -> VisitCard:
    visit = _visit(session, ctx, visit_id)
    me = _person(ctx)
    person = _target(session, ctx, body.person_id) if body and body.person_id else me
    # Own visit: write_own against the assignees; someone else's: write.
    own = person.id == me.id and me.id in visit.assigned_person_ids
    require_visit(session, ctx, "write", me.id if own else None)
    actor = ctx.actor
    if person.id != me.id:  # the office acting for a cleaner: both are logged (rule 5)
        actor = Actor(
            principal=ctx.actor.principal,
            on_behalf_of=Principal(type="person", id=person.id, roles=list(person.roles)),
            branch_id=ctx.actor.branch_id,
        )
    try:
        row = getattr(scheduling, fn)(session, actor, visit, person, utcnow())
    except scheduling.ScheduleError as exc:
        raise HTTPException(409, str(exc)) from exc
    return visit_card(session, row, branch_of(session, ctx).timezone)


@router.post("/visits/{visit_id}/check-in", response_model=VisitCard)
def check_in(
    session: DbSession, ctx: PersonAuth, visit_id: str, body: PersonIn | None = None
) -> VisitCard:
    """The acting person (or, for the office, `person_id`) arrives at the site."""
    return _attendance(session, ctx, visit_id, body, "check_in")


@router.post("/visits/{visit_id}/check-out", response_model=VisitCard)
def check_out(
    session: DbSession, ctx: PersonAuth, visit_id: str, body: PersonIn | None = None
) -> VisitCard:
    """The visit is finished."""
    return _attendance(session, ctx, visit_id, body, "check_out")


@router.get("/approvals", response_model=list[ApprovalCard])
def approvals_inbox(session: DbSession, ctx: PersonAuth) -> list[ApprovalCard]:
    """The approvals the signed-in person may decide, oldest first."""
    return [
        ApprovalCard(
            id=a.id,
            type=a.type,
            summary=a.summary,
            evidence=dict(a.evidence),
            requester_id=a.requester_id,
            created_at=a.created_at,
            expires_at=a.expires_at,
            status=a.status,
            channel=a.channel,
        )
        for a in scheduling.inbox(session, ctx.actor)
    ]
