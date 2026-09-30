"""Dispatcher tools: typed inputs and outputs, permission checked data access, writes only
through mia.core services. Scheduling decisions live in scoring.py, not in the model."""

import datetime as dt
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.dispatcher import scoring
from mia.agents.dispatcher.models import Absence
from mia.core import approvals, store
from mia.core.models import Actor, Approval, Job, Location, Person, Visit
from mia.core.rbac import Resource, get_rbac
from mia.templates.cleaning.models import StaffAvailability, WorkLimit

APPROVAL_TYPE = "assignment_change"
MORNING_ENDS = dt.time(12, 0)


# ---- shared read models -------------------------------------------------------------------


class VisitInfo(BaseModel):
    visit_id: str
    date: dt.date
    start: str
    end: str
    location: str
    job: str
    assigned: list[str]
    status: str


class Candidate(BaseModel):
    person_id: str
    name: str
    reasons: list[str]


def _names(session: Session, ids: list[str]) -> list[str]:
    return [p.name for i in ids if (p := session.get(Person, i)) is not None]


def visit_info(session: Session, visit: Visit, tz: str) -> VisitInfo:
    loc = session.get(Location, visit.location_id)
    job = session.get(Job, visit.job_id)
    zone = ZoneInfo(tz)
    return VisitInfo(
        visit_id=visit.id,
        date=visit.date,
        start=visit.planned_start.astimezone(zone).strftime("%H:%M"),
        end=visit.planned_end.astimezone(zone).strftime("%H:%M"),
        location=loc.name if loc else "?",
        job=job.name if job else "?",
        assigned=_names(session, visit.assigned_person_ids),
        status=visit.status,
    )


def visits_for(
    session: Session, branch_id: str, person_id: str, start: dt.date, end: dt.date
) -> list[Visit]:
    stmt = (
        select(Visit)
        .where(Visit.branch_id == branch_id)
        .where(col(Visit.date) >= start)
        .where(col(Visit.date) <= end)
        .order_by(col(Visit.planned_start))
    )
    return [v for v in session.exec(stmt) if person_id in v.assigned_person_ids]


def find_person(session: Session, branch_id: str, hint: str) -> Person:
    """Match a (possibly inflected) first name or full name. Raises LookupError."""
    hint_low = hint.lower().strip()
    persons = session.exec(select(Person).where(Person.branch_id == branch_id)).all()
    for p in persons:
        if p.name.lower() == hint_low:
            return p
    matches = []
    for p in persons:
        first = p.name.split()[0].lower()
        if hint_low.startswith(first) or (len(hint_low) >= 3 and first.startswith(hint_low)):
            matches.append(p)
    if len(matches) != 1:
        raise LookupError(f"no single person matches {hint!r}")
    return matches[0]


def _check(deps: AgentDeps, resource: Resource, action: str, tool_call_id: str) -> None:
    get_rbac().require(
        deps.actor, resource, action, session=deps.session, tool_call_id=tool_call_id
    )


# ---- get_my_visits ------------------------------------------------------------------------


class GetMyVisitsInput(BaseModel):
    start: dt.date | None = Field(None, description="First day, default today")
    end: dt.date | None = Field(None, description="Last day, default six days after start")
    person_name: str | None = Field(
        None, description="Only when the user asks about someone else's visits"
    )


class VisitList(BaseModel):
    person: str
    visits: list[VisitInfo]


def get_my_visits(deps: AgentDeps, args: GetMyVisitsInput, tool_call_id: str) -> VisitList:
    """List visits for the acting person (or, with permission, for another person)."""
    target = deps.person
    if args.person_name:
        target = find_person(deps.session, deps.branch.id, args.person_name)
    resource = Resource(kind="data", name="core.visit", owner_id=target.id)
    _check(deps, resource, "read", tool_call_id)
    start = args.start or deps.today
    end = args.end or start + dt.timedelta(days=6)
    visits = visits_for(deps.session, deps.branch.id, target.id, start, end)
    infos = [visit_info(deps.session, v, deps.branch.timezone) for v in visits]
    return VisitList(person=target.name, visits=infos)


