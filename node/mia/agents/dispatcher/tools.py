"""Dispatcher tools: typed inputs and outputs, permission checked data access, writes only
through mia.core services. Scheduling decisions live in scoring.py, not in the model."""

import datetime as dt
import re
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.dispatcher import cover, scoring
from mia.agents.dispatcher.models import Absence
from mia.core import scheduling, store
from mia.core.db import utcnow
from mia.core.models import Job, Location, Person, Visit
from mia.core.rbac import Resource, get_rbac

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
    """A visit as the model sees it, with times in the branch time zone."""
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
    """Visits in the branch between start and end (inclusive) assigned to the person, by start time."""
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

    @model_validator(mode="after")
    def late_means_morning(self) -> "RecordAbsenceInput":
        """Running late affects the morning (rule 7: code decides, not the model)."""
        if self.reason == "late" and self.partial_day is None:
            self.partial_day = "morning"
        return self


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


def _degrade(word: str) -> str:
    """Finnish consonant gradation: Kamppi, Kampissa; Tiitta, Tiitan. Doubled consonants
    collapse so an inflected site name still matches its nominative."""
    return re.sub(r"([bcdfghjklmnpqrstvwxz])\1", r"\1", word.lower())


def _location_matches(loc: Location, hint: str) -> bool:
    hint_low = _degrade(hint)
    return any(
        hint_low.startswith(word) or word.startswith(hint_low)
        for word in (_degrade(w) for w in loc.name.split())
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


def candidate_data(
    session: Session, deps: AgentDeps, visit: Visit, *, include_assigned: bool = False
) -> list[scoring.CandidateData]:
    """Gather everything scoring needs, for every active staff member not on the visit."""
    return scheduling.candidate_data(session, deps.branch, visit, include_assigned=include_assigned)


def _ranked(deps: AgentDeps, visit: Visit) -> list[scoring.Ranked]:
    job = deps.session.get(Job, visit.job_id)
    return scoring.rank_candidates(
        candidate_data(deps.session, deps, visit),
        scheduling.slot_of(deps.session, visit, deps.branch.timezone),
        job.required_skills if job else [],
    )


def find_replacements(
    deps: AgentDeps, args: FindReplacementsInput, tool_call_id: str
) -> FindReplacementsOutput:
    """Top three replacement candidates for a visit, with reasons. Read only."""
    _check(deps, Resource(kind="data", name="core.visit"), "read", tool_call_id)
    _check(deps, Resource(kind="data", name="core.person"), "read", tool_call_id)
    visit = resolve_visit(deps.session, deps, args)
    ranked = _ranked(deps, visit)
    return FindReplacementsOutput(
        visit=visit_info(deps.session, visit, deps.branch.timezone),
        candidates=[
            Candidate(person_id=r.person_id, name=r.name, reasons=r.reasons) for r in ranked
        ],
        escalated=not ranked,
    )


# ---- assign_cover -------------------------------------------------------------------------


class AssignCoverInput(BaseModel):
    visit_id: str
    candidate_id: str | None = Field(None, description="person_id from find_replacements")
    candidate_name: str | None = Field(
        None, description="Name, when the person is not one of the suggested candidates"
    )


class AssignCoverOutput(BaseModel):
    status: str  # asking, awaiting_approval
    stage: str
    candidate: str
    visit: VisitInfo
    approval_id: str | None = None
    next_action_at: dt.datetime | None = None
    note: str | None = None  # what the reply must tell the user (for the model, not shown as is)


def assign_cover(deps: AgentDeps, args: AssignCoverInput, tool_call_id: str) -> AssignCoverOutput:
    """Act on a person's explicit instruction to assign cover (the instruction is the approval).

    The visit does not change here: the candidate is asked to confirm first. When the choice
    breaks a hard rule, an override approval goes to admin or owner instead.
    """
    session = deps.session
    visit = session.get(Visit, args.visit_id)
    if visit is None or visit.branch_id != deps.branch.id:
        raise LookupError("visit not found")
    if args.candidate_id:
        person = session.get(Person, args.candidate_id)
        if person is None or person.branch_id != deps.branch.id:
            raise LookupError("candidate not found")
    elif args.candidate_name:
        person = find_person(session, deps.branch.id, args.candidate_name)
    else:
        raise LookupError("name the person to assign")
    pool = {c.person_id: c for c in candidate_data(session, deps, visit, include_assigned=True)}
    if person.id not in pool:
        raise LookupError(f"{person.name} is not on the cleaning staff")
    if person.id in visit.assigned_person_ids:
        raise LookupError(f"{person.name} is already on this visit")
    absent = {a.person_id for a in session.exec(select(Absence).where(Absence.date == visit.date))}
    replace = [p for p in visit.assigned_person_ids if p in absent] or list(
        visit.assigned_person_ids
    )
    queue = [r.person_id for r in _ranked(deps, visit) if r.person_id != person.id]
    request = cover.instruct(
        session,
        deps.actor,
        visit,
        scheduling.slot_of(session, visit, deps.branch.timezone),
        pool[person.id],
        queue,
        replace,
        utcnow(),
        tool_call_id=tool_call_id,
    )
    return AssignCoverOutput(
        status=request.status,
        stage=request.stage,
        candidate=person.name,
        visit=visit_info(session, visit, deps.branch.timezone),
        approval_id=request.approval_id,
        next_action_at=request.next_action_at,
        note=(
            f"{person.name} breaks a scheduling rule for this visit, so an admin or owner must "
            "approve first; tell the user that."
            if request.status == "awaiting_approval"
            else None
        ),
    )


# ---- respond_to_cover ---------------------------------------------------------------------


class RespondToCoverInput(BaseModel):
    accept: bool = Field(description="True when the user agrees to cover the visit")


class RespondToCoverOutput(BaseModel):
    accepted: bool
    visit: VisitInfo


def respond_to_cover(
    deps: AgentDeps, args: RespondToCoverInput, tool_call_id: str
) -> RespondToCoverOutput:
    """The user's answer to a cover request sent to them. Accepting changes the visit."""
    try:
        request = cover.respond(deps.session, deps.person, args.accept, deps.actor, utcnow())
    except cover.CoverError as exc:
        raise LookupError(str(exc)) from exc
    visit = deps.session.get(Visit, request.visit_id)
    if visit is None:
        raise LookupError("visit not found")
    return RespondToCoverOutput(
        accepted=args.accept, visit=visit_info(deps.session, visit, deps.branch.timezone)
    )


# ---- field work: check-in, check-out, visit details ---------------------------------------


class CheckInInput(BaseModel):
    location_name: str | None = Field(None, description="The site, when the user names it")


class CheckOutInput(BaseModel):
    location_name: str | None = Field(None, description="The site, when the user names it")


class VisitDetailsInput(BaseModel):
    location_name: str | None = Field(None, description="The site, when the user names it")


class AttendanceOutput(BaseModel):
    status: Literal["ok", "invalid"]
    reason: str | None = None  # no_visit, too_early, too_late, already, not_checked_in
    visit: VisitInfo | None = None
    time: str = ""


class VisitDetailsOutput(BaseModel):
    status: Literal["ok", "invalid"]
    reason: str | None = None
    visit: VisitInfo | None = None
    address: str = ""
    instructions: str = ""
    access_notes: str = ""
    checklist: list[str] = Field(default_factory=list)


def _own_visits_today(deps: AgentDeps, location_name: str | None) -> list[Visit]:
    """The acting person's visits around today (yesterday to tomorrow, so a visit that crosses
    midnight is still found), by start; narrowed to a named site."""
    day = dt.timedelta(days=1)
    rows = visits_for(
        deps.session, deps.branch.id, deps.person.id, deps.today - day, deps.today + day
    )
    if location_name:
        rows = [
            v
            for v in rows
            if (loc := deps.session.get(Location, v.location_id)) is not None
            and _location_matches(loc, location_name)
        ]
    return rows


def _reason(exc: scheduling.ScheduleError) -> str:
    text = str(exc)
    if "too early" in text:
        return "too_early"
    if "too late" in text:
        return "too_late"
    if "in_progress" in text or "completed" in text:
        return "already"
    return "no_visit"


def _local_time(when: dt.datetime, tz: str) -> str:
    return when.astimezone(ZoneInfo(tz)).strftime("%H:%M")


def check_in(deps: AgentDeps, args: CheckInInput, tool_call_id: str) -> AttendanceOutput:
    """Check the acting person in to their planned visit whose window holds now."""
    _check(
        deps,
        Resource(kind="data", name="core.visit", owner_id=deps.person.id),
        "write",
        tool_call_id,
    )
    now = utcnow()
    rows = _own_visits_today(deps, args.location_name)
    if any(v.status == "in_progress" for v in rows):
        return AttendanceOutput(status="invalid", reason="already")
    planned = [v for v in rows if v.status == "planned"]
    if not planned:
        return AttendanceOutput(status="invalid", reason="no_visit")
    open_now = [
        v
        for v in planned
        if v.planned_start - scheduling.CHECK_IN_EARLY
        <= now
        <= v.planned_end + scheduling.CHECK_IN_LATE
    ]
    if not open_now:
        nearest = min(planned, key=lambda v: abs((v.planned_start - now).total_seconds()))
        reason = "too_early" if now < nearest.planned_start else "too_late"
        return AttendanceOutput(status="invalid", reason=reason)
    visit = min(open_now, key=lambda v: abs((v.planned_start - now).total_seconds()))
    try:
        scheduling.check_in(deps.session, deps.actor, visit, deps.person, now)
    except scheduling.ScheduleError as exc:
        return AttendanceOutput(status="invalid", reason=_reason(exc))
    tz = deps.branch.timezone
    return AttendanceOutput(
        status="ok", visit=visit_info(deps.session, visit, tz), time=_local_time(now, tz)
    )


def check_out(deps: AgentDeps, args: CheckOutInput, tool_call_id: str) -> AttendanceOutput:
    """Check the acting person out of their visit in progress."""
    _check(
        deps,
        Resource(kind="data", name="core.visit", owner_id=deps.person.id),
        "write",
        tool_call_id,
    )
    now = utcnow()
    running = [v for v in _own_visits_today(deps, args.location_name) if v.status == "in_progress"]
    if not running:
        return AttendanceOutput(status="invalid", reason="not_checked_in")
    visit = running[0]
    try:
        scheduling.check_out(deps.session, deps.actor, visit, deps.person, now)
    except scheduling.ScheduleError as exc:
        return AttendanceOutput(status="invalid", reason=_reason(exc))
    tz = deps.branch.timezone
    return AttendanceOutput(
        status="ok", visit=visit_info(deps.session, visit, tz), time=_local_time(now, tz)
    )


def visit_details(
    deps: AgentDeps, args: VisitDetailsInput, tool_call_id: str
) -> VisitDetailsOutput:
    """Address, instructions, access notes and checklist of the acting person's current or
    next visit today (or of the named site's visit)."""
    _check(
        deps,
        Resource(kind="data", name="core.visit", owner_id=deps.person.id),
        "read",
        tool_call_id,
    )
    now = utcnow()
    rows = [v for v in _own_visits_today(deps, args.location_name) if v.status != "cancelled"]
    if not rows:
        return VisitDetailsOutput(status="invalid", reason="no_visit")
    current = [v for v in rows if v.status == "in_progress" or v.planned_end >= now]
    visit = current[0] if current else rows[-1]
    loc = deps.session.get(Location, visit.location_id)
    _check(deps, Resource(kind="data", name="core.location"), "read", tool_call_id)
    from mia.templates.cleaning.models import CleaningChecklist

    checklist = deps.session.exec(
        select(CleaningChecklist).where(CleaningChecklist.job_id == visit.job_id)
    ).first()
    items = [str(i.get("text", "")) for i in (checklist.items if checklist else [])]
    return VisitDetailsOutput(
        status="ok",
        visit=visit_info(deps.session, visit, deps.branch.timezone),
        address=loc.address if loc else "",
        instructions=loc.instructions if loc else "",
        access_notes=loc.access_notes if loc else "",
        checklist=items,
    )


# ---- site problems -----------------------------------------------------------------------


class ReportProblemInput(BaseModel):
    kind: Literal["cannot_access", "site_problem"] = Field(
        description="cannot_access: locked door, no key, wrong code, alarm; site_problem: the "
        "site is unusable (no water or power, renovation, client still there)"
    )
    text: str = Field(max_length=500, description="The user's own words")


class ProblemOutput(BaseModel):
    status: Literal["ok", "invalid"]
    reason: str | None = None
    visit: VisitInfo | None = None
    problem_id: str | None = None


def report_site_problem(
    deps: AgentDeps, args: ReportProblemInput, tool_call_id: str
) -> ProblemOutput:
    """Record a problem at the acting person's current (or next) visit today and tell the
    supervisors at once."""
    from mia.agents.dispatcher.alerts import supervisors
    from mia.agents.dispatcher.models import SiteProblem
    from mia.chat.blocks import TextBlock
    from mia.chat.channels import notify
    from mia.i18n import t

    _check(
        deps,
        Resource(kind="data", name="dispatcher_site_problems", owner_id=deps.person.id),
        "write",
        tool_call_id,
    )
    now = utcnow()
    rows = [v for v in _own_visits_today(deps, None) if v.status in ("planned", "in_progress")]
    current = [v for v in rows if v.status == "in_progress" or v.planned_end >= now]
    if not rows:
        return ProblemOutput(status="invalid", reason="no_visit")
    visit = current[0] if current else rows[-1]
    row = store.insert(
        deps.session,
        SiteProblem(
            branch_id=deps.branch.id,
            visit_id=visit.id,
            person_id=deps.person.id,
            kind=args.kind,
            text=args.text,
        ),
        deps.actor,
        action="site_problem.reported",
        tool_call_id=tool_call_id,
    )
    info = visit_info(deps.session, visit, deps.branch.timezone)
    for sup in supervisors(deps.session, deps.branch.id):
        text = t(
            f"alert.{args.kind}",
            sup.language,
            name=deps.person.name,
            location=info.location,
            text=args.text,
        )
        notify(deps.session, sup, [TextBlock(text=text)], deps.actor, deps.manifest.id, urgent=True)
    return ProblemOutput(status="ok", visit=info, problem_id=row.id)


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
        "dispatcher.assign_cover",
        assign_cover,
        AssignCoverInput,
        "Assign cover when the user explicitly tells you whom to assign. The person is asked "
        "to confirm before the visit changes. Never call this on your own initiative.",
    ),
    ToolBinding(
        "dispatcher.respond_to_cover",
        respond_to_cover,
        RespondToCoverInput,
        "Record the user's yes or no to a cover request Mia sent them.",
    ),
    ToolBinding(
        "dispatcher.check_in",
        check_in,
        CheckInInput,
        "The user says they arrived at a site: check them in to their visit that is due now.",
    ),
    ToolBinding(
        "dispatcher.check_out",
        check_out,
        CheckOutInput,
        "The user says they finished and are leaving: check them out of the visit in progress.",
    ),
    ToolBinding(
        "dispatcher.visit_details",
        visit_details,
        VisitDetailsInput,
        "Address, instructions, access notes and checklist of the user's current or next "
        "visit today (or of the site they name).",
    ),
    ToolBinding(
        "dispatcher.report_site_problem",
        report_site_problem,
        ReportProblemInput,
        "The user cannot get into the site, or the site is unusable: record it and tell the "
        "supervisors. Pass the user's own words as text.",
    ),
]
