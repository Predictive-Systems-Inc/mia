"""Cover assignment and cleaner confirmation (decisions D1, D6, D10, D11).

Flow: a person with the right role instructs an assignment; the instruction is the approval
(D1) unless no rule allows it (candidate breaks a hard rule, or the instructor is one of the
people being replaced), in which case an approval goes to admin or owner. Then the candidate is
asked to confirm: message, then a call, then the next candidate. The visit changes only when
the candidate accepts. Quiet hours: messages wait until they end unless the cover is urgent;
calls never happen inside quiet hours.

Every state change is written through mia.core.store (events) and every timing decision is a
pure function of `now`, the visit and the organisation settings, so it is unit tested.
"""

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.dispatcher import scoring
from mia.agents.dispatcher.models import CoverRequest
from mia.channels.base import TemplateCall
from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.chat.channels import call_adapter, notify
from mia.core import approvals, events, store
from mia.core.models import Actor, Approval, Branch, Location, Person, Visit
from mia.core.orgconfig import OrgSettings
from mia.core.orgconfig import load as load_org
from mia.i18n import t

AGENT_ID = "dispatcher"
OVERRIDE_TYPE = "dispatcher.cover_override"
OVERRIDE_APPROVERS = ["admin", "owner"]
OPEN = ("awaiting_approval", "asking")


# ---- timing rules (pure) ------------------------------------------------------------------


def _local(now: dt.datetime, tz: str) -> dt.datetime:
    return now.astimezone(ZoneInfo(tz))


def quiet_end_after(now: dt.datetime, tz: str, org: OrgSettings) -> dt.datetime:
    """The next moment quiet hours end, in UTC-aware form."""
    local = _local(now, tz)
    end = dt.datetime.combine(local.date(), org.quiet_hours.end, tzinfo=local.tzinfo)
    return end if end > local else end + dt.timedelta(days=1)


def is_quiet(now: dt.datetime, tz: str, org: OrgSettings) -> bool:
    """True when `now` falls inside the organisation's quiet hours in the branch time zone."""
    return org.quiet_hours.contains(_local(now, tz).time().replace(tzinfo=None))


def is_urgent_overnight(
    now: dt.datetime, visit_start: dt.datetime, tz: str, org: OrgSettings
) -> bool:
    """During quiet hours: the visit starts before `urgent_until` on the morning quiet hours end."""
    end = quiet_end_after(now, tz, org)
    cutoff = dt.datetime.combine(end.date(), org.cover_confirmation.urgent_until, tzinfo=end.tzinfo)
    return visit_start <= cutoff


def is_soon(now: dt.datetime, visit_start: dt.datetime, org: OrgSettings) -> bool:
    """True when the visit starts within the organisation's soon window."""
    return visit_start - now <= dt.timedelta(minutes=org.cover_confirmation.soon_window_minutes)


def may_message(now: dt.datetime, visit_start: dt.datetime, tz: str, org: OrgSettings) -> bool:
    """Messaging is allowed outside quiet hours, or inside them for urgent overnight cover (D11)."""
    return not is_quiet(now, tz, org) or is_urgent_overnight(now, visit_start, tz, org)


def may_call(now: dt.datetime, tz: str, org: OrgSettings) -> bool:
    """Calls are allowed only outside quiet hours (D11)."""
    return not is_quiet(now, tz, org)


# ---- helpers -------------------------------------------------------------------------------


class CoverError(LookupError):
    """The request cannot be carried out (unknown visit or person, nobody to replace)."""


def _visit_text(session: Session, visit: Visit, tz: str, lang: str) -> dict[str, str]:
    loc = session.get(Location, visit.location_id)
    start = visit.planned_start.astimezone(ZoneInfo(tz))
    date = f"{start.day}.{start.month}." if lang == "fi" else start.strftime("%a %-d %b")
    return {"location": loc.name if loc else "?", "date": date, "time": start.strftime("%H:%M")}


def _branch(session: Session, branch_id: str) -> Branch:
    branch = session.get(Branch, branch_id)
    if branch is None:
        raise CoverError("branch not found")
    return branch


def _person(session: Session, person_id: str) -> Person:
    person = session.get(Person, person_id)
    if person is None:
        raise CoverError("person not found")
    return person


def _tell(
    session: Session,
    person_id: str,
    key: str,
    actor: Actor,
    params: dict[str, str],
    extra: list[Block] | None = None,
) -> None:
    person = _person(session, person_id)
    blocks: list[Block] = [TextBlock(text=t(key, person.language, **params))]
    template = None
    if key == "cover.ask":  # asks are already gated by D11 (may_message), so they are urgent
        lang = person.language
        template = TemplateCall(
            name="mia_cover_request",
            lang=lang,
            params=[person.name.split()[0], params["location"], params["date"], params["time"]],
            buttons=[t("cover.reply_accept", lang), t("cover.reply_decline", lang)],
        )
    notify(
        session,
        person,
        blocks + (extra or []),
        actor,
        AGENT_ID,
        template=template,
        urgent=template is not None,
    )