# ---- record_absence -----------------------------------------------------------------------


class RecordAbsenceInput(BaseModel):
    date: dt.date
    reason: Literal["sick", "late", "leaving_early", "other"] = "sick"
    partial_day: Literal["morning", "afternoon"] | None = Field(
        None, description="None means the whole day"
    )
    person_name: str | None = Field(None, description="Only when reporting for someone else")


class RecordAbsenceOutput(BaseModel):
    absence_id: str
    person: str
    date: dt.date
    partial_day: str | None
    updated: bool
    affected_visits: list[VisitInfo]


def _affected(visits: list[Visit], partial_day: str | None, tz: str) -> list[Visit]:
    if partial_day is None:
        return visits
    zone = ZoneInfo(tz)
    morning = [v for v in visits if v.planned_start.astimezone(zone).time() < MORNING_ENDS]
    return morning if partial_day == "morning" else [v for v in visits if v not in morning]


def record_absence(
    deps: AgentDeps, args: RecordAbsenceInput, tool_call_id: str
) -> RecordAbsenceOutput:
    """Record (or update) an absence and return the visits it affects. Visits are not changed."""
    person = deps.person
    if args.person_name:
        person = find_person(deps.session, deps.branch.id, args.person_name)
    resource = Resource(kind="data", name="dispatcher_absences", owner_id=person.id)
    _check(deps, resource, "write", tool_call_id)
    existing = deps.session.exec(
        select(Absence).where(Absence.person_id == person.id).where(Absence.date == args.date)
    ).first()
    if existing:
        changes = {"reason": args.reason, "partial_day": args.partial_day}
        absence = store.update(
            deps.session, existing, changes, deps.actor, tool_call_id=tool_call_id
        )
    else:
        absence = store.insert(
            deps.session,
            Absence(
                branch_id=deps.branch.id,
                person_id=person.id,
                date=args.date,
                reason=args.reason,
                partial_day=args.partial_day,
                reported_by=deps.person.id,
            ),
            deps.actor,
            tool_call_id=tool_call_id,
        )
    day_visits = visits_for(deps.session, deps.branch.id, person.id, args.date, args.date)
    affected = _affected(day_visits, args.partial_day, deps.branch.timezone)
    return RecordAbsenceOutput(
        absence_id=absence.id,
        person=person.name,
        date=args.date,
        partial_day=args.partial_day,
        updated=existing is not None,
        affected_visits=[visit_info(deps.session, v, deps.branch.timezone) for v in affected],
    )


# ---- find_replacements --------------------------------------------------------------------


class FindReplacementsInput(BaseModel):
    visit_id: str | None = Field(None, description="The visit, if known")
    location_name: str | None = Field(None, description="Site name when visit_id is unknown")
    date: dt.date | None = Field(None, description="Visit day when visit_id is unknown")
    time: dt.time | None = Field(None, description="Visit start time when visit_id is unknown")


class FindReplacementsOutput(BaseModel):
    visit: VisitInfo
    candidates: list[Candidate]
    escalated: bool


def _location_matches(loc: Location, hint: str) -> bool:
    hint_low = hint.lower()
    return any(
        hint_low.startswith(word) or word.startswith(hint_low)
        for word in loc.name.lower().split()
        if len(word) >= 4
    )


