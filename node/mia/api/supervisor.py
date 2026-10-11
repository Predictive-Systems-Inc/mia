"""The supervisor view (plan, Sprint 2): what needs attention in one call, and closing a site
problem. Every route takes the signed-in person and checks RBAC (rule 4)."""

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import col, select

from mia.agents.dispatcher.models import SiteProblem
from mia.api.deps import DbSession, PersonAuth
from mia.api.schedule import VisitCard, branch_of, require_visit, visit_card
from mia.channels.inbound import OUTSIDE_FENCE
from mia.core import scheduling, store
from mia.core.db import utcnow
from mia.core.models import Event, Location, Person, Visit
from mia.core.orgconfig import load as load_org

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
        select(SiteProblem)
        .where(SiteProblem.branch_id == branch.id)
        .where(SiteProblem.status == "open")
        .order_by(col(SiteProblem.id))
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
    row = session.get(SiteProblem, problem_id)
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
