"""Scheduling core (plan item 4, Sprint 2): recurrence rules, visit generation, eligibility,
assignment, check-in and check-out, the week view and the approvals inbox.

Guarantees: scheduling decisions are code (rule 7); every write goes through store and emits
an event; one visit per (job, date); a rule-breaking assignment needs an approval
(`schedule.assignment_override`, admin or owner, app only) and the visit does not change
until it is approved.
"""

import datetime as dt
import logging
from collections.abc import Collection
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.shift_supervisor import scoring
from mia.core import approvals, events, store
from mia.core.db import utcnow  # bound here, so the tests' clock pins never reach it
from mia.core.models import (
    Actor,
    Approval,
    Availability,
    Branch,
    Job,
    Location,
    Person,
    Visit,
    WorkLimit,
)

log = logging.getLogger(__name__)
WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
HORIZON_DAYS = 28
OVERRIDE_TYPE = "schedule.assignment_override"
OVERRIDE_ROLES = ["admin", "owner"]
CHECK_IN_EARLY = dt.timedelta(hours=2)
CHECK_IN_LATE = dt.timedelta(hours=4)
OPEN = ("planned", "unfilled")


class ScheduleError(RuntimeError):
    """A refused scheduling operation; the message is the reason."""


# ---- recurrence (pure) -------------------------------------------------------------------


def _parts(rule: str) -> dict[str, str]:
    try:
        parts = dict(p.split("=", 1) for p in rule.split(";") if p)
    except ValueError as exc:
        raise ValueError(f"unsupported recurrence {rule!r}") from exc
    freq = parts.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        raise ValueError(f"unsupported recurrence {rule!r}")
    if freq == "WEEKLY" and not parts.get("BYDAY"):
        raise ValueError(f"weekly recurrence needs BYDAY: {rule!r}")
    if any(d not in WEEKDAYS for d in parts.get("BYDAY", "MO").split(",")):
        raise ValueError(f"unknown weekday in {rule!r}")
    if int(parts.get("INTERVAL", "1")) < 1:
        raise ValueError(f"INTERVAL must be positive: {rule!r}")
    if "UNTIL" in parts:
        _until(parts)
    unknown = set(parts) - {"FREQ", "BYDAY", "INTERVAL", "UNTIL"}
    if unknown:
        raise ValueError(f"unsupported recurrence part {min(unknown)} in {rule!r}")
    return parts


def _until(parts: dict[str, str]) -> dt.date:
    u = parts["UNTIL"][:8]
    try:
        return dt.date(int(u[:4]), int(u[4:6]), int(u[6:8]))
    except ValueError as exc:
        raise ValueError(f"UNTIL must be YYYYMMDD: {parts['UNTIL']!r}") from exc


def validate_rule(rule: str) -> None:
    """Raise ValueError unless the rule is FREQ=DAILY or FREQ=WEEKLY;BYDAY=.. with an optional
    INTERVAL and UNTIL."""
    _parts(rule)


