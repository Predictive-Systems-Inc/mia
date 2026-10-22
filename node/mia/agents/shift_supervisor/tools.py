"""Shift supervisor tools: typed inputs and outputs, permission checked data access, writes only
through mia.core services. Scheduling decisions live in scoring.py, not in the model."""

import datetime as dt
import re
from collections.abc import Sequence
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.shift_supervisor import cover, scoring
from mia.agents.shift_supervisor import roster as patterns
from mia.agents.shift_supervisor import timesheets as sheets
from mia.agents.shift_supervisor.rules import fmt_date, is_retail
from mia.core import events, sales, scheduling, store
from mia.core.db import utcnow
from mia.core.models import (
    Absence,
    Branch,
    IncidentKind,
    Job,
    Location,
    Person,
    SalesSession,
    SupplierOrder,
    Timesheet,
    Visit,
)
from mia.core.rbac import Resource, get_rbac
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailBranchHours, RetailClosure

MORNING_ENDS = dt.time(12, 0)
LATE_NOTICE = "visit.late_notice"  # alerts.LATE reads it
LATE_HOLD_MAX = dt.timedelta(minutes=120)  # a late notice never holds the alert past this


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
    session: Session, branch_ids: Sequence[str], person_id: str, start: dt.date, end: dt.date
) -> list[Visit]:
    """Visits in the branches between start and end (inclusive) assigned to the person, by
    start time."""
    stmt = (
        select(Visit)
        .where(col(Visit.branch_id).in_(branch_ids))
        .where(col(Visit.date) >= start)
        .where(col(Visit.date) <= end)
        .order_by(col(Visit.planned_start))
    )
    return [v for v in session.exec(stmt) if person_id in v.assigned_person_ids]


def find_person(session: Session, branch_ids: Sequence[str], hint: str) -> Person:
    """Match a (possibly inflected) first name or full name in the branches. Raises LookupError."""
    hint_low = hint.lower().strip()
    persons = session.exec(select(Person).where(col(Person.branch_id).in_(branch_ids))).all()
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


def _branch_ids(deps: AgentDeps) -> list[str]:
    """Where the acting person's own shifts are looked up: every branch of the organisation in
    retail (a covering clerk's shift at the other kiosk, D39), else the person's branch."""
    if not is_retail():
        return [deps.branch.id]
    stmt = select(Branch.id).where(Branch.organisation_id == deps.branch.organisation_id)
    return list(deps.session.exec(stmt).all())


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
        target = find_person(deps.session, [deps.branch.id], args.person_name)
    resource = Resource(kind="data", name="core.visit", owner_id=target.id)
    _check(deps, resource, "read", tool_call_id)
    start = args.start or deps.today
    end = args.end or start + dt.timedelta(days=6)
    where = _branch_ids(deps) if target.id == deps.person.id else [deps.branch.id]
    visits = visits_for(deps.session, where, target.id, start, end)
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
    arrive_at: dt.time | None = Field(
        None, description="Retail late notice: the clock time the sender says they arrive"
    )

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
    late_visit: VisitInfo | None = None  # retail: the shift a late notice is for
    arrive_at: str | None = None  # retail: the expected arrival, "HH:MM" local


def _affected(visits: list[Visit], partial_day: str | None, tz: str) -> list[Visit]:
    if partial_day is None:
        return visits
    zone = ZoneInfo(tz)
    morning = [v for v in visits if v.planned_start.astimezone(zone).time() < MORNING_ENDS]
    return morning if partial_day == "morning" else [v for v in visits if v not in morning]


class PastDay(BaseModel):
    """A refusal for a day gone by (retail offers past days for a time correction only)."""

    status: Literal["invalid"] = "invalid"
    reason: Literal["past"] = "past"
    date: dt.date


def _late_visit(visits: list[Visit], now: dt.datetime) -> Visit | None:
    """The shift a late notice is for: the one in progress, else the planned one not yet over
    with the earliest start (the one whose start is nearest after now), whatever its hour."""
    running = [v for v in visits if v.status == "in_progress"]
    ahead = sorted(
        (v for v in visits if v.status == "planned" and v.planned_end > now),
        key=lambda v: v.planned_start,
    )
    return next(iter(running + ahead), None)


def _arrival(at: dt.time, visit: Visit, tz: str) -> str:
    """The stated arrival as "HH:MM": a 12-hour reading ("1:30" for a 13:00 shift) is the one
    of at and at + 12 h nearest the shift's start (rule 7: code reads the clock)."""
    start = visit.planned_start.astimezone(ZoneInfo(tz))
    options = [at, at.replace(hour=at.hour + 12)] if at.hour < 12 else [at]
    target = start.hour * 60 + start.minute
    best = min(options, key=lambda o: abs(o.hour * 60 + o.minute - target))
    return best.strftime("%H:%M")


def _tell_late(
    deps: AgentDeps,
    person: Person,
    info: VisitInfo,
    branch_id: str,
    arrive: str | None,
    far: bool,
) -> None:
    """Tell the kiosk's head staff (alerts.supervisors) of a late clerk once per notice, not
    urgent: the clerk, the shift and the expected arrival when given, said to be more than
    LATE_HOLD_MAX late when `far`. The reporter is never told of their own notice."""
    from mia.agents.shift_supervisor.alerts import supervisors
    from mia.chat.blocks import TextBlock
    from mia.chat.channels import notify
    from mia.i18n import t

    key = "retail.alert.late_far" if far else "retail.alert.late"
    key = key if arrive else "retail.alert.late_unknown"
    for sup in supervisors(deps.session, branch_id):
        if sup.id == deps.person.id:
            continue
        text = t(
            key,
            sup.language,
            name=person.name,
            start=info.start,
            location=info.location,
            date=fmt_date(info.date.isoformat(), sup.language),
            time=arrive or "",
        )
        notify(deps.session, sup, [TextBlock(text=text)], deps.actor, deps.manifest.id)