def cancel_open(session: Session, visit_id: str, actor: Actor, keep: str | None = None) -> None:
    """Close every other open ask for the visit (a new instruction or an acceptance wins)."""
    rows = session.exec(
        select(CoverRequest)
        .where(CoverRequest.visit_id == visit_id)
        .where(col(CoverRequest.status).in_(OPEN))
    ).all()
    for row in rows:
        if row.id != keep:
            store.update(
                session,
                row,
                {"status": "cancelled", "next_action_at": None},
                actor,
                action="cover.cancelled",
            )


def system_actor(branch_id: str) -> Actor:
    """The system actor for a branch, used for scheduled escalation steps."""
    return Actor.system(branch_id)


# ---- instruct ------------------------------------------------------------------------------


def instruct(
    session: Session,
    actor: Actor,
    visit: Visit,
    slot: scoring.Slot,
    candidate: scoring.CandidateData,
    queue: list[str],
    replace_ids: list[str],
    now: dt.datetime,
    *,
    tool_call_id: str | None = None,
) -> CoverRequest:
    """Record an instructed assignment and start confirmation, or request an override approval."""
    instructor = actor.person_id or actor.principal.id
    branch = _branch(session, visit.branch_id)
    broken = scoring.ineligibility(candidate, slot)
    if "absent that day" in broken:
        raise CoverError(f"{candidate.name} is absent that day")
    cancel_open(session, visit.id, actor)
    request = CoverRequest(
        branch_id=visit.branch_id,
        visit_id=visit.id,
        candidate_id=candidate.person_id,
        replace_person_ids=replace_ids,
        queue=queue,
        instructed_by=instructor,
    )
    self_cover = instructor in replace_ids
    if broken or self_cover:
        reasons = broken + (["the instructor is the person being replaced"] if self_cover else [])
        params = _visit_text(session, visit, branch.timezone, "en")
        approval = approvals.request(
            session,
            OVERRIDE_TYPE,
            ("visit", visit.id),
            f"Assign {candidate.name} to {params['location']} {params['date']} {params['time']} "
            f"although: {', '.join(reasons)}",
            actor,
            OVERRIDE_APPROVERS,
            channel="app_only",
            evidence={
                "visit_id": visit.id,
                "candidate_id": candidate.person_id,
                "reasons": reasons,
                "triggered_by": replace_ids,
            },
            tool_call_id=tool_call_id,
        )
        request.status = "awaiting_approval"
        request.approval_id = approval.id
        request.next_action_at = None
        return store.insert(session, request, actor, tool_call_id=tool_call_id)
    events.emit(
        session,
        "assignment.instructed",
        visit,
        None,
        {
            "candidate_id": candidate.person_id,
            "instructed_by": instructor,
            "approved_by": instructor,
        },
        actor,
        tool_call_id=tool_call_id,
    )
    store.insert(session, request, actor, tool_call_id=tool_call_id)
    return start_asking(session, request, actor, now)