def resolve_visit(session: Session, deps: AgentDeps, args: FindReplacementsInput) -> Visit:
    """Find the visit by id or by site, day and start time. Raises LookupError."""
    if args.visit_id:
        visit = session.get(Visit, args.visit_id)
        if visit is None or visit.branch_id != deps.branch.id:
            raise LookupError("visit not found")
        return visit
    if not args.location_name:
        raise LookupError("need a visit id or a site name")
    day = args.date or deps.today
    locations = session.exec(select(Location).where(Location.branch_id == deps.branch.id)).all()
    loc_ids = {loc.id for loc in locations if _location_matches(loc, args.location_name)}
    stmt = select(Visit).where(Visit.date == day).where(col(Visit.location_id).in_(loc_ids))
    visits = sorted(session.exec(stmt), key=lambda v: v.planned_start)
    zone = ZoneInfo(deps.branch.timezone)
    if args.time is not None:
        target = args.time.hour * 60 + args.time.minute

        def distance(v: Visit) -> int:
            local = v.planned_start.astimezone(zone)
            return abs(local.hour * 60 + local.minute - target)

        visits = [v for v in visits if distance(v) <= 30]
    if not visits:
        raise LookupError("no matching visit")
    return visits[0]


def _slot(visit: Visit, tz: str) -> scoring.Slot:
    zone = ZoneInfo(tz)
    return scoring.Slot(visit.planned_start.astimezone(zone), visit.planned_end.astimezone(zone))


def candidate_data(session: Session, deps: AgentDeps, visit: Visit) -> list[scoring.CandidateData]:
    """Gather everything scoring needs, for every active staff member not on the visit."""
    branch_id, tz = deps.branch.id, deps.branch.timezone
    week_start = visit.date - dt.timedelta(days=visit.date.weekday())
    week_end = week_start + dt.timedelta(days=6)
    persons = session.exec(
        select(Person).where(Person.branch_id == branch_id).where(Person.status == "active")
    ).all()
    week_visits = session.exec(
        select(Visit)
        .where(Visit.branch_id == branch_id)
        .where(col(Visit.date) >= week_start)
        .where(col(Visit.date) <= week_end)
        .where(Visit.status != "cancelled")
    ).all()
    past_here = session.exec(
        select(Visit)
        .where(Visit.location_id == visit.location_id)
        .where(Visit.status == "completed")
    ).all()
    result = []
    for p in persons:
        if "staff" not in p.roles or p.id in visit.assigned_person_ids:
            continue
        windows = {
            a.weekday: (dt.time.fromisoformat(a.start), dt.time.fromisoformat(a.end))
            for a in session.exec(
                select(StaffAvailability).where(StaffAvailability.person_id == p.id)
            )
        }
        limit = session.exec(select(WorkLimit).where(WorkLimit.person_id == p.id)).first()
        absences = session.exec(select(Absence).where(Absence.person_id == p.id)).all()
        result.append(
            scoring.CandidateData(
                person_id=p.id,
                name=p.name,
                skills=list(p.skills),
                windows=windows,
                max_daily_minutes=limit.max_daily_minutes if limit else 600,
                max_weekly_minutes=limit.max_weekly_minutes if limit else 2400,
                booked=[_slot(v, tz) for v in week_visits if p.id in v.assigned_person_ids],
                absent_dates={a.date for a in absences},
                site_visits=sum(1 for v in past_here if p.id in v.assigned_person_ids),
            )
        )
    return result


def find_replacements(
    deps: AgentDeps, args: FindReplacementsInput, tool_call_id: str
) -> FindReplacementsOutput:
    """Top three replacement candidates for a visit, with reasons. Read only."""
    _check(deps, Resource(kind="data", name="core.visit"), "read", tool_call_id)
    _check(deps, Resource(kind="data", name="core.person"), "read", tool_call_id)
    visit = resolve_visit(deps.session, deps, args)
    job = deps.session.get(Job, visit.job_id)
    ranked = scoring.rank_candidates(
        candidate_data(deps.session, deps, visit),
        _slot(visit, deps.branch.timezone),
        job.required_skills if job else [],
    )
    return FindReplacementsOutput(
        visit=visit_info(deps.session, visit, deps.branch.timezone),
        candidates=[
            Candidate(person_id=r.person_id, name=r.name, reasons=r.reasons) for r in ranked
        ],
        escalated=not ranked,
    )


# ---- propose_assignment -------------------------------------------------------------------


