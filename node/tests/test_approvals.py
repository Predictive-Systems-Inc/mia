"""Approvals: no self-approval, approver roles, channels, expiry, handlers, and the money rule."""

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

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
    row = _request(session, Actor.person(people["Sanna"]).as_agent("agent.shift_supervisor"))
    assert row.status == "pending" and row.expires_at is not None
    assert session.exec(select(Event).where(Event.action == "approval.requested")).first()


def test_requester_cannot_approve_own_request(session: Session, people: dict[str, Person]) -> None:
    sanna = Actor.person(people["Sanna"])
    row = _request(session, sanna.as_agent("agent.shift_supervisor"))
    with pytest.raises(ApprovalError, match="made or triggered"):
        approvals.decide(session, row.id, sanna, "approved")


def test_an_owners_own_price_change_is_decided_by_the_owner_with_step_up(
    session: Session, people: dict[str, Person]
) -> None:
    helena = Actor.person(people["Helena"])  # the owner (D37)
    row = _request(session, helena.as_agent("agent.shift_supervisor"), risk="money")
    with pytest.raises(ApprovalError, match="made or triggered"):
        approvals.decide(session, row.id, helena, "approved")  # no step-up
    ok = approvals.decide(session, row.id, helena, "approved", stepped_up_at=utcnow())
    assert ok.status == "approved" and ok.decided_by == people["Helena"].id


def test_an_owner_cannot_self_decide_a_non_money_request(
    session: Session, people: dict[str, Person]
) -> None:
    helena = Actor.person(people["Helena"])  # the owner; D37 reaches app_only requests only
    row = _request(session, helena.as_agent("agent.shift_supervisor"))
    assert row.channel == "any"
    with pytest.raises(ApprovalError, match="made or triggered"):
        approvals.decide(session, row.id, helena, "approved", stepped_up_at=utcnow())


def test_a_supervisor_still_cannot_decide_their_own_request(
    session: Session, people: dict[str, Person]
) -> None:
    sanna = Actor.person(people["Sanna"])
    row = _request(session, sanna.as_agent("agent.shift_supervisor"), risk="money")
    with pytest.raises(ApprovalError, match="made or triggered"):
        approvals.decide(session, row.id, sanna, "approved", stepped_up_at=utcnow())


