"""The supervisor view (plan, Sprint 2): what needs attention in one call, and closing a site
problem. Every route takes the signed-in person and checks RBAC (rule 4)."""

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import col, select

from mia.api.deps import DbSession, PersonAuth
from mia.api.schedule import VisitCard, branch_of, require_visit, visit_card
from mia.channels.inbound import OUTSIDE_FENCE
from mia.chat import phrases
from mia.chat.route_memory import key_of
from mia.core import scheduling, store
from mia.core.db import utcnow
from mia.core.models import Event, Incident, Location, Person, Visit
from mia.core.orgconfig import load as load_org
from mia.core.rbac import Resource, get_rbac

router = APIRouter(tags=["supervisor"])


class ProblemCard(BaseModel):
    id: str
    kind: str
    text: str
    person: str
    location: str
    visit_id: str
    reported_at: dt.datetime


class FenceCard(BaseModel):
    """A check-in or check-out by location share outside the site's geofence."""

    kind: str  # check_in or check_out
    reason: str  # outside (the fence) or picked_place (a chosen place, not the person's position)
    person: str
    distance_m: int
    visit: VisitCard


class Summary(BaseModel):
    unfilled: list[VisitCard]
    late_check_ins: list[VisitCard]
    outside_fence: list[FenceCard]
    open_problems: list[ProblemCard]
    pending_approvals: int


@router.get("/supervisor/summary", response_model=Summary)
def summary(session: DbSession, ctx: PersonAuth) -> Summary:
    """Unfilled visits this week, today's late check-ins, open problems and the number of
    approvals the person may decide. Staff get 403."""
    require_visit(session, ctx, "read", None)
    branch = branch_of(session, ctx)
    tz = branch.timezone
    now = utcnow()
    today = now.astimezone(ZoneInfo(tz)).date()
    week = scheduling.week(session, branch.id, today)
    grace = dt.timedelta(minutes=load_org().alerts.check_in_grace_minutes)
    late = [
        v
        for v in week
        if v.date == today
        and v.status == "planned"
        and v.assigned_person_ids
        and v.planned_start <= now - grace
    ]
    problems = session.exec(
        select(Incident)
        .where(Incident.branch_id == branch.id)
        .where(Incident.status == "open")
        .order_by(col(Incident.id))
    ).all()
    flagged = session.exec(
        select(Event).where(Event.branch_id == branch.id).where(Event.action == OUTSIDE_FENCE)
    ).all()
    fence = []
    for ev in flagged:
        data = ev.after or {}
        visit = session.get(Visit, ev.entity_id)
        if visit is None or data.get("date") != today.isoformat():
            continue
        person = session.get(Person, str(data.get("person_id")))
        fence.append(
            FenceCard(
                kind=str(data.get("kind")),
                reason=str(data.get("reason", "outside")),
                person=person.name if person else "?",
                distance_m=int(data.get("distance_m", 0)),
                visit=visit_card(session, visit, tz),
            )
        )
    cards = []
    for p in problems:
        person = session.get(Person, p.person_id)
        visit = session.get(Visit, p.visit_id)
        loc = session.get(Location, visit.location_id) if visit else None
        cards.append(
            ProblemCard(
                id=p.id,
                kind=p.kind,
                text=p.text,
                person=person.name if person else "?",
                location=loc.name if loc else "?",
                visit_id=p.visit_id,
                reported_at=p.created_at,
            )
        )
    return Summary(
        unfilled=[visit_card(session, v, tz) for v in week if v.status == "unfilled"],
        late_check_ins=[visit_card(session, v, tz) for v in late],
        outside_fence=fence,
        open_problems=cards,
        pending_approvals=len(scheduling.inbox(session, ctx.actor)),
    )


@router.post("/problems/{problem_id}/resolve")
def resolve(session: DbSession, ctx: PersonAuth, problem_id: str) -> dict[str, str]:
    """Close a site problem (supervisors and up)."""
    require_visit(session, ctx, "write", None)
    row = session.get(Incident, problem_id)
    if row is None or row.branch_id != ctx.actor.branch_id:
        raise HTTPException(404, "problem not found")
    if row.status == "open":
        store.update(
            session,
            row,
            {"status": "resolved", "resolved_by": ctx.actor.principal.id, "resolved_at": utcnow()},
            ctx.actor,
            action="site_problem.resolved",
        )
    return {"id": row.id, "status": row.status}


# Saved reports (teach-Mia 4c): owners and admins (read_all on sales_counts, who read every
# kiosk's sales) list and retire them at their branch in production, not only on the dev sim.
REPORTS_RIGHT = (Resource(kind="data", name="sales_counts"), "read_all")


class ReportRetireIn(BaseModel):
    key: str  # the saved question's words or its key


def _require_reports(session: DbSession, ctx: PersonAuth) -> None:
    if not get_rbac().check(ctx.actor, *REPORTS_RIGHT, session=session):
        session.commit()  # keep the rbac.deny event
        raise HTTPException(403, "owners and admins only")


@router.get("/reports")
def saved_reports(session: DbSession, ctx: PersonAuth) -> list[dict[str, object]]:
    """The branch's live saved reports: key, text and form (owners and admins)."""
    _require_reports(session, ctx)
    found = phrases.saved_reports(session, ctx.actor.branch_id)
    return [{"key": k, "text": a.get("text", k), "form": a["form"]} for k, a in found.items()]


@router.post("/reports/retire")
def retire_report(session: DbSession, ctx: PersonAuth, body: ReportRetireIn) -> dict[str, str]:
    """Withdraw a saved report at the branch (report.retired); 404 when none is saved."""
    _require_reports(session, ctx)
    key = key_of(body.key)
    if phrases.saved_report(session, ctx.actor.branch_id, key) is None:
        raise HTTPException(404, "no saved report for that key")
    phrases.retire_report(session, ctx.actor, ctx.actor.branch_id, key)
    return {"key": key, "status": "retired"}
