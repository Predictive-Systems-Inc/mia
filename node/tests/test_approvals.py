"""Approvals: no self-approval, approver roles, channels, expiry, handlers, and the money rule."""

import datetime as dt
from pathlib import Path

import pytest
from pydantic import BaseModel
from sqlmodel import Session, select

from mia.agents.base import AgentDeps, Manifest, ToolBinding, call_tool, guard
from mia.core import approvals, store
from mia.core.approvals import ApprovalError, ApprovalRequired
from mia.core.db import utcnow
from mia.core.models import Actor, Approval, Branch, Event, Person


def _request(session: Session, requester: Actor, **kw: object) -> Approval:
    return approvals.request(
        session,
        "demo_change",
        ("visit", "V1"),
        "demo",
        requester,
        ["supervisor", "owner"],
        **kw,  # type: ignore[arg-type]
    )


def test_request_is_pending_and_logged(session: Session, people: dict[str, Person]) -> None:
    row = _request(session, Actor.person(people["Sanna"]).as_agent("agent.dispatcher"))
    assert row.status == "pending" and row.expires_at is not None
    assert session.exec(select(Event).where(Event.action == "approval.requested")).first()


def test_requester_cannot_approve_own_request(session: Session, people: dict[str, Person]) -> None:
    sanna = Actor.person(people["Sanna"])
    row = _request(session, sanna.as_agent("agent.dispatcher"))
    with pytest.raises(ApprovalError, match="made or triggered"):
        approvals.decide(session, row.id, sanna, "approved")


def test_person_who_triggered_cannot_approve(session: Session, people: dict[str, Person]) -> None:
    helena = Actor.person(people["Helena"])
    row = _request(
        session, Actor.person(people["Sanna"]), evidence={"triggered_by": [people["Helena"].id]}
    )
    with pytest.raises(ApprovalError, match="made or triggered"):
        approvals.decide(session, row.id, helena, "approved")


def test_decider_needs_an_approver_role(session: Session, people: dict[str, Person]) -> None:
    row = _request(session, Actor.person(people["Sanna"]))
    with pytest.raises(ApprovalError, match="approver role"):
        approvals.decide(session, row.id, Actor.person(people["Maria"]), "approved")


def test_agents_never_decide(session: Session, people: dict[str, Person]) -> None:
    row = _request(session, Actor.person(people["Sanna"]))
    agent = Actor.person(people["Helena"]).as_agent("agent.dispatcher")
    with pytest.raises(ApprovalError, match="only people"):
        approvals.decide(session, row.id, agent, "approved")


def test_money_approvals_are_app_only(session: Session, people: dict[str, Person]) -> None:
    row = _request(session, Actor.person(people["Sanna"]), risk="money")
    assert row.channel == "app_only"
    with pytest.raises(ApprovalError, match="Mia app"):
        approvals.decide(
            session, row.id, Actor.person(people["Helena"]), "approved", channel="whatsapp"
        )
    ok = approvals.decide(
        session, row.id, Actor.person(people["Helena"]), "approved", channel="app"
    )
    assert ok.status == "approved" and ok.decided_by == people["Helena"].id


def test_approved_runs_handler_rejected_does_not(
    session: Session, people: dict[str, Person]
) -> None:
    calls: list[str] = []
    approvals.register_handler("demo_change", lambda s, a, d: calls.append(a.id))
    first = _request(session, Actor.person(people["Sanna"]))
    second = _request(session, Actor.person(people["Sanna"]))
    approvals.decide(session, first.id, Actor.person(people["Helena"]), "approved")
    approvals.decide(session, second.id, Actor.person(people["Helena"]), "rejected", "no")
    assert calls == [first.id]
    with pytest.raises(ApprovalError, match="approved"):
        approvals.decide(session, first.id, Actor.person(people["Helena"]), "rejected")


def test_timeout_escalates_once_then_expires(session: Session, people: dict[str, Person]) -> None:
    sanna = Actor.person(people["Sanna"])
    row = approvals.request(
        session,
        "demo_change",
        ("visit", "V1"),
        "demo",
        sanna,
        ["supervisor"],
        ttl=dt.timedelta(seconds=-1),
        escalate_to=["owner"],
    )
    row = approvals.expire_if_due(session, row, sanna)
    assert row.status == "escalated" and "owner" in row.approver_roles
    store.update(session, row, {"expires_at": utcnow() - dt.timedelta(seconds=1)}, sanna)
    row = approvals.expire_if_due(session, row, sanna)
    assert row.status == "expired"
    with pytest.raises(ApprovalError, match="expired"):
        approvals.decide(session, row.id, Actor.person(people["Helena"]), "approved")
    assert approvals.pending(session, sanna.branch_id) == []