def _monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def occurs_on(rule: str, anchor: dt.date, day: dt.date) -> bool:
    """True when the rule has an occurrence on `day`. INTERVAL counts days (DAILY) or weeks
    (WEEKLY) from `anchor` (the job's creation date, local)."""
    parts = _parts(rule)
    if day < anchor:
        return False
    if "UNTIL" in parts and day > _until(parts):
        return False
    interval = int(parts.get("INTERVAL", "1"))
    if parts["FREQ"] == "DAILY":
        return (day - anchor).days % interval == 0
    days = parts["BYDAY"].split(",")
    if WEEKDAYS[day.weekday()] not in days:
        return False
    first = anchor  # the first occurrence on or after the anchor starts the week count
    while WEEKDAYS[first.weekday()] not in days:
        first += dt.timedelta(days=1)
    return ((_monday(day) - _monday(first)).days // 7) % interval == 0


def local_dt(day: dt.date, hhmm: str, tz: str) -> dt.datetime:
    """A local wall-clock time on a day, in the branch time zone."""
    hour, minute = map(int, hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=ZoneInfo(tz))


# ---- eligibility -------------------------------------------------------------------------


def is_staff(person: Person) -> bool:
    """True when one of the person's roles is staff or inherits staff (a retail clerk) without
    being or inheriting supervisor: field staff are cover candidates, head staff never."""
    from mia.core.rbac import get_rbac

    enforcer = get_rbac().enforcer
    for role in person.roles:
        graph = {role, *enforcer.get_implicit_roles_for_user(role, "*")}
        if "staff" in graph and "supervisor" not in graph:
            return True
    return False


def slot_of(session: Session, visit: Visit, tz: str) -> scoring.Slot:
    """The visit as a local-time slot with the site's coordinates when known."""
    zone = ZoneInfo(tz)
    loc = session.get(Location, visit.location_id)
    where = (loc.lat, loc.lon) if loc and loc.lat is not None and loc.lon is not None else None
    return scoring.Slot(
        visit.planned_start.astimezone(zone), visit.planned_end.astimezone(zone), where
    )


def candidate_data(
    session: Session,
    branch: Branch,
    visit: Visit,
    *,
    include_assigned: bool = False,
    only: set[str] | None = None,
    org_wide: bool = False,
    among: Collection[str] | None = None,
) -> list[scoring.CandidateData]:
    """Everything scoring needs for the active staff of the branch (or `only` those ids):
    availability windows, hour limits, this week's other bookings, absences and approved leave
    days, site history. With `org_wide` (the retail cover, D39) the staff and their bookings
    come from every branch of the branch's organisation (only those in `among` when given, the
    retail kiosks), never another organisation's."""
    from mia.core.models import Absence, Leave

    branches = (
        session.exec(select(Branch).where(Branch.organisation_id == branch.organisation_id)).all()
        if org_wide
        else [branch]
    )
    if among is not None:
        branches = [b for b in branches if b.id in among or b.id == branch.id]
    zones = {b.id: b.timezone for b in branches}
    week_start = _monday(visit.date)
    week_end = week_start + dt.timedelta(days=6)
    persons = session.exec(
        select(Person).where(col(Person.branch_id).in_(zones)).where(Person.status == "active")
    ).all()
    week_visits = [
        v
        for v in session.exec(
            select(Visit)
            .where(col(Visit.branch_id).in_(zones))
            .where(col(Visit.date) >= week_start)
            .where(col(Visit.date) <= week_end)
            .where(Visit.status != "cancelled")
        ).all()
        if v.id != visit.id
    ]
    slots = {v.id: slot_of(session, v, zones[v.branch_id]) for v in week_visits}
    past_here = session.exec(
        select(Visit)
        .where(Visit.location_id == visit.location_id)
        .where(Visit.status == "completed")
    ).all()
    result = []
    for p in persons:
        if not is_staff(p) or (only is not None and p.id not in only):
            continue
        if p.id in visit.assigned_person_ids and not include_assigned:
            continue
        windows = {
            a.weekday: (dt.time.fromisoformat(a.start), dt.time.fromisoformat(a.end))
            for a in session.exec(select(Availability).where(Availability.person_id == p.id))
        }
        limit = session.exec(select(WorkLimit).where(WorkLimit.person_id == p.id)).first()
        absent = {a.date for a in session.exec(select(Absence).where(Absence.person_id == p.id))}
        for leave in session.exec(
            select(Leave).where(Leave.person_id == p.id).where(Leave.status == "approved")
        ):
            span = (leave.end_date - leave.start_date).days + 1
            absent |= {leave.start_date + dt.timedelta(days=n) for n in range(span)}
        home = (
            (p.home_lat, p.home_lon) if p.home_lat is not None and p.home_lon is not None else None
        )
        result.append(
            scoring.CandidateData(
                person_id=p.id,
                name=p.name,
                skills=list(p.skills),
                windows=windows,
                max_daily_minutes=limit.max_daily_minutes if limit else 600,
                max_weekly_minutes=limit.max_weekly_minutes if limit else 2400,
                booked=[slots[v.id] for v in week_visits if p.id in v.assigned_person_ids],
                absent_dates=absent,
                site_visits=sum(1 for v in past_here if p.id in v.assigned_person_ids),
                home=home,
            )
        )
    return result


def ineligibility(
    session: Session,
    branch: Branch,
    visit: Visit,
    person: Person,
    *,
    org_wide: bool = False,
    among: Collection[str] | None = None,
) -> list[str]:
    """Why the person may not take the visit (empty when they may): the shift supervisor's reasons
    plus missing skills. An inactive or non-staff person gets one reason, and so does a person
    of a branch outside `among` ("not kiosk staff"). `org_wide` as in candidate_data (the retail
    cover, D39)."""
    if person.status != "active":
        return ["person is not active"]
    if not is_staff(person):
        return ["not a staff member"]
    job = session.get(Job, visit.job_id)
    data = candidate_data(
        session,
        branch,
        visit,
        include_assigned=True,
        only={person.id},
        org_wide=org_wide,
        among=among,
    )
    if not data:  # read only the `among` branches (and this one): a person outside them
        outside = among is not None and person.branch_id not in {*among, branch.id}
        return ["not kiosk staff" if outside else "person is not active"]
    reasons = list(scoring.ineligibility(data[0], slot_of(session, visit, branch.timezone)))
    missing = sorted(set(job.required_skills if job else []) - set(person.skills))
    if missing:
        reasons.append("missing skills: " + ", ".join(missing))
    return reasons


# ---- generation ------------------------------------------------------------------------


def _last_assignees(session: Session, job: Job, day: dt.date) -> list[str]:
    """Who did this job most recently on the same weekday (the copied assignment, Q21); the
    most recent visit of any weekday when there was none."""
    rows = session.exec(
        select(Visit)
        .where(Visit.job_id == job.id)
        .where(col(Visit.date) < day)
        .where(Visit.status != "cancelled")
        .order_by(col(Visit.date).desc())
    ).all()
    for v in rows:
        if v.date.weekday() == day.weekday() and v.assigned_person_ids:
            return list(v.assigned_person_ids)
    return list(rows[0].assigned_person_ids) if rows else []


def generate(
    session: Session,
    actor: Actor,
    branch: Branch,
    *,
    days: int = HORIZON_DAYS,
    today: dt.date | None = None,
) -> list[Visit]:
    """Create the missing visits of every job for the next `days` days. Existing (job, date)
    pairs are left alone, cancelled ones included. New visits copy the last assignment on the
    same weekday when that person is still eligible, else they are `unfilled`."""
    tz = branch.timezone
    today = today or utcnow().astimezone(ZoneInfo(tz)).date()
    events.write_lock(session)  # the ticker and `mia schedule generate` must not both read
    jobs = session.exec(select(Job).where(Job.branch_id == branch.id)).all()
    existing = {
        (v.job_id, v.date)
        for v in session.exec(
            select(Visit).where(Visit.branch_id == branch.id).where(col(Visit.date) >= today)
        )
    }
    new: list[Visit] = []
    for job in jobs:
        try:
            validate_rule(job.recurrence)
        except ValueError as exc:
            log.warning("job %s (%s) skipped: %s", job.name, job.id, exc)
            continue
        anchor = job.created_at.astimezone(ZoneInfo(tz)).date()
        for offset in range(days):
            day = today + dt.timedelta(days=offset)
            if (job.id, day) in existing or not occurs_on(job.recurrence, anchor, day):
                continue
            start = local_dt(day, job.start_time, tz)
            visit = Visit(
                branch_id=branch.id,
                job_id=job.id,
                location_id=job.location_id,
                date=day,
                planned_start=start,
                planned_end=start + dt.timedelta(minutes=job.duration_minutes),
                status="unfilled",
            )
            people = [
                p
                for pid in _last_assignees(session, job, day)
                if (p := session.get(Person, pid)) is not None and p.status == "active"
            ]
            keep = [p.id for p in people if not ineligibility(session, branch, visit, p)]
            if keep:
                visit.assigned_person_ids = keep
                visit.status = "planned"
            new.append(store.insert(session, visit, actor, action="visit.generated"))
            existing.add((job.id, day))
    return new


_generated_on: dict[str, dt.date] = {}


GENERATE_FROM_HOUR = 3


def generate_due(session: Session, now: dt.datetime) -> int:
    """Run generation for every branch once per local day, from 03:00 local (the ticker).
    Returns new visits."""
    count = 0
    for branch in session.exec(select(Branch)).all():
        local = now.astimezone(ZoneInfo(branch.timezone))
        local_day = local.date()
        if local.hour < GENERATE_FROM_HOUR or _generated_on.get(branch.id) == local_day:
            continue
        count += len(generate(session, Actor.system(branch.id), branch, today=local_day))
        _generated_on[branch.id] = local_day
    return count


def reset_generation() -> None:
    """Forget the per-day marker (tests)."""
    _generated_on.clear()


# ---- assignment --------------------------------------------------------------------------


@dataclass(frozen=True)
class Assignment:
    visit: Visit
    approval_id: str | None
    reasons: list[str]


def _apply(
    session: Session,
    actor: Actor,
    visit: Visit,
    person: Person,
    add: bool,
    approval_id: str | None = None,
) -> Visit:
    ids = list(visit.assigned_person_ids) if add else []
    if person.id in ids:
        return visit
    ids.append(person.id)
    return store.update(
        session,
        visit,
        {"assigned_person_ids": ids, "status": "planned"},
        actor,
        action="visit.assigned",
        approval_id=approval_id,
    )


def assign(
    session: Session,
    actor: Actor,
    visit: Visit,
    person: Person,
    *,
    add: bool = False,
    org_wide: bool = False,
    among: Collection[str] | None = None,
) -> Assignment:
    """Put the person on the visit (replacing the assignees unless `add`). Eligible: done and
    `visit.assigned`. Not eligible: an override approval is created and the visit is unchanged
    until an admin or owner approves it. ScheduleError for an inactive person or a visit that
    is not open."""
    if visit.status not in OPEN:
        raise ScheduleError(f"visit is {visit.status}")
    if person.status != "active":
        raise ScheduleError("person is not active")
    already = person.id in visit.assigned_person_ids
    if already and (add or visit.assigned_person_ids == [person.id]):
        return Assignment(visit, None, [])
    branch = session.get(Branch, visit.branch_id)
    assert branch is not None
    reasons = ineligibility(session, branch, visit, person, org_wide=org_wide, among=among)
    if reasons:
        for open_one in approvals.pending(session, visit.branch_id):  # one card per ask
            if (
                open_one.type == OVERRIDE_TYPE
                and open_one.subject_id == visit.id
                and open_one.evidence.get("person_id") == person.id
            ):
                return Assignment(visit, open_one.id, reasons)
        approval = approvals.request(
            session,
            OVERRIDE_TYPE,
            ("visit", visit.id),
            f"Assign {person.name} to a visit outside the rules: " + "; ".join(reasons),
            actor,
            OVERRIDE_ROLES,
            "app_only",
            evidence={
                "person_id": person.id,
                "person": person.name,
                "reasons": reasons,
                "add": add,
            },
        )
        return Assignment(visit, approval.id, reasons)
    return Assignment(_apply(session, actor, visit, person, add), None, [])


def cancel_day(session: Session, actor: Actor, branch_id: str, day: dt.date) -> list[Visit]:
    """Cancel every open (planned or unfilled) visit of the branch on the local date, each with
    `visit.cancelled`; visits in progress or done are left alone. Returns the cancelled ones."""
    rows = session.exec(
        select(Visit)
        .where(Visit.branch_id == branch_id)
        .where(Visit.date == day)
        .where(col(Visit.status).in_(OPEN))
    ).all()
    return [
        store.update(session, v, {"status": "cancelled"}, actor, action="visit.cancelled")
        for v in rows
    ]


def unassign(session: Session, actor: Actor, visit: Visit, person: Person) -> Visit:
    """Take the person off the visit; nobody left makes it `unfilled`."""
    if person.id not in visit.assigned_person_ids:
        raise ScheduleError("person is not assigned to this visit")
    ids = [i for i in visit.assigned_person_ids if i != person.id]
    status = visit.status if ids else "unfilled"
    return store.update(
        session,
        visit,
        {"assigned_person_ids": ids, "status": status},
        actor,
        action="visit.unassigned",
    )


def on_override_approved(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: apply the assignment the office asked for."""
    visit = session.get(Visit, approval.subject_id)
    person = session.get(Person, str(approval.evidence.get("person_id")))
    if visit is None or person is None or visit.status not in OPEN or person.status != "active":
        why = (
            "visit gone"
            if visit is None
            else "person gone"
            if person is None
            else (
                f"visit is {visit.status}" if visit.status not in OPEN else "person is not active"
            )
        )
        events.emit(session, "visit.override_not_applied", approval, None, {"reason": why}, decider)
        return
    _apply(session, decider, visit, person, bool(approval.evidence.get("add")), approval.id)


approvals.register_handler(OVERRIDE_TYPE, on_override_approved)


# ---- the current visit ---------------------------------------------------------------------


def current_visit(
    session: Session,
    branch: Branch,
    person: Person,
    now: dt.datetime,
    *,
    location_id: str | None = None,
) -> Visit | None:
    """The person's visit in progress today, else the planned one today nearest to now that
    has not ended (the visit check-in, photos and problem reports attach to)."""
    today = now.astimezone(ZoneInfo(branch.timezone)).date()
    rows = [
        v
        for v in session.exec(
            select(Visit)
            .where(Visit.branch_id == branch.id)
            .where(Visit.date == today)
            .where(col(Visit.status).in_(("planned", "in_progress")))
            .order_by(col(Visit.planned_start))
        ).all()
        if person.id in v.assigned_person_ids
        and (location_id is None or v.location_id == location_id)
    ]
    running = [v for v in rows if v.status == "in_progress"]
    if running:
        return running[0]
    ahead = [v for v in rows if v.planned_end >= now]
    return min(ahead, key=lambda v: abs((v.planned_start - now).total_seconds())) if ahead else None


# ---- check-in and check-out ------------------------------------------------------------


def check_in(
    session: Session, actor: Actor, visit: Visit, person: Person, now: dt.datetime
) -> Visit:
    """Mark the visit in progress for an assigned person, from 2 hours before the planned
    start until 4 hours after the planned end."""
    if person.id not in visit.assigned_person_ids:
        raise ScheduleError("person is not assigned to this visit")
    if visit.status != "planned":
        raise ScheduleError(f"visit is {visit.status}")
    if now < visit.planned_start - CHECK_IN_EARLY:
        raise ScheduleError("too early to check in")
    if now > visit.planned_end + CHECK_IN_LATE:
        raise ScheduleError("too late to check in")
    return store.update(
        session,
        visit,
        {"actual_start": now, "status": "in_progress"},
        actor,
        action="visit.checked_in",
    )


def check_out(
    session: Session, actor: Actor, visit: Visit, person: Person, now: dt.datetime
) -> Visit:
    """Complete a visit in progress for an assigned person."""
    if person.id not in visit.assigned_person_ids:
        raise ScheduleError("person is not assigned to this visit")
    if visit.status != "in_progress":
        raise ScheduleError(f"visit is {visit.status}")
    return store.update(
        session,
        visit,
        {"actual_end": now, "status": "completed"},
        actor,
        action="visit.checked_out",
    )


# ---- reading ------------------------------------------------------------------------------


def week(
    session: Session,
    branch_id: str,
    start: dt.date,
    *,
    person_id: str | None = None,
    location_id: str | None = None,
) -> list[Visit]:
    """Seven days of visits from `start`, by planned start; optionally one person's or one
    site's."""
    stmt = (
        select(Visit)
        .where(Visit.branch_id == branch_id)
        .where(col(Visit.date) >= start)
        .where(col(Visit.date) <= start + dt.timedelta(days=6))
        .order_by(col(Visit.planned_start))
    )
    if location_id is not None:
        stmt = stmt.where(Visit.location_id == location_id)
    rows = list(session.exec(stmt).all())
    if person_id is not None:
        rows = [v for v in rows if person_id in v.assigned_person_ids]
    return rows


def inbox(session: Session, actor: Actor) -> list[Approval]:
    """Pending and escalated approvals the actor may decide (approver roles, or the escalation
    roles once escalated; their own request only as an owner of its branch, D37), oldest
    first. Roles inherit through policy.csv (owner > admin > ...)."""
    from mia.core.rbac import get_rbac

    enforcer = get_rbac().enforcer
    mine = set(actor.principal.roles)
    for role in list(mine):
        mine.update(enforcer.get_implicit_roles_for_user(role, "*"))
    out = []
    for approval in approvals.pending(session, actor.branch_id):
        own = actor.ids & approvals.requester_ids(approval)
        if own and not approvals.owner_of_own(session, approval, actor):
            continue  # nobody approves a request they made or triggered, but an owner (D37)
        roles = set(approval.approver_roles)
        if approval.status == "escalated":
            roles |= set(approval.escalate_to)
        if roles & mine:
            out.append(approval)
    return out