def test_an_owner_of_another_branch_cannot_decide_it(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    helena = Actor.person(people["Helena"])
    other = store.insert(
        session, Branch(organisation_id=branch.organisation_id, name="Other"), helena
    )
    owner = store.insert(
        session, Person(branch_id=other.id, name="Olli Owner", roles=["owner"]), helena
    )
    here = Actor.person(owner).model_copy(update={"branch_id": branch.id})  # acting here
    row = _request(session, here.as_agent("agent.shift_supervisor"), risk="money")
    assert row.branch_id == branch.id
    with pytest.raises(ApprovalError, match="made or triggered"):
        approvals.decide(session, row.id, here, "approved", stepped_up_at=utcnow())


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
    agent = Actor.person(people["Helena"]).as_agent("agent.shift_supervisor")
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
        session,
        row.id,
        Actor.person(people["Helena"]),
        "approved",
        channel="app",
        stepped_up_at=utcnow(),
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


def test_rejected_runs_the_reject_handler_in_the_same_transaction(
    session: Session, people: dict[str, Person]
) -> None:
    rejected: list[str] = []
    approvals.register_reject_handler("demo_reject", lambda s, a, d: rejected.append(a.status))
    requester = Actor.person(people["Sanna"])
    first, second = (
        approvals.request(
            session, "demo_reject", ("visit", "V1"), "x", requester, ["supervisor", "owner"]
        )
        for _ in range(2)
    )
    approvals.decide(session, first.id, Actor.person(people["Helena"]), "approved")
    approvals.decide(session, second.id, Actor.person(people["Helena"]), "rejected", "no")
    assert rejected == ["rejected"]  # the approve path does not run it


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
        today=dt.datetime.now(ZoneInfo("Europe/Helsinki")).date(),
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
    assert approval.evidence == {
        "tool_call_id": "call-2",
        "input": {"amount_minor": 5000},
        "risk": "money",
    }
    co_owner = store.insert(
        session,
        Person(branch_id=branch.id, name="Otto Osakas", roles=["owner"]),
        Actor.system(branch.id),
    )
    approvals.decide(
        session, approval.id, Actor.person(co_owner), "approved", stepped_up_at=utcnow()
    )
    deps.approved.add(approval.id)
    assert call_tool(
        deps, ToolBinding("payer.pay", pay, PayInput, "pay"), PayInput(amount_minor=5000), "c3"
    ) == {"paid": True}
    assert executed == [5000]


def _internal_deps(
    session: Session, branch: Branch, people: dict[str, Person], **row: object
) -> AgentDeps:
    """The payer with pay as a write_internal tool that is always approved first."""
    deps = _money_deps(session, branch, people)
    tool = {"id": "payer.pay", "kind": "agent", "risk": "write_internal", "approval": "always"}
    deps.manifest = Manifest.model_validate({**MONEY_MANIFEST, "tools": [tool | row]})
    return deps


def _pay_binding(executed: list[int], **kw: object) -> ToolBinding:
    def pay(d: AgentDeps, args: PayInput, call_id: str) -> PayOutput:
        executed.append(args.amount_minor)
        return PayOutput(paid=True)

    return ToolBinding("payer.pay", pay, PayInput, "pay", **kw)  # type: ignore[arg-type]


def test_an_always_tool_waits_for_approval_when_not_risky(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = _internal_deps(session, branch, people)
    executed: list[int] = []
    out = call_tool(deps, _pay_binding(executed), PayInput(amount_minor=7), "w1")
    assert out["status"] == "approval_required" and executed == []
    approval = session.get(Approval, out["approval_id"])
    assert approval is not None and approval.channel == "any"  # not money: no app-only rule
    assert approval.evidence["input"] == {"amount_minor": 7}
    co_owner = store.insert(
        session,
        Person(branch_id=branch.id, name="Otto Osakas", roles=["owner"]),
        Actor.system(branch.id),
    )
    approvals.decide(session, approval.id, Actor.person(co_owner), "approved", channel="chat")
    deps.approved.add(approval.id)
    assert call_tool(deps, _pay_binding(executed), PayInput(amount_minor=7), "w2") == {"paid": True}
    assert executed == [7]


def test_a_precheck_refuses_before_any_approval(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = _internal_deps(session, branch, people)

    def refuse(d: AgentDeps, args: PayInput, call_id: str) -> None:
        raise LookupError("too_small")

    executed: list[int] = []
    out = call_tool(deps, _pay_binding(executed, precheck=refuse), PayInput(amount_minor=1), "p1")
    assert (out["status"], out["message"]) == ("invalid", "too_small")
    assert session.exec(select(Approval)).all() == [] and executed == []


def test_a_sensitive_tool_logs_ids_only(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = _internal_deps(session, branch, people, sensitive=True)
    call_tool(deps, _pay_binding([]), PayInput(amount_minor=4242), "s1")
    plain = _internal_deps(session, branch, people)
    call_tool(plain, _pay_binding([]), PayInput(amount_minor=1717), "s2")
    called = {
        e.tool_call_id: e for e in session.exec(select(Event).where(Event.action == "tool.called"))
    }
    assert called["s1"].before == {"input": {"amount_minor": "<redacted>"}}
    after = called["s1"].after
    assert after is not None and after["output"]["status"] == "approval_required"
    assert called["s2"].before == {"input": {"amount_minor": 1717}}  # not sensitive: unchanged
    requested = session.exec(select(Event).where(Event.action == "approval.requested")).all()
    assert all("4242" not in str(e.after) for e in requested)  # evidence stays off the chain


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


def test_the_requester_withdraws_a_pending_request(
    session: Session, people: dict[str, Person]
) -> None:
    requester = Actor.person(people["Juha"]).as_agent("agent.shift_supervisor")
    row = approvals.withdraw(session, _request(session, requester), requester, "cancelled")
    assert row.status == "withdrawn"
    event = session.exec(select(Event).where(Event.action == "approval.withdrawn")).one()
    assert event.after is not None and event.after["reason"] == "cancelled"


def test_a_stranger_cannot_withdraw_a_request(session: Session, people: dict[str, Person]) -> None:
    row = _request(session, Actor.person(people["Juha"]).as_agent("agent.shift_supervisor"))
    for stranger in [
        Actor.person(people["Sanna"]),
        Actor.person(people["Mikael"]).as_agent("agent.shift_supervisor"),  # the same agent id
    ]:
        with pytest.raises(ApprovalError):
            approvals.withdraw(session, row, stranger, "cancelled")
    assert row.status == "pending"


def test_a_withdrawn_request_cannot_be_decided_or_withdrawn_again(
    session: Session, people: dict[str, Person]
) -> None:
    requester = Actor.person(people["Juha"]).as_agent("agent.shift_supervisor")
    row = _request(session, requester)
    approvals.withdraw(session, row, Actor.system(row.branch_id), "cancelled")
    with pytest.raises(ApprovalError, match="withdrawn"):
        approvals.decide(session, row.id, Actor.person(people["Sanna"]), "approved")
    with pytest.raises(ApprovalError):
        approvals.withdraw(session, row, requester, "again")


def test_expire_closes_an_open_request_with_its_reason_and_runs_no_handler(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[str] = []
    monkeypatch.setitem(approvals._handlers, "demo_change", lambda s, a, d: ran.append(a.id))
    row = _request(session, Actor.person(people["Juha"]).as_agent("agent.shift_supervisor"))
    approvals.expire(session, row, Actor.system(row.branch_id), "past")
    assert (row.status, row.reason, ran) == ("expired", "past", [])
    event = session.exec(select(Event).where(Event.action == "approval.expired")).one()
    assert event.approval_id == row.id
    with pytest.raises(ApprovalError, match="expired"):
        approvals.decide(session, row.id, Actor.person(people["Sanna"]), "approved")
    with pytest.raises(ApprovalError):  # no longer open
        approvals.expire(session, row, Actor.system(row.branch_id), "again")