class ProposeAssignmentInput(BaseModel):
    visit_id: str
    candidate_id: str = Field(description="person_id of one of the find_replacements candidates")


class ProposeAssignmentOutput(BaseModel):
    approval_id: str
    status: str
    candidate: str
    visit: VisitInfo
    summary: str


def propose_assignment(
    deps: AgentDeps, args: ProposeAssignmentInput, tool_call_id: str
) -> ProposeAssignmentOutput:
    """Create an assignment_change approval. Does not change the visit."""
    visit = deps.session.get(Visit, args.visit_id)
    candidate = deps.session.get(Person, args.candidate_id)
    if visit is None or visit.branch_id != deps.branch.id:
        raise LookupError("visit not found")
    if candidate is None or candidate.branch_id != deps.branch.id:
        raise LookupError("candidate not found")
    pool = {c.person_id: c for c in candidate_data(deps.session, deps, visit)}
    data = pool.get(candidate.id)
    if data is None or not scoring.eligible(data, _slot(visit, deps.branch.timezone)):
        raise LookupError(f"{candidate.name} is not eligible for this visit")
    absent = {
        a.person_id for a in deps.session.exec(select(Absence).where(Absence.date == visit.date))
    }
    replace = [p for p in visit.assigned_person_ids if p in absent] or list(
        visit.assigned_person_ids
    )
    info = visit_info(deps.session, visit, deps.branch.timezone)
    replaced = ", ".join(_names(deps.session, replace)) or "-"
    summary = f"{candidate.name} replaces {replaced} at {info.location}, {info.date} {info.start}-{info.end}"
    approval = approvals.request(
        deps.session,
        APPROVAL_TYPE,
        ("visit", visit.id),
        summary,
        deps.actor,
        deps.manifest.roles.approvers["dispatcher.propose_assignment"],
        channel="app_only",
        evidence={
            "visit_id": visit.id,
            "candidate_id": candidate.id,
            "replace_person_ids": replace,
            "triggered_by": replace,
            "tool_call_id": tool_call_id,
        },
        tool_call_id=tool_call_id,
    )
    return ProposeAssignmentOutput(
        approval_id=approval.id,
        status=approval.status,
        candidate=candidate.name,
        visit=info,
        summary=summary,
    )


def apply_assignment(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: swap the replaced people for the candidate and emit visit.reassigned."""
    visit = session.get(Visit, approval.evidence["visit_id"])
    if visit is None:
        raise LookupError("visit no longer exists")
    replace = set(approval.evidence.get("replace_person_ids", []))
    candidate_id = approval.evidence["candidate_id"]
    keep = [p for p in visit.assigned_person_ids if p not in replace and p != candidate_id]
    store.update(
        session,
        visit,
        {"assigned_person_ids": [candidate_id, *keep]},
        decider,
        action="visit.reassigned",
        approval_id=approval.id,
    )


approvals.register_handler(APPROVAL_TYPE, apply_assignment)

BINDINGS = [
    ToolBinding(
        "dispatcher.get_my_visits",
        get_my_visits,
        GetMyVisitsInput,
        "List visits for the user (default: today and the next six days). "
        "Set person_name only when the user asks about someone else.",
    ),
    ToolBinding(
        "dispatcher.record_absence",
        record_absence,
        RecordAbsenceInput,
        "Record that the user is absent (sick, late, leaving early) on a date and "
        "return the visits it affects. Call again to change partial_day.",
    ),
    ToolBinding(
        "dispatcher.find_replacements",
        find_replacements,
        FindReplacementsInput,
        "Find the top three people who can cover a visit, with reasons. Give visit_id, "
        "or location_name with date and time.",
    ),
    ToolBinding(
        "dispatcher.propose_assignment",
        propose_assignment,
        ProposeAssignmentInput,
        "Propose assigning a candidate from find_replacements to a visit. Creates an "
        "approval; the visit does not change until a person approves it.",
    ),
]
