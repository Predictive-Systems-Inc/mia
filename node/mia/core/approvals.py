"""Approvals: a record, not a chat message.

Guarantees: nobody decides a request they made or triggered (checked on principal,
on_behalf_of and evidence["triggered_by"]); agents never decide; the decider must hold one of
the approver roles; app_only approvals are decided only in the authenticated app; every
request and decision is written to the events log; approved requests run their handler.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlmodel import Session, col, select

from mia.core import store
from mia.core.db import utcnow
from mia.core.models import Actor, Approval
from mia.core.rbac import get_rbac

RISKY = {"money", "external", "delete"}
DEFAULT_TTL = timedelta(hours=24)

Handler = Callable[[Session, Approval, Actor], None]
_handlers: dict[str, Handler] = {}


class ApprovalRequired(Exception):
    """The action needs a human decision first. Nothing was executed."""

    def __init__(self, approval_id: str) -> None:
        super().__init__(f"approval required: {approval_id}")
        self.approval_id = approval_id


class ApprovalError(Exception):
    """A decision was refused (self-approval, wrong role, wrong channel, not pending)."""


def register_handler(approval_type: str, handler: Handler) -> None:
    """Register the service function that applies an approved request of this type."""
    _handlers[approval_type] = handler


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
    escalate_to: list[str] | None = None,
    tool_call_id: str | None = None,
) -> Approval:
    """Create a pending approval. Money, external and delete risks are forced to app_only."""
    if not approver_roles:
        raise ValueError("an approval needs at least one approver role")
    if risk in RISKY:
        channel = "app_only"
    approval = Approval(
        branch_id=requester.branch_id,
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
        expires_at=utcnow() + ttl,
        escalate_to=escalate_to or ["owner"],
    )
    return store.insert(
        session, approval, requester, action="approval.requested", tool_call_id=tool_call_id
    )


def _requester_ids(approval: Approval) -> set[str]:
    ids = {approval.requester_id}
    if approval.requester_on_behalf_of:
        ids.add(approval.requester_on_behalf_of)
    triggered = approval.evidence.get("triggered_by", [])
    ids.update(triggered if isinstance(triggered, list) else [triggered])
    return ids


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


def decide(
    session: Session,
    approval_id: str,
    decider: Actor,
    outcome: str,
    reason: str | None = None,
    *,
    channel: str = "app",
) -> Approval:
    """Record a decision. Raises ApprovalError when any approval rule is broken."""
    if outcome not in ("approved", "rejected"):
        raise ValueError("outcome must be approved or rejected")
    approval = session.get(Approval, approval_id)
    if approval is None or approval.branch_id != decider.branch_id:
        raise ApprovalError("approval not found")
    approval = expire_if_due(session, approval, decider)
    if approval.status not in ("pending", "escalated"):
        raise ApprovalError(f"approval is {approval.status}")
    if decider.principal.type != "person":
        raise ApprovalError("only people decide approvals")
    if decider.ids & _requester_ids(approval):
        raise ApprovalError("nobody approves a request they made or triggered")
    if not _holds_role(decider, approval.approver_roles):
        raise ApprovalError("decider does not hold an approver role")
    if approval.channel == "app_only" and channel != "app":
        raise ApprovalError("this approval can only be decided in the Mia app")
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
    return approval


def pending(session: Session, branch_id: str) -> list[Approval]:
    """Open approvals for a branch, oldest first."""
    stmt = (
        select(Approval)
        .where(Approval.branch_id == branch_id)
        .where(col(Approval.status).in_(["pending", "escalated"]))
        .order_by(col(Approval.id))
    )
    return list(session.exec(stmt))