def record_absence(
    deps: AgentDeps, args: RecordAbsenceInput, tool_call_id: str
) -> RecordAbsenceOutput | PastDay:
    """Record (or update) an absence and return the visits it affects. Visits are not changed.
    In retail a day before today is refused (`past`): Jev may pick past days, for corrections."""
    person = deps.person
    if args.person_name:
        person = find_person(deps.session, [deps.branch.id], args.person_name)
    resource = Resource(kind="data", name="core.absence", owner_id=person.id)
    _check(deps, resource, "write", tool_call_id)
    if is_retail() and args.date < deps.today:
        return PastDay(date=args.date)
    tz = deps.branch.timezone
    day_visits = visits_for(deps.session, [deps.branch.id], person.id, args.date, args.date)
    late = _late_visit(day_visits, utcnow()) if is_retail() and args.reason == "late" else None
    partial_day = args.partial_day
    if late is not None:  # the half of the day the shift starts in, never "morning" by default
        morning = late.planned_start.astimezone(ZoneInfo(tz)).time() < MORNING_ENDS
        partial_day = "morning" if morning else "afternoon"
    existing = deps.session.exec(
        select(Absence).where(Absence.person_id == person.id).where(Absence.date == args.date)
    ).first()
    if existing:
        changes = {"reason": args.reason, "partial_day": partial_day}
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
                partial_day=partial_day,
                reported_by=deps.person.id,
            ),
            deps.actor,
            tool_call_id=tool_call_id,
        )
    if late is not None:
        info = visit_info(deps.session, late, tz)
        arrive = _arrival(args.arrive_at, late, tz) if args.arrive_at else None
        when = None
        if arrive:
            local = late.planned_start.astimezone(ZoneInfo(tz))
            hour, minute = map(int, arrive.split(":"))
            when = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        far = when is not None and when > late.planned_start + LATE_HOLD_MAX
        _tell_late(deps, person, info, late.branch_id, arrive, far)
        stated = when.isoformat() if when else None
        after = {"person_id": person.id, "absence_id": absence.id, "arrive_at": stated}
        events.emit(  # the hold on this shift's missed check-in alert (alerts.LATE)
            deps.session,
            LATE_NOTICE,
            ("visit", late.id),
            None,
            after,
            deps.actor,
            tool_call_id=tool_call_id,
        )
        return RecordAbsenceOutput(
            absence_id=absence.id,
            person=person.name,
            date=args.date,
            partial_day=partial_day,
            updated=existing is not None,
            affected_visits=[info],
            late_visit=info,
            arrive_at=arrive,
        )
    affected = _affected(day_visits, args.partial_day, tz)
    return RecordAbsenceOutput(
        absence_id=absence.id,
        person=person.name,
        date=args.date,
        partial_day=args.partial_day,
        updated=existing is not None,
        affected_visits=[visit_info(deps.session, v, tz) for v in affected],
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
    if _degrade(loc.name) == hint_low:  # the full name ("Mall kiosk": "Mall" is too short)
        return True
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


def _kiosks(session: Session, branch: Branch) -> set[str]:
    """Ids of the organisation's kiosks (branches with hours rows): cross-kiosk cover is kiosk
    staff only (D39, Q112), never the commissary's. Used only where org_wide is, which is
    retail only, so the cleaning organisation (no hours rows) is untouched."""
    return {b.id for b in retail_hours.shops(session, branch.organisation_id)}


def candidate_data(
    session: Session, deps: AgentDeps, visit: Visit, *, include_assigned: bool = False
) -> list[scoring.CandidateData]:
    """Gather everything scoring needs, for every active staff member not on the visit: the
    organisation's in retail (the cover across kiosks, D39), else the branch's."""
    return scheduling.candidate_data(
        session,
        deps.branch,
        visit,
        include_assigned=include_assigned,
        org_wide=is_retail(),
        among=_kiosks(session, deps.branch) if is_retail() else None,
    )


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
        if person is None or person.branch_id not in _branch_ids(deps):
            raise LookupError("candidate not found")
    elif args.candidate_name:
        person = find_person(session, _branch_ids(deps), args.candidate_name)
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
    opening_float: int | None = None  # check-in on a receipts kiosk: the drawer's float
    currency: str = ""


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
        deps.session, _branch_ids(deps), deps.person.id, deps.today - day, deps.today + day
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
    """Check the acting person in to their planned visit whose window holds now. A retail
    clerk (never head staff) on a receipts kiosk also gets her open sales session (the drawer,
    sales.open_for_shift), its write checked before the visit's so a denial writes nothing."""
    _check(
        deps,
        Resource(kind="data", name="core.visit", owner_id=deps.person.id),
        "write",
        tool_call_id,
    )
    drawer_due = (
        is_retail()
        and scheduling.is_staff(deps.person)
        and sales.source_of(deps.branch, deps.today) == "receipts"
    )
    if drawer_due:
        resource = Resource(kind="data", name=SalesSession.__tablename__, owner_id=deps.person.id)
        _check(deps, resource, "write", tool_call_id)
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
    out = AttendanceOutput(
        status="ok", visit=visit_info(deps.session, visit, tz), time=_local_time(now, tz)
    )
    if drawer_due:
        try:
            s = sales.open_for_shift(
                deps.session, deps.actor, deps.branch, deps.person.id, visit.id, now
            )
        except sales.SalesError as exc:  # ponytail: only "item" (a kiosk with no menu) is
            raise LookupError(str(exc)) from exc  # reachable; the visit stays checked in
        out.opening_float, out.currency = s.opening_float, s.currency
    return out


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
    if is_retail():  # a kiosk has no site details or checklist (Q109)
        return VisitDetailsOutput(status="invalid", reason="not_offered")
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
    kind: IncidentKind = Field(
        description="cannot_access: locked door, no key, wrong code, alarm; site_problem: the "
        "site is unusable (no water or power, renovation, client still there); equipment, "
        "no_delivery and customer are kiosk kinds, refused outside the retail template"
    )
    text: str = Field(max_length=500, description="The user's own words")
    location_name: str | None = Field(None, description="The site, when the user names it")


class ProblemOutput(BaseModel):
    status: Literal["ok", "invalid"]
    reason: str | None = None
    visit: VisitInfo | None = None
    problem_id: str | None = None
    location: str | None = None  # retail: the shift's kiosk, else the branch (no shift today)


def _current_visit(deps: AgentDeps, location_name: str | None, now: dt.datetime) -> Visit | None:
    """The acting person's visit in progress, else the current or next one today; a named
    site narrows it (the one choice shared with photos through scheduling.current_visit)."""
    location_id = None
    if location_name:
        rows = [v for v in _own_visits_today(deps, location_name) if v.date == deps.today]
        if not rows:
            return None
        location_id = rows[0].location_id
    found = [
        v
        for bid in _branch_ids(deps)
        if (branch := deps.session.get(Branch, bid)) is not None
        and (
            v := scheduling.current_visit(
                deps.session, branch, deps.person, now, location_id=location_id
            )
        )
    ]
    running = [v for v in found if v.status == "in_progress"]
    if running or not found:
        return running[0] if running else None
    return min(found, key=lambda v: abs((v.planned_start - now).total_seconds()))


CLEANING_KINDS = ("cannot_access", "site_problem")  # ADR 019: cleaning keeps its two kinds
RETAIL_KINDS = ("equipment", "no_delivery", "customer", "site_problem")


def open_order(session: Session, branch_id: str) -> tuple[str, dt.date] | None:
    """The branch's newest approved supplier order as (supplier, business date), else None. A
    system read like alerts.supervisors: it words head staff's alert, never the clerk's reply."""
    row = session.exec(
        select(SupplierOrder)
        .where(SupplierOrder.branch_id == branch_id)
        .where(SupplierOrder.status == "approved")
        .order_by(col(SupplierOrder.id).desc())
    ).first()
    return (row.supplier, row.business_date) if row else None


def _report_at_kiosk(
    deps: AgentDeps, args: ReportProblemInput, visit: Visit | None, tool_call_id: str
) -> ProblemOutput:
    """The retail report: the incident on the person's shift, else (head staff without one,
    Q107) on the kiosk's first open shift today; on a day with none (closed) no row is written
    and the message still goes. Head staff of the shift's kiosk and the owners and admins are
    told at once with retail.alert.<kind>; a missed delivery names the open order."""
    from mia.agents.shift_supervisor.alerts import leads, supervisors
    from mia.chat.blocks import TextBlock
    from mia.chat.channels import notify
    from mia.core.models import Incident
    from mia.i18n import t

    session = deps.session
    if visit is None:
        visit = session.exec(
            select(Visit)
            .where(Visit.branch_id == deps.branch.id)
            .where(Visit.date == deps.today)
            .where(col(Visit.status).in_(("planned", "in_progress")))
            .order_by(col(Visit.planned_start))
        ).first()
    branch_id = visit.branch_id if visit else deps.branch.id
    row = None
    info = None
    if visit is not None:
        incident = Incident(
            branch_id=visit.branch_id,
            visit_id=visit.id,
            person_id=deps.person.id,
            kind=args.kind,
            text=args.text,
        )
        row = store.insert(
            session, incident, deps.actor, action="site_problem.reported", tool_call_id=tool_call_id
        )
        info = visit_info(session, visit, deps.branch.timezone)
    location = info.location if info else deps.branch.name
    order = open_order(session, branch_id) if args.kind == "no_delivery" else None
    seen = {deps.person.id}  # the reporter is never paged about their own report
    for p in [*supervisors(session, branch_id), *leads(session, deps.branch.organisation_id)]:
        if p.id in seen:
            continue
        seen.add(p.id)
        extra: dict[str, object] = {}
        if args.kind == "no_delivery":
            extra["order"] = (
                t(
                    "retail.alert.order",
                    p.language,
                    supplier=order[0],
                    date=fmt_date(order[1].isoformat(), p.language),
                )
                if order
                else t("retail.alert.no_order", p.language)
            )
        text = t(
            f"retail.alert.{args.kind}",
            p.language,
            name=deps.person.name,
            location=location,
            text=args.text,
            **extra,
        )
        notify(session, p, [TextBlock(text=text)], deps.actor, deps.manifest.id, urgent=True)
    return ProblemOutput(
        status="ok", visit=info, problem_id=row.id if row else None, location=location
    )


def report_site_problem(
    deps: AgentDeps, args: ReportProblemInput, tool_call_id: str
) -> ProblemOutput:
    """Record a problem at the acting person's current (or next) visit today and tell the
    supervisors at once."""
    from mia.agents.shift_supervisor.alerts import supervisors
    from mia.chat.blocks import TextBlock
    from mia.chat.channels import notify
    from mia.core.models import Incident
    from mia.i18n import t

    _check(
        deps,
        Resource(kind="data", name="core.incident", owner_id=deps.person.id),
        "write",
        tool_call_id,
    )
    if args.kind not in (RETAIL_KINDS if is_retail() else CLEANING_KINDS):
        return ProblemOutput(status="invalid", reason="kind")
    now = utcnow()
    visit = _current_visit(deps, args.location_name, now)  # today only: never tomorrow's
    if is_retail():
        return _report_at_kiosk(deps, args, visit, tool_call_id)
    if visit is None:
        return ProblemOutput(status="invalid", reason="no_visit")
    row = store.insert(
        deps.session,
        Incident(
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
        if sup.id == deps.person.id:
            continue  # a supervisor reporting from their own visit is not paged about it
        text = t(
            f"alert.{args.kind}",
            sup.language,
            name=deps.person.name,
            location=info.location,
            text=args.text,
        )
        notify(deps.session, sup, [TextBlock(text=text)], deps.actor, deps.manifest.id, urgent=True)
    return ProblemOutput(status="ok", visit=info, problem_id=row.id)


# ---- checklist -----------------------------------------------------------------------------


class ChecklistInput(BaseModel):
    item: str | None = Field(
        None, max_length=200, description="An item to tick off, when the user says one is done"
    )
    location_name: str | None = Field(None, description="The site, when the user names it")


class ChecklistItem(BaseModel):
    text: str
    done: bool


class ChecklistOutput(BaseModel):
    status: Literal["ok", "invalid"]
    reason: str | None = None  # no_visit, no_checklist
    visit: VisitInfo | None = None
    items: list[ChecklistItem] = Field(default_factory=list)
    ticked: str | None = None  # the item just ticked
    unknown: str | None = None  # the item asked for that matched nothing


def checklist(deps: AgentDeps, args: ChecklistInput, tool_call_id: str) -> ChecklistOutput:
    """The current visit's checklist with its ticks; with `item`, tick that item (prefix match,
    case-insensitive). Ticking twice is a no-op; an unknown item is reported back."""
    from mia.templates.cleaning.models import CleaningChecklist, CleaningChecklistTick

    owner = Resource(kind="data", name="core.visit", owner_id=deps.person.id)
    _check(deps, owner, "read", tool_call_id)
    if is_retail():  # a kiosk has no checklist (Q109)
        return ChecklistOutput(status="invalid", reason="not_offered")
    now = utcnow()
    visit = _current_visit(deps, args.location_name, now)
    if visit is None:
        return ChecklistOutput(status="invalid", reason="no_visit")
    sheet = deps.session.exec(
        select(CleaningChecklist).where(CleaningChecklist.job_id == visit.job_id)
    ).first()
    texts = [str(i.get("text", "")) for i in (sheet.items if sheet else []) if i.get("text")]
    if not texts:
        return ChecklistOutput(
            status="invalid",
            reason="no_checklist",
            visit=visit_info(deps.session, visit, deps.branch.timezone),
        )
    ticks = deps.session.exec(
        select(CleaningChecklistTick).where(CleaningChecklistTick.visit_id == visit.id)
    ).all()
    done = {t_.item for t_ in ticks}
    ticked = unknown = None
    if args.item is not None:
        wanted = args.item.strip().lower()
        lowered = {t: t.lower() for t in texts}
        if len(wanted) < 2:  # nothing, or one letter: never a write
            matches: list[str] = []
        elif wanted in lowered.values():  # exact first, then prefix, then substring
            matches = [t for t, low in lowered.items() if low == wanted]
        else:
            matches = [
                t for t, low in lowered.items() if low.startswith(wanted) or wanted.startswith(low)
            ]
            if not matches:
                matches = [t for t, low in lowered.items() if wanted in low]
        if matches:
            ticked = min(matches, key=len)
            if ticked not in done:
                _check(
                    deps,
                    Resource(kind="data", name="cleaning_checklist_ticks", owner_id=deps.person.id),
                    "write",
                    tool_call_id,
                )
                store.insert(
                    deps.session,
                    CleaningChecklistTick(
                        branch_id=deps.branch.id,
                        visit_id=visit.id,
                        item=ticked,
                        ticked_by=deps.person.id,
                        ticked_at=now,
                    ),
                    deps.actor,
                    action="checklist.ticked",
                    tool_call_id=tool_call_id,
                )
                done.add(ticked)
        else:
            unknown = args.item
    return ChecklistOutput(
        status="ok",
        visit=visit_info(deps.session, visit, deps.branch.timezone),
        items=[ChecklistItem(text=t, done=t in done) for t in texts],
        ticked=ticked,
        unknown=unknown,
    )


# ---- retail: the roster, swaps, the time correction, closed days (D39) -------------------

JOBS = Resource(kind="data", name="core.job")
VISITS = Resource(kind="data", name="core.visit")
CLOSURES = Resource(kind="data", name=RetailClosure.__tablename__)
HOURS = Resource(kind="data", name=RetailBranchHours.__tablename__)
Weekday = Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _first(person: Person) -> str:
    return person.name.split()[0]


def _kiosk(
    deps: AgentDeps, location_name: str | None, resource: Resource, tool_call_id: str
) -> tuple[Branch, Location]:
    """The named kiosk (a location of the organisation's branches, matched as resolve_visit
    does) else the person's own, with its location; checks write on the resource, and
    write_all for another branch (owner and admin). Raises LookupError, PermissionDenied."""
    rows = deps.session.exec(
        select(Location, Branch)
        .join(Branch, col(Location.branch_id) == col(Branch.id))
        .where(Branch.organisation_id == deps.branch.organisation_id)
        .order_by(col(Location.id))
    ).all()
    if location_name:
        found = [(b, loc) for loc, b in rows if _location_matches(loc, location_name)]
    else:
        found = [(b, loc) for loc, b in rows if b.id == deps.branch.id]
    _check(deps, resource, "write", tool_call_id)  # before any lookup: no kiosk names leak
    if len({b.id for b, _ in found}) != 1:
        raise LookupError(f"no single kiosk matches {location_name or deps.branch.name!r}")
    branch, loc = found[0]
    if branch.id != deps.branch.id:
        _check(deps, resource, "write_all", tool_call_id)
    return branch, loc


# ---- set_roster ----------------------------------------------------------------------------


class ShiftIn(BaseModel):
    person_id: str
    byday: list[Weekday] = Field(min_length=1)
    start: dt.time
    end: dt.time

    @model_validator(mode="after")
    def ends_after_start(self) -> "ShiftIn":
        """A kiosk shift ends on the day it starts."""
        if self.end <= self.start:
            raise ValueError("the end must be after the start")
        return self


class SetRosterInput(BaseModel):
    shifts: list[ShiftIn] = Field(min_length=1, max_length=20)
    location_name: str | None = Field(None, description="The kiosk, when not the user's own")


class Clash(BaseModel):
    person: str
    dates: list[dt.date]
    reason: str


class RosterOut(BaseModel):
    status: Literal["ok", "invalid"]
    reason: str | None = None  # outside_hours
    jobs: list[str] = Field(default_factory=list)
    planned: int = 0
    clashes: list[Clash] = Field(default_factory=list)
    outside: list[str] = Field(default_factory=list)  # "Pao MO": a shift outside the hours


def _jobs_of(session: Session, location_id: str, person_id: str) -> list[Job]:
    """The person's running jobs at the location: no UNTIL, and their newest visit that is not
    cancelled has the person on it (what generation copies; a job name may repeat)."""
    out = []
    for job in session.exec(select(Job).where(Job.location_id == location_id)).all():
        if "UNTIL=" in job.recurrence:  # ponytail: set_roster only ever ends a job yesterday
            continue
        newest = session.exec(
            select(Visit)
            .where(Visit.job_id == job.id)
            .where(Visit.status != "cancelled")
            .order_by(col(Visit.date).desc())
        ).first()
        if newest is not None and person_id in newest.assigned_person_ids:
            out.append(job)
    return out


def _open_visits(session: Session, job: Job, since: dt.date) -> list[Visit]:
    return list(
        session.exec(
            select(Visit)
            .where(Visit.job_id == job.id)
            .where(col(Visit.date) >= since)
            .where(col(Visit.status).in_(scheduling.OPEN))
            .order_by(col(Visit.date))
        ).all()
    )


def _end_job(deps: AgentDeps, job: Job, tool_call_id: str) -> None:
    """End the job yesterday (;UNTIL=) and cancel its open visits from today."""
    until = (deps.today - dt.timedelta(days=1)).strftime("%Y%m%d")
    store.update(
        deps.session,
        job,
        {"recurrence": f"{job.recurrence};UNTIL={until}"},
        deps.actor,
        action="job.ended",
        tool_call_id=tool_call_id,
    )
    for v in _open_visits(deps.session, job, deps.today):
        store.update(deps.session, v, {"status": "cancelled"}, deps.actor, action="visit.cancelled")
        cover.cancel_open(deps.session, v.id, deps.actor)


def _upsert_jobs(
    deps: AgentDeps,
    branch: Branch,
    loc: Location,
    person: Person,
    shifts: list[ShiftIn],
    hours: retail_hours.Hours,
    tool_call_id: str,
) -> list[Job]:
    """The person's jobs for the shifts: an equal running job (days, start, length) is kept,
    a running job no shift asks for is ended, a missing one inserted (created today, local)."""
    wanted: dict[tuple[str, str, int], str] = {}
    for s in shifts:
        wd = scheduling.WEEKDAYS.index(s.byday[0])
        opens, closes = retail_hours.opens(hours, wd), retail_hours.closes(hours, wd)
        minutes = (s.end.hour * 60 + s.end.minute) - (s.start.hour * 60 + s.start.minute)
        key = (patterns.rrule(s.byday), s.start.strftime("%H:%M"), minutes)
        wanted[key] = patterns.job_name(s.start, s.end, s.byday, opens, closes, _first(person))
    out = []
    for job in _jobs_of(deps.session, loc.id, person.id):
        if wanted.pop((job.recurrence, job.start_time, job.duration_minutes), None) is not None:
            out.append(job)
        else:
            _end_job(deps, job, tool_call_id)
    zone = ZoneInfo(branch.timezone)
    for (rule, start, minutes), name in wanted.items():
        job = Job(
            branch_id=branch.id,
            location_id=loc.id,
            name=name,
            recurrence=rule,
            start_time=start,
            duration_minutes=minutes,
            created_at=dt.datetime.combine(deps.today, dt.time(0, 0), zone),
        )
        out.append(store.insert(deps.session, job, deps.actor, tool_call_id=tool_call_id))
    return out


def set_roster(deps: AgentDeps, args: SetRosterInput, tool_call_id: str) -> RosterOut:
    """The kiosk's weekly pattern from head staff. A shift outside the branch's hours refuses
    the whole input (`outside_hours`, nothing written). Else each person's jobs are kept, ended
    or inserted, visits generated, and each open visit of those jobs from today gets its person
    when scheduling finds no reason against it; a reason is a Clash and the visit stays
    unfilled (never an approval); a closed date is left unassigned for enforce_closures. Another
    kiosk needs write_all on jobs. Not offered outside retail (nothing read or written)."""
    if not is_retail():
        return RosterOut(status="invalid", reason="not_offered")
    session = deps.session
    branch, loc = _kiosk(deps, args.location_name, JOBS, tool_call_id)
    _check(deps, VISITS, "write", tool_call_id)
    _check(deps, HOURS, "read", tool_call_id)
    hours = retail_hours.load(session, branch.id)
    people: dict[str, Person] = {}
    for s in args.shifts:
        p = session.get(Person, s.person_id)
        if p is None or p.branch_id != branch.id or not scheduling.is_staff(p):
            raise LookupError("only the kiosk's clerks take shifts")
        people[p.id] = p
    outside = [
        f"{_first(people[s.person_id])} {code}"
        for s in args.shifts
        for code in patterns.outside_hours(
            patterns.Clause(s.person_id, list(s.byday), s.start, s.end), hours
        )
    ]
    if outside:
        return RosterOut(status="invalid", reason="outside_hours", outside=outside)
    jobs = {
        pid: _upsert_jobs(
            deps,
            branch,
            loc,
            p,
            [s for s in args.shifts if s.person_id == pid],
            hours,
            tool_call_id,
        )
        for pid, p in people.items()
    }
    scheduling.generate(session, deps.actor, branch, today=deps.today)
    planned, clashes, closed = (
        0,
        dict[tuple[str, str], list[dt.date]](),
        retail_hours.closed(session, branch.id),
    )
    kiosks = _kiosks(session, branch)
    for pid, rows in jobs.items():
        person = people[pid]
        for v in (v for job in rows for v in _open_visits(session, job, deps.today)):
            if pid in v.assigned_person_ids or v.date in closed:
                continue
            reasons = scheduling.ineligibility(
                session, branch, v, person, org_wide=True, among=kiosks
            )
            for r in reasons:
                clashes.setdefault((person.name, r), []).append(v.date)
            if not reasons:
                scheduling.assign(session, deps.actor, v, person, org_wide=True, among=kiosks)
                planned += 1
    return RosterOut(
        status="ok",
        jobs=[j.name for rows in jobs.values() for j in rows],
        planned=planned,
        clashes=[Clash(person=n, dates=d, reason=r) for (n, r), d in clashes.items()],
    )


# ---- roster (the week) ---------------------------------------------------------------------


class RosterInput(BaseModel):
    start: dt.date | None = Field(None, description="A day of the week asked about, default today")
    person_name: str | None = Field(None, description="Only when head staff ask about one person")


class WeekOut(BaseModel):
    start: dt.date
    people: dict[str, list[VisitInfo]]
    status: Literal["ok", "invalid"] = "ok"
    reason: str | None = None  # not_offered


def roster(deps: AgentDeps, args: RosterInput, tool_call_id: str) -> WeekOut:
    """Monday to Sunday of the week holding `start` (default today, the branch's local date) by
    first name: head staff the branch's shifts (or one person's), a clerk only her own (at
    either kiosk, so a covering clerk sees that one shift, never the other kiosk's roster).
    Cancelled shifts are left out. Not offered outside retail (nothing read)."""
    if not is_retail():
        return WeekOut(start=deps.today, people={}, status="invalid", reason="not_offered")
    session = deps.session
    day = args.start or deps.today
    monday = day - dt.timedelta(days=day.weekday())
    sunday = monday + dt.timedelta(days=6)
    only: set[str] | None
    if args.person_name:
        target = find_person(session, [deps.branch.id], args.person_name)
        _check(
            deps, Resource(kind="data", name="core.visit", owner_id=target.id), "read", tool_call_id
        )
        where = _branch_ids(deps) if target.id == deps.person.id else [deps.branch.id]
        rows, only = visits_for(session, where, target.id, monday, sunday), {target.id}
    elif get_rbac().check(deps.actor, VISITS, "read", session=session, tool_call_id=tool_call_id):
        rows, only = scheduling.week(session, deps.branch.id, monday), None
    else:
        own = Resource(kind="data", name="core.visit", owner_id=deps.person.id)
        _check(deps, own, "read", tool_call_id)
        rows = visits_for(session, _branch_ids(deps), deps.person.id, monday, sunday)
        only = {deps.person.id}
    people: dict[str, list[VisitInfo]] = {}
    for v in rows:
        if v.status == "cancelled":
            continue
        for pid in v.assigned_person_ids:
            if (only is None or pid in only) and (p := session.get(Person, pid)) is not None:
                people.setdefault(_first(p), []).append(
                    visit_info(session, v, deps.branch.timezone)
                )
    return WeekOut(start=monday, people=people)


# ---- swap_shifts ---------------------------------------------------------------------------


class SwapShiftsInput(BaseModel):
    person_name: str | None = Field(None, description="The co-worker to swap with")
    date: dt.date | None = Field(None, description="The day of both shifts")
    accept: bool | None = Field(None, description="The user's yes or no to a swap asked of them")


class SwapOut(BaseModel):
    status: Literal["asked", "confirming", "override", "declined", "invalid"]
    reason: str | None = None
    approval_id: str | None = None
    date: dt.date | None = None
    other: str | None = None


def _planned_shift(deps: AgentDeps, person: Person, day: dt.date) -> Visit | None:
    rows = visits_for(deps.session, [deps.branch.id], person.id, day, day)
    return next((v for v in rows if v.status == "planned"), None)


def swap_shifts(deps: AgentDeps, args: SwapShiftsInput, tool_call_id: str) -> SwapOut:
    """A swap of two clerks' planned shifts on one day of the branch. With person_name and
    date: the ask (cover.ask_swap); the co-worker's shift is read by the swap itself and only
    its day and name come back. With accept: the answer to the newest ask of the user
    (cover.answer_swap): no tells the asker, yes asks head staff to confirm (`confirming`), or
    the owner when a rule breaks (`override`). Nothing changes until it is approved. Not
    offered outside retail (nothing read or written)."""
    if not is_retail():
        return SwapOut(status="invalid", reason="not_offered")
    session = deps.session
    _check(
        deps,
        Resource(kind="data", name="core.visit", owner_id=deps.person.id),
        "write",
        tool_call_id,
    )
    if args.accept is not None:
        try:
            approval = cover.answer_swap(
                session, deps.person, args.accept, deps.actor, utcnow(), tool_call_id=tool_call_id
            )
        except cover.CoverError as exc:
            return SwapOut(status="invalid", reason=str(exc))
        if approval is None:
            return SwapOut(status="declined")
        mine = session.get(Visit, str(approval.evidence["mine"]))
        asker = session.get(Person, str(approval.evidence["asker_id"]))
        return SwapOut(
            status="override" if approval.type == cover.SWAP_OVERRIDE_TYPE else "confirming",
            approval_id=approval.id,
            date=mine.date if mine else None,
            other=asker.name if asker else None,
        )
    if not args.person_name or args.date is None:
        return SwapOut(status="invalid", reason="need_person_and_date")
    if args.date < deps.today:
        return SwapOut(status="invalid", reason="past", date=args.date)
    other = find_person(session, [deps.branch.id], args.person_name)
    if other.id == deps.person.id or not scheduling.is_staff(other):
        return SwapOut(status="invalid", reason="not_a_clerk", other=other.name)
    mine, theirs = (
        _planned_shift(deps, deps.person, args.date),
        _planned_shift(deps, other, args.date),
    )
    if mine is None or theirs is None or mine.id == theirs.id:
        reason = (
            "no_shift" if mine is None else "no_their_shift" if theirs is None else "same_shift"
        )
        return SwapOut(status="invalid", reason=reason, date=args.date, other=other.name)
    cover.ask_swap(session, deps.actor, mine, theirs, deps.person, other, tool_call_id=tool_call_id)
    return SwapOut(status="asked", date=args.date, other=other.name)


# ---- correct_timesheet ---------------------------------------------------------------------


class CorrectTimesheetInput(BaseModel):
    date: dt.date | None = Field(None, description="The day worked, default today")
    start: dt.time | None = Field(None, description="The real start, when it changes")
    end: dt.time | None = Field(None, description="The real end, when it changes")
    person_name: str | None = Field(None, description="Only when head staff correct someone else")
    note: str = Field("", max_length=500)


class TimesheetOut(BaseModel):
    status: Literal["ok", "invalid"]
    # no_time, no_timesheet, in_progress, approved, end_before_start, not_offered
    reason: str | None = None
    date: dt.date | None = None
    start: str | None = None
    end: str | None = None
    minutes: int | None = None


def _sheet(
    deps: AgentDeps, person: Person, day: dt.date, end: dt.time | None, tool_call_id: str
) -> Timesheet | Literal["in_progress", "end_before_start"] | None:
    """The person's timesheet of the day; a shift still in progress is checked out at the
    stated `end` and drafted first, a finished one without a draft drafted. Nothing changes
    for a running shift without an end or with an end after now ("in_progress": she is still
    on it), or with an end before her check-in ("end_before_start")."""
    session = deps.session
    stmt = select(Timesheet).where(Timesheet.person_id == person.id).where(Timesheet.date == day)
    if (row := session.exec(stmt).first()) is not None:
        return row
    where = _branch_ids(deps) if person.id == deps.person.id else [deps.branch.id]
    for v in visits_for(session, where, person.id, day, day):
        if v.status == "in_progress":
            if end is None:
                return "in_progress"  # a start alone never checks her out
            until = dt.datetime.combine(day, end, ZoneInfo(deps.branch.timezone))
            if until > utcnow():
                return "in_progress"  # never a check-out in the future
            if v.actual_start is not None and until < v.actual_start:
                return "end_before_start"
            _check(
                deps,
                Resource(kind="data", name="core.visit", owner_id=person.id),
                "write",
                tool_call_id,
            )
            scheduling.check_out(session, deps.actor, v, person, until)
        if v.status == "completed":
            sheets.draft(session, v)
    return session.exec(stmt).first()  # ponytail: one kiosk shift per clerk and day


def correct_timesheet(
    deps: AgentDeps, args: CorrectTimesheetInput, tool_call_id: str
) -> TimesheetOut:
    """Set the start or end of a day's time (timesheets.correct): the row goes back to draft
    with the correcting person as its enterer, so they never approve it. A clerk corrects only
    her own draft; an approved row needs head staff (`approved`). Not offered outside retail
    (nothing read or written)."""
    if not is_retail():
        return TimesheetOut(status="invalid", reason="not_offered")
    session = deps.session
    person = deps.person
    if args.person_name:
        person = find_person(session, [deps.branch.id], args.person_name)
    _check(
        deps,
        Resource(kind="data", name="core.timesheet", owner_id=person.id),
        "write",
        tool_call_id,
    )
    day = args.date or deps.today
    if args.start is None and args.end is None:
        return TimesheetOut(status="invalid", reason="no_time", date=day)
    row = _sheet(deps, person, day, args.end, tool_call_id)
    if row is None or isinstance(row, str):
        return TimesheetOut(status="invalid", reason=row or "no_timesheet", date=day)
    zone = ZoneInfo(deps.branch.timezone)
    start = dt.datetime.combine(day, args.start, zone) if args.start else row.start
    end = dt.datetime.combine(day, args.end, zone) if args.end else row.end
    try:
        row = sheets.correct(session, deps.actor, row, start, end, args.note)
    except sheets.AlreadyApproved:
        return TimesheetOut(status="invalid", reason="approved", date=day)
    except sheets.TimesheetError:
        return TimesheetOut(status="invalid", reason="end_before_start", date=day)
    tz = deps.branch.timezone
    return TimesheetOut(
        status="ok",
        date=day,
        start=_local_time(row.start, tz),
        end=_local_time(row.end, tz),
        minutes=row.minutes,
    )


# ---- close_day -----------------------------------------------------------------------------


class CloseDayInput(BaseModel):
    date: dt.date
    location_name: str | None = Field(None, description="The kiosk, when not the user's own")
    reason: str = Field("", max_length=200)


class CloseDayOut(BaseModel):
    status: Literal["ok", "invalid"]
    reason: str | None = None  # past, already
    branch: str = ""
    date: dt.date | None = None
    cancelled: int = 0


def close_day(deps: AgentDeps, args: CloseDayInput, tool_call_id: str) -> CloseDayOut:
    """Close the kiosk on a date from today on: the closure row (`retail.closure_set`), the
    day's open shifts cancelled with their open cover asks, each clerk on them told. Another
    kiosk needs write_all on closures; a past or already closed date is invalid. Not offered
    outside retail (nothing read or written)."""
    if not is_retail():
        return CloseDayOut(status="invalid", reason="not_offered")
    from mia.chat.blocks import TextBlock
    from mia.chat.channels import notify
    from mia.i18n import t

    session = deps.session
    branch, _ = _kiosk(deps, args.location_name, CLOSURES, tool_call_id)
    _check(deps, VISITS, "write", tool_call_id)
    if args.date < deps.today:
        return CloseDayOut(status="invalid", reason="past", branch=branch.name, date=args.date)
    if args.date in retail_hours.closed(session, branch.id):
        return CloseDayOut(status="invalid", reason="already", branch=branch.name, date=args.date)
    closure = RetailClosure(
        branch_id=branch.id, date=args.date, reason=args.reason, set_by=deps.person.id
    )
    store.insert(
        session, closure, deps.actor, action="retail.closure_set", tool_call_id=tool_call_id
    )
    cancelled = scheduling.cancel_day(session, deps.actor, branch.id, args.date)
    told: set[str] = set()
    for v in cancelled:
        cover.cancel_open(session, v.id, deps.actor)
        for pid in v.assigned_person_ids:
            if pid in told or (p := session.get(Person, pid)) is None:
                continue
            told.add(pid)
            day = fmt_date(args.date.isoformat(), p.language)
            text = t("shift.closed.told", p.language, location=branch.name, date=day)
            notify(session, p, [TextBlock(text=text)], deps.actor, deps.manifest.id)
    return CloseDayOut(status="ok", branch=branch.name, date=args.date, cancelled=len(cancelled))


BINDINGS = [
    ToolBinding(
        "shift_supervisor.get_my_visits",
        get_my_visits,
        GetMyVisitsInput,
        "List visits for the user (default: today and the next six days). "
        "Set person_name only when the user asks about someone else.",
    ),
    ToolBinding(
        "shift_supervisor.record_absence",
        record_absence,
        RecordAbsenceInput,
        "Record that the user is absent (sick, late, leaving early) on a date and "
        "return the visits it affects. Call again to change partial_day.",
    ),
    ToolBinding(
        "shift_supervisor.find_replacements",
        find_replacements,
        FindReplacementsInput,
        "Find the top three people who can cover a visit, with reasons. Give visit_id, "
        "or location_name with date and time.",
    ),
    ToolBinding(
        "shift_supervisor.assign_cover",
        assign_cover,
        AssignCoverInput,
        "Assign cover when the user explicitly tells you whom to assign. The person is asked "
        "to confirm before the visit changes. Never call this on your own initiative.",
    ),
    ToolBinding(
        "shift_supervisor.respond_to_cover",
        respond_to_cover,
        RespondToCoverInput,
        "Record the user's yes or no to a cover request Mia sent them.",
    ),
    ToolBinding(
        "shift_supervisor.check_in",
        check_in,
        CheckInInput,
        "The user says they arrived at a site: check them in to their visit that is due now.",
    ),
    ToolBinding(
        "shift_supervisor.check_out",
        check_out,
        CheckOutInput,
        "The user says they finished and are leaving: check them out of the visit in progress.",
    ),
    ToolBinding(
        "shift_supervisor.visit_details",
        visit_details,
        VisitDetailsInput,
        "Address, instructions, access notes and checklist of the user's current or next "
        "visit today (or of the site they name).",
    ),
    ToolBinding(
        "shift_supervisor.report_site_problem",
        report_site_problem,
        ReportProblemInput,
        "The user cannot get into the site, or the site is unusable: record it and tell the "
        "supervisors. Pass the user's own words as text.",
    ),
    ToolBinding(
        "shift_supervisor.checklist",
        checklist,
        ChecklistInput,
        "The checklist of the user's current visit; give item when the user says one is done.",
    ),
    ToolBinding(
        "shift_supervisor.set_roster",
        set_roster,
        SetRosterInput,
        "Head staff set the kiosk's weekly pattern: one shift per person, days and times.",
    ),
    ToolBinding(
        "shift_supervisor.roster",
        roster,
        RosterInput,
        "The week's shifts: the user's own, or the branch's for head staff.",
    ),
    ToolBinding(
        "shift_supervisor.swap_shifts",
        swap_shifts,
        SwapShiftsInput,
        "Ask a co-worker to swap shifts on a day (person_name and date), or answer a swap "
        "asked of the user (accept). Head staff confirm before anything changes.",
    ),
    ToolBinding(
        "shift_supervisor.correct_timesheet",
        correct_timesheet,
        CorrectTimesheetInput,
        "Correct the start or end time the user (or, for head staff, a clerk) worked on a day.",
    ),
    ToolBinding(
        "shift_supervisor.close_day",
        close_day,
        CloseDayInput,
        "Head staff close the kiosk on a date (a holiday): its shifts are cancelled and the "
        "clerks told.",
    ),
]