def test_bad_outcome_and_unknown_approval(session: Session, people: dict[str, Person]) -> None:
    helena = Actor.person(people["Helena"])
    with pytest.raises(ValueError):
        approvals.decide(session, "nope", helena, "maybe")
    with pytest.raises(ApprovalError, match="not found"):
        approvals.decide(session, "nope", helena, "approved")
    with pytest.raises(ValueError):
        approvals.request(session, "x", ("visit", "V"), "s", helena, [])


# ---- the money rule for tools (required negative test) ----------------------------------------

MONEY_MANIFEST = {
    "id": "payer",
    "name": "Payer",
    "version": "0.0.1",
    "standard_version": "1.0",
    "instructions": {"base": "base.md"},
    "roles": {
        "agent_role": "agent.payer",
        "grants": ["tool:payer.pay:execute"],
        "denies": ["tool:*:approve"],
        "approvers": {"payer.pay": ["owner"]},
    },
    "tools": [{"id": "payer.pay", "kind": "agent", "risk": "money", "approval": "always"}],
}


class PayInput(BaseModel):
    amount_minor: int


class PayOutput(BaseModel):
    paid: bool


def _money_deps(session: Session, branch: Branch, people: dict[str, Person]) -> AgentDeps:
    from mia.core.rbac import get_rbac

    manifest = Manifest.model_validate(MONEY_MANIFEST)
    rbac = get_rbac()
    rbac.load_agent_role("agent.payer", ["tool:payer.pay:execute", "tool:payer.pay:request"], [])
    if not rbac.enforcer.has_policy("owner", "*", "tool:payer.pay", "request", "allow"):
        rbac.enforcer.add_policy("owner", "*", "tool:payer.pay", "request", "allow")
    helena = people["Helena"]
    return AgentDeps(
        session=session,
        actor=Actor.person(helena).as_agent("agent.payer"),
        person=helena,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=dt.datetime.now(dt.UTC).date(),
        lang="en",
        manifest=manifest,
    )


def test_money_tool_without_approval_raises_and_does_not_execute(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = _money_deps(session, branch, people)
    executed: list[int] = []

    def pay(d: AgentDeps, args: PayInput, call_id: str) -> PayOutput:
        executed.append(args.amount_minor)
        return PayOutput(paid=True)

    with pytest.raises(ApprovalRequired) as info:
        guard(deps, deps.manifest.tool("payer.pay"), "call-1")
    assert session.get(Approval, info.value.approval_id) is not None

    out = call_tool(
        deps, ToolBinding("payer.pay", pay, PayInput, "pay"), PayInput(amount_minor=5000), "call-2"
    )
    assert out["status"] == "approval_required"
    assert executed == []

    approval = session.get(Approval, out["approval_id"])
    assert approval is not None and approval.channel == "app_only"
    co_owner = store.insert(
        session,
        Person(branch_id=branch.id, name="Otto Osakas", roles=["owner"]),
        Actor.system(branch.id),
    )
    approvals.decide(session, approval.id, Actor.person(co_owner), "approved")
    deps.approved.add(approval.id)
    assert call_tool(
        deps, ToolBinding("payer.pay", pay, PayInput, "pay"), PayInput(amount_minor=5000), "c3"
    ) == {"paid": True}
    assert executed == [5000]


def test_manifest_rejects_risky_tool_without_approval() -> None:
    bad = {
        **MONEY_MANIFEST,
        "tools": [{"id": "payer.pay", "kind": "agent", "risk": "money", "approval": "never"}],
    }
    with pytest.raises(ValueError, match="approval never"):
        Manifest.model_validate(bad)
    no_approvers = {**MONEY_MANIFEST, "roles": {**MONEY_MANIFEST["roles"], "approvers": {}}}  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="approvers"):
        Manifest.model_validate(no_approvers)


def test_manifest_loads_from_yaml(tmp_path: Path) -> None:
    import yaml

    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(MONEY_MANIFEST))
    manifest = Manifest.load(path)
    assert manifest.tool("payer.pay").name == "pay"
    with pytest.raises(KeyError):
        manifest.tool("payer.nope")
