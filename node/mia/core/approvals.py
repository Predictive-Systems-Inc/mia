"""Approvals: a record, not a chat message.

Guarantees: nobody decides a request they made or triggered (checked on principal,
on_behalf_of and evidence["triggered_by"]), except an owner of the approval's branch deciding
their own money, external or delete request with a fresh PIN step-up (D37); agents never
decide; the decider must hold one of the approver roles; app_only approvals are decided only in
the authenticated app, never from the chat (a `chat` approval, D47, takes a chat tap); every request and decision is written to the events log; approved
requests run their handler and rejected ones their reject handler, in the decision's transaction.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, col, select

from mia.core import assignments, events, store
from mia.core.db import utcnow
from mia.core.models import Actor, Approval, Person
from mia.core.rbac import get_rbac

RISKY = {"money", "external", "delete"}
DEFAULT_TTL = timedelta(hours=24)

Handler = Callable[[Session, Approval, Actor], None]
_handlers: dict[str, Handler] = {}
_reject_handlers: dict[str, Handler] = {}
_on_refused: set[str] = set()  # types whose reject handler also follows up a close_refused


class ApprovalRequired(Exception):
    """The action needs a human decision first. Nothing was executed."""

    def __init__(self, approval_id: str) -> None:
        super().__init__(f"approval required: {approval_id}")
        self.approval_id = approval_id


class ApprovalError(Exception):
    """A decision was refused (self-approval, wrong role, wrong channel, not pending)."""


STEP_UP_TTL = timedelta(minutes=5)


class StepUpRequired(ApprovalError):
    """An app_only approval needs aal2 and a PIN entered in the last five minutes."""


def register_handler(approval_type: str, handler: Handler) -> None:
    """Register the service function that applies an approved request of this type."""
    _handlers[approval_type] = handler


def register_reject_handler(
    approval_type: str, handler: Handler, *, on_refused: bool = False
) -> None:
    """Register the service function that follows up a rejected request of this type. With
    on_refused it also runs after close_refused (it must handle status expired with the
    approve handler's reason); without, a refused request closes silently."""
    _reject_handlers[approval_type] = handler
    if on_refused:
        _on_refused.add(approval_type)
    else:
        _on_refused.discard(approval_type)


def request(
    session: Session,
    type: str,
    subject: tuple[str, str],
    summary: str,
    requester: Actor,
    approver_roles: list[str],
    channel: str = "any",
    *,
    risk: str | None = None,
    evidence: dict[str, Any] | None = None,
    ttl: timedelta = DEFAULT_TTL,
    expires_at: datetime | None = None,
    escalate_to: list[str] | None = None,
    tool_call_id: str | None = None,
    branch_id: str | None = None,
) -> Approval:
    """Create a pending approval at `branch_id` (default the requester's branch), the branch
    whose people may decide it (decide's scope); a requester still never decides their own.
    Money, external and delete risks are forced to app_only (whatever `channel` asks, so never
    `chat`, D47) and recorded as evidence["risk"]
    (the approvals table has no risk column; D37 reads it). It expires at `expires_at` when
    given, else `ttl` from now. A timed-out request escalates once to `escalate_to` (default
    owner); `escalate_to=[]` expires it at the deadline instead."""
    if not approver_roles:
        raise ValueError("an approval needs at least one approver role")
    if risk in RISKY:
        channel = "app_only"
        evidence = {**(evidence or {}), "risk": risk}
    else:
        evidence = {k: v for k, v in (evidence or {}).items() if k != "risk"}  # never caller-set
    approval = Approval(
        branch_id=branch_id or requester.branch_id,
        type=type,
        requester_type=requester.principal.type,
        requester_id=requester.principal.id,
        requester_on_behalf_of=requester.on_behalf_of.id if requester.on_behalf_of else None,
        subject_type=subject[0],
        subject_id=subject[1],
        summary=summary,
        evidence=evidence or {},
        approver_roles=list(approver_roles),
        channel=channel,
        expires_at=expires_at or utcnow() + ttl,
        escalate_to=escalate_to if escalate_to is not None else ["owner"],
    )
    return store.insert(
        session, approval, requester, action="approval.requested", tool_call_id=tool_call_id
    )


def requester_ids(approval: Approval) -> set[str]:
    """The principal ids that made or triggered the request (never its approvers)."""
    ids = {approval.requester_id}
    if approval.requester_on_behalf_of:
        ids.add(approval.requester_on_behalf_of)
    return ids | _triggered(approval)


def _triggered(approval: Approval) -> set[str]:
    triggered = approval.evidence.get("triggered_by", [])
    return set(triggered if isinstance(triggered, list) else [triggered])


def owner_of_own(session: Session, approval: Approval, actor: Actor) -> bool:
    """D37, a money rule: the request carries a risky risk (money, external or delete, which
    request records in evidence["risk"] and forces to app_only), the actor made (not
    triggered) it and holds the owner role in the approval's branch (their person row's
    branch), so they may decide it with a step-up. Any other own request (a cover override,
    which is app_only without a risk, or a leave) waits for another approver."""
    if approval.channel != "app_only" or approval.evidence.get("risk") not in RISKY:
        return False
    if not actor.ids & requester_ids(approval) or actor.ids & _triggered(approval):
        return False
    person = session.get(Person, actor.person_id or "")
    return person is not None and person.branch_id == approval.branch_id and "owner" in person.roles


def _owner_deciding_own(
    session: Session, approval: Approval, decider: Actor, stepped_up_at: datetime | None
) -> bool:
    """owner_of_own with a step-up in the last five minutes."""
    fresh = stepped_up_at is not None and utcnow() - stepped_up_at <= STEP_UP_TTL
    return fresh and owner_of_own(session, approval, decider)


def _holds_role(decider: Actor, roles: list[str]) -> bool:
    enforcer = get_rbac().enforcer
    held: set[str] = set()
    for role in decider.principal.roles:
        held.add(role)
        held.update(enforcer.get_implicit_roles_for_user(role, decider.branch_id))
    return bool(held & set(roles))


def expire_if_due(session: Session, approval: Approval, actor: Actor) -> Approval:
    """Escalate a timed-out request once, then expire it."""
    if approval.status not in ("pending", "escalated") or approval.expires_at is None:
        return approval
    if approval.expires_at > utcnow():
        return approval
    if approval.status == "pending" and approval.escalate_to:
        roles = sorted(set(approval.approver_roles) | set(approval.escalate_to))
        changes = {
            "status": "escalated",
            "approver_roles": roles,
            "expires_at": utcnow() + DEFAULT_TTL,
        }
        return store.update(session, approval, changes, actor, action="approval.escalated")
    return store.update(session, approval, {"status": "expired"}, actor, action="approval.expired")


def _refused(
    session: Session,
    approval: Approval,
    decider: Actor,
    why: str,
    exc: type[ApprovalError] = ApprovalError,
) -> None:
    events.emit(
        session,
        "approval.refused",
        approval,
        None,
        {"reason": why},
        decider,
        approval_id=approval.id,
    )
    session.commit()  # raised inside a request: a rollback must not lose the refusal event
    raise exc(why)


def decide(
    session: Session,
    approval_id: str,
    decider: Actor,
    outcome: str,
    reason: str | None = None,
    *,
    channel: str = "app",
    aal: str = "aal2",
    stepped_up_at: datetime | None = None,
) -> Approval:
    """Record a decision. Raises ApprovalError when any approval rule is broken (a requester
    decides their own request only as an owner of its branch with a fresh step-up); an app_only
    approval also needs the app channel, aal2 and a PIN step-up in the last five minutes
    (the approval's branch is the decider's or one they are assigned to, D50)
    (StepUpRequired); a chat decision is taken only for a `chat` approval (D47); each refusal
    is written as `approval.refused`. A request that times out
    at the decision expires and is committed, then runs its type's opted-in reject handler
    (on_refused, so the requester is told; its writes are committed before the ApprovalError,
    and its own error propagates with the expiry kept)."""
    if outcome not in ("approved", "rejected"):
        raise ValueError("outcome must be approved or rejected")
    approval = session.get(Approval, approval_id)
    if approval is None or approval.branch_id not in assignments.actor_branches(session, decider):
        raise ApprovalError("approval not found")
    was_open = approval.status in ("pending", "escalated")
    approval = expire_if_due(session, approval, decider)
    if was_open and approval.status == "expired":
        session.commit()  # first: neither a raising handler nor the caller's rollback loses it
        if approval.type in _on_refused:  # it handles status expired and tells the requester
            _reject_handlers[approval.type](session, approval, decider)
            session.commit()  # the requester's message, before the ApprovalError
    if approval.status not in ("pending", "escalated"):
        raise ApprovalError(f"approval is {approval.status}")
    if decider.principal.type != "person":
        raise ApprovalError("only people decide approvals")
    own = decider.ids & requester_ids(approval)
    if own and not _owner_deciding_own(session, approval, decider, stepped_up_at):
        raise ApprovalError("nobody approves a request they made or triggered")
    if not _holds_role(decider, approval.approver_roles):
        raise ApprovalError("decider does not hold an approver role")
    if channel == "chat" and approval.channel != "chat":  # D47: only a chat approval takes a tap
        _refused(session, approval, decider, "this approval can only be decided in the Mia app")
    if approval.channel == "app_only":
        if channel != "app":
            _refused(session, approval, decider, "this approval can only be decided in the Mia app")
        fresh = stepped_up_at is not None and utcnow() - stepped_up_at <= STEP_UP_TTL
        if aal != "aal2" or not fresh:
            _refused(session, approval, decider, "step_up_required", StepUpRequired)
    approval = store.update(
        session,
        approval,
        {
            "status": outcome,
            "decided_by": decider.principal.id,
            "decided_at": utcnow(),
            "reason": reason,
        },
        decider,
        action=f"approval.{outcome}",
        approval_id=approval.id,
    )
    if outcome == "approved" and approval.type in _handlers:
        _handlers[approval.type](session, approval, decider)
    if outcome == "rejected" and approval.type in _reject_handlers:
        _reject_handlers[approval.type](session, approval, decider)
    return approval


def close_refused(session: Session, approval_id: str, decider: Actor, reason: str) -> Approval:
    """After an approve handler refused (raised LookupError) and the caller rolled the
    decision back: record the attempt (event approval.refused by the decider with the reason,
    the status unchanged), then close the request as expired with the reason (system actor,
    expire), so it is no dead end that every retry refuses, and run the type's reject handler
    only when it opted in (register_reject_handler on_refused; it sees status expired and the
    reason and tells the requester). Raises ApprovalError when the request is no longer open."""
    approval = session.get(Approval, approval_id)
    if approval is None or approval.status not in ("pending", "escalated"):
        raise ApprovalError("approval is not open")
    after = {"reason": reason, "outcome": "approved"}
    events.emit(
        session, "approval.refused", approval, None, after, decider, approval_id=approval.id
    )
    approval = expire(session, approval, Actor.system(approval.branch_id), reason)
    if approval.type in _on_refused:
        _reject_handlers[approval.type](session, approval, decider)
    return approval


def withdraw(session: Session, approval: Approval, actor: Actor, reason: str) -> Approval:
    """Close an open (pending or escalated) request without a decision: status `withdrawn`,
    event `approval.withdrawn` with the reason, no handler runs. Only the requester (its
    principal or on_behalf_of id) or the system may withdraw; raises ApprovalError otherwise
    or when the request is no longer open. An agent's id is shared by everyone it acts for,
    so a request made on behalf of someone needs that someone."""
    if approval.status not in ("pending", "escalated"):
        raise ApprovalError(f"approval is {approval.status}")
    requester = approval.requester_on_behalf_of or approval.requester_id
    if actor.principal.type != "system" and requester not in actor.ids:
        raise ApprovalError("only the requester withdraws a request")
    return store.update(
        session,
        approval,
        {"status": "withdrawn", "reason": reason},
        actor,
        action="approval.withdrawn",
        approval_id=approval.id,
    )


def expire(session: Session, approval: Approval, actor: Actor, reason: str) -> Approval:
    """Close an open (pending or escalated) request that can no longer be decided, now, with
    a reason (for example its subject's date passed): status `expired`, event
    `approval.expired`, no handler runs. A system path: the caller owns the subject and says
    why; raises ApprovalError when the request is no longer open."""
    if approval.status not in ("pending", "escalated"):
        raise ApprovalError(f"approval is {approval.status}")
    return store.update(
        session,
        approval,
        {"status": "expired", "reason": reason},
        actor,
        action="approval.expired",
        approval_id=approval.id,
    )


def pending(session: Session, branch_id: str) -> list[Approval]:
    """Open approvals for a branch, oldest first."""
    stmt = (
        select(Approval)
        .where(Approval.branch_id == branch_id)
        .where(col(Approval.status).in_(["pending", "escalated"]))
        .order_by(col(Approval.id))
    )
    return list(session.exec(stmt))