def on_override_approved(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: the override was approved, so start asking the candidate."""
    request = session.exec(
        select(CoverRequest).where(CoverRequest.approval_id == approval.id)
    ).first()
    if request is not None and request.status == "awaiting_approval":
        start_asking(session, request, decider, dt.datetime.now(dt.UTC))


approvals.register_handler(OVERRIDE_TYPE, on_override_approved)


# ---- asking and escalation -----------------------------------------------------------------


def _ask(session: Session, request: CoverRequest, actor: Actor) -> None:
    visit = session.get(Visit, request.visit_id)
    candidate = _person(session, request.candidate_id)
    if visit is None:
        raise CoverError("visit not found")
    tz = _branch(session, visit.branch_id).timezone
    lang = candidate.language
    params = _visit_text(session, visit, tz, lang)
    quick = QuickRepliesBlock(
        options=[t("cover.reply_accept", lang), t("cover.reply_decline", lang)]
    )
    _tell(session, candidate.id, "cover.ask", actor, params, [quick])


def _call(session: Session, request: CoverRequest, actor: Actor) -> None:
    visit = session.get(Visit, request.visit_id)
    candidate = _person(session, request.candidate_id)
    if visit is None:
        raise CoverError("visit not found")
    tz = _branch(session, visit.branch_id).timezone
    params = _visit_text(session, visit, tz, candidate.language)
    call_adapter().call(
        session, candidate, t("cover.call_script", candidate.language, **params), actor
    )


def start_asking(
    session: Session, request: CoverRequest, actor: Actor, now: dt.datetime
) -> CoverRequest:
    """First contact with the candidate, respecting quiet hours and urgency."""
    visit = session.get(Visit, request.visit_id)
    if visit is None:
        raise CoverError("visit not found")
    tz = _branch(session, visit.branch_id).timezone
    org = load_org()
    conf = org.cover_confirmation
    if not may_message(now, visit.planned_start, tz, org):
        changes = {
            "status": "asking",
            "stage": "waiting_quiet",
            "next_action_at": quiet_end_after(now, tz, org),
        }
        return store.update(session, request, changes, actor, action="cover.held_for_quiet_hours")
    _ask(session, request, actor)
    if is_soon(now, visit.planned_start, org) and may_call(now, tz, org):
        _call(session, request, actor)
        changes = {
            "status": "asking",
            "stage": "call",
            "next_action_at": now + dt.timedelta(minutes=conf.soon_call_wait_minutes),
        }
        return store.update(session, request, changes, actor, action="cover.asked_and_called")
    changes = {
        "status": "asking",
        "stage": "message",
        "next_action_at": now + dt.timedelta(minutes=conf.message_wait_minutes),
    }
    return store.update(session, request, changes, actor, action="cover.asked")


def advance(
    session: Session, request: CoverRequest, actor: Actor, now: dt.datetime
) -> CoverRequest | None:
    """Take the next escalation step for a due request. Returns the request now being worked."""
    visit = session.get(Visit, request.visit_id)
    if visit is None:
        return store.update(
            session, request, {"status": "cancelled", "next_action_at": None}, actor
        )
    tz = _branch(session, visit.branch_id).timezone
    org = load_org()
    if request.stage == "waiting_quiet":
        return start_asking(session, request, actor, now)
    if request.stage == "message":
        candidate = _person(session, request.candidate_id)
        if not candidate.accepts_calls:
            return give_up(session, request, "timed_out", actor, now)
        if not may_call(now, tz, org):
            changes: dict[str, Any] = {"next_action_at": quiet_end_after(now, tz, org)}
            return store.update(
                session, request, changes, actor, action="cover.call_held_for_quiet_hours"
            )
        _call(session, request, actor)
        wait = org.cover_confirmation.call_wait_minutes
        if is_soon(now, visit.planned_start, org):
            wait = org.cover_confirmation.soon_call_wait_minutes
        changes = {"stage": "call", "next_action_at": now + dt.timedelta(minutes=wait)}
        return store.update(session, request, changes, actor, action="cover.called")
    return give_up(session, request, "timed_out", actor, now)


def give_up(
    session: Session, request: CoverRequest, status: str, actor: Actor, now: dt.datetime
) -> CoverRequest | None:
    """Close this ask (declined or timed out), tell the instructor, and ask the next candidate."""
    store.update(
        session,
        request,
        {"status": status, "next_action_at": None},
        actor,
        action=f"cover.{status}",
    )
    visit = session.get(Visit, request.visit_id)
    if visit is None:
        return None
    tz = _branch(session, visit.branch_id).timezone
    instructor = _person(session, request.instructed_by)
    params = _visit_text(session, visit, tz, instructor.language)
    who = _person(session, request.candidate_id).name
    for next_id in request.queue:
        nxt = CoverRequest(
            branch_id=request.branch_id,
            visit_id=request.visit_id,
            candidate_id=next_id,
            replace_person_ids=request.replace_person_ids,
            queue=[q for q in request.queue if q != next_id],
            instructed_by=request.instructed_by,
        )
        candidate = _person(session, next_id)
        _tell(
            session,
            instructor.id,
            f"cover.sup_{status}_next",
            actor,
            {**params, "name": who, "next": candidate.name},
        )
        store.insert(session, nxt, actor)
        return start_asking(session, nxt, actor, now)
    _tell(session, instructor.id, f"cover.sup_{status}_nobody", actor, {**params, "name": who})
    return None


def respond(
    session: Session, person: Person, accept: bool, actor: Actor, now: dt.datetime
) -> CoverRequest:
    """The candidate's answer. Accept reassigns the visit; decline moves to the next candidate."""
    request = session.exec(
        select(CoverRequest)
        .where(CoverRequest.candidate_id == person.id)
        .where(CoverRequest.status == "asking")
        .order_by(col(CoverRequest.id).desc())
    ).first()
    if request is None:
        raise CoverError("no open cover request for you")
    if not accept:
        give_up(session, request, "declined", actor, now)
        return request
    visit = session.get(Visit, request.visit_id)
    if visit is None:
        raise CoverError("visit not found")
    keep = [
        p
        for p in visit.assigned_person_ids
        if p not in request.replace_person_ids and p != person.id
    ]
    store.update(
        session,
        visit,
        {"assigned_person_ids": [person.id, *keep]},
        actor,
        action="visit.reassigned",
        approval_id=request.approval_id,
    )
    store.update(
        session,
        request,
        {"status": "accepted", "next_action_at": None},
        actor,
        action="cover.accepted",
    )
    cancel_open(session, visit.id, actor, keep=request.id)
    tz = _branch(session, visit.branch_id).timezone
    instructor = _person(session, request.instructed_by)
    params = _visit_text(session, visit, tz, instructor.language)
    _tell(session, instructor.id, "cover.sup_accepted", actor, {**params, "name": person.name})
    return request


def process_due(session: Session, now: dt.datetime) -> int:
    """Advance every open request whose next action is due. Returns how many advanced."""
    due = session.exec(
        select(CoverRequest)
        .where(CoverRequest.status == "asking")
        .where(col(CoverRequest.next_action_at).is_not(None))
        .order_by(col(CoverRequest.id))
    ).all()
    count = 0
    for request in due:
        if request.next_action_at is not None and request.next_action_at <= now:
            advance(session, request, system_actor(request.branch_id), now)
            count += 1
    return count
