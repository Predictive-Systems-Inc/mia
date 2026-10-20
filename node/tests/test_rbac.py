"""Permissions: Casbin roles with branch domains, ownership and agent checks."""

from pathlib import Path

import pytest
from sqlmodel import Session, select

from mia.core.models import Actor, Event, Person, Principal
from mia.core.rbac import PermissionDenied, Rbac, Resource, get_rbac, split_permission
from mia.settings import get_settings


def visit(owner: str | None = None) -> Resource:
    return Resource(kind="data", name="core.visit", owner_id=owner)


def test_cleaner_cannot_read_another_persons_visits(
    session: Session, people: dict[str, Person]
) -> None:
    cleaner = Actor.person(people["Juha"])
    assert not get_rbac().check(cleaner, visit(people["Maria"].id), "read", session=session)
    denied = session.exec(select(Event).where(Event.action == "rbac.deny")).all()
    assert denied and denied[-1].after is not None
    assert denied[-1].after["failed_on"] == people["Juha"].id


def test_cleaner_can_read_own_visits(people: dict[str, Person]) -> None:
    cleaner = Actor.person(people["Juha"])
    assert get_rbac().check(cleaner, visit(people["Juha"].id), "read")


def test_supervisor_reads_everyone(people: dict[str, Person]) -> None:
    sup = Actor.person(people["Sanna"])
    assert get_rbac().check(sup, visit(people["Maria"].id), "read")


def test_role_hierarchy_owner_inherits_supervisor(people: dict[str, Person]) -> None:
    owner = Actor.person(people["Helena"])
    tool = Resource(kind="tool", name="shift_supervisor.cover_override")
    assert get_rbac().check(owner, tool, "approve")
    assert not get_rbac().check(Actor.person(people["Sanna"]), tool, "approve")


def test_agent_on_behalf_of_cleaner_is_limited_by_the_cleaner(people: dict[str, Person]) -> None:
    from mia.agents.shift_supervisor.agent import create_agent

    create_agent("test")  # registers the shift supervisor role from its manifest
    via_agent = Actor.person(people["Juha"]).as_agent("agent.shift_supervisor")
    assert get_rbac().principal_allowed(via_agent.principal, "B", visit(people["Maria"].id), "read")
    assert not get_rbac().check(via_agent, visit(people["Maria"].id), "read")


def test_agent_never_approves_even_if_granted() -> None:
    rbac = Rbac(get_settings().config_dir / "policies")
    rbac.load_agent_role("agent.x", ["tool:x.pay:approve"], ["tool:*:approve"])
    agent = Actor(principal=Principal(type="agent", id="agent.x", roles=["agent.x"]), branch_id="B")
    assert not rbac.check(agent, Resource(kind="tool", name="x.pay"), "approve")


def test_risky_wildcard_grants_are_refused() -> None:
    rbac = Rbac(get_settings().config_dir / "policies")
    with pytest.raises(ValueError, match="one by one"):
        rbac.load_agent_role("agent.x", ["tool:*:request"], [])


def test_domains_isolate_branches() -> None:
    rbac = Rbac(get_settings().config_dir / "policies")
    rbac.enforcer.add_policy("local_role", "BRANCH_A", "data:core.visit", "read", "allow")
    p = Principal(type="person", id="P", roles=["local_role"])
    in_a = Actor(principal=p, branch_id="BRANCH_A")
    in_b = Actor(principal=p, branch_id="BRANCH_B")
    assert rbac.check(in_a, visit(), "read")
    assert not rbac.check(in_b, visit(), "read")


def test_require_raises_permission_denied(people: dict[str, Person]) -> None:
    with pytest.raises(PermissionDenied):
        get_rbac().require(Actor.person(people["Juha"]), visit(people["Aino"].id), "read")


def test_split_permission() -> None:
    assert split_permission("tool:shift_supervisor.x:execute") == (
        "tool:shift_supervisor.x",
        "execute",
    )
    with pytest.raises(ValueError):
        split_permission("nonsense")


ACTIONS = ("read", "write", "read_own", "write_own", "read_all", "write_all", "request")
FULL = {"read", "write", "read_all", "write_all"}
SHARED_RIGHTS: dict[str, dict[str, set[str]]] = {
    "sales_counts": {
        "clerk": {"read_own", "write_own"},
        "supervisor": {"read", "write"},
        "owner": FULL,
        "admin": FULL,
        "agent.sales_supervisor": {"read", "write", "read_all"},
    },
    "sales_targets": {
        "clerk": {"read"},
        "supervisor": {"read", "write"},
        "owner": FULL,
        "admin": FULL,
        "agent.sales_supervisor": {"read", "write", "write_all"},
    },
    "sales_notes": {
        "clerk": {"read_own", "write_own"},  # read_own: the branch manager reads themes
        "supervisor": {"read", "write"},
        "owner": FULL,
        "admin": FULL,
        "agent.sales_supervisor": {"write"},
    },
    "stock_events": {
        "clerk": {"read_own", "write_own"},
        "supervisor": {"read", "write"},
        "owner": FULL,
        "admin": FULL,
        "agent.inventory_manager": FULL,
    },
}


def test_shared_sales_and_stock_tables_keep_exactly_the_rights_they_had() -> None:
    """Data standard 1.5 renamed the tables; the role-by-action table equals the one before the
    rename (no right dropped, none added). A new reader changes this table with its agent."""
    from mia.agents.base import Manifest

    rbac = Rbac(get_settings().config_dir / "policies")
    roles = ["staff", "clerk", "supervisor", "owner", "admin", "viewer", "accountant"]
    agents = Path(__file__).resolve().parent.parent / "mia" / "agents"
    for path in sorted(agents.glob("*/manifest.yaml")):
        spec = Manifest.load(path).roles
        rbac.load_agent_role(spec.agent_role, spec.grants, spec.denies)
        roles.append(spec.agent_role)
    assert len(roles) == 7 + len(list(agents.glob("*/manifest.yaml")))  # every agent role
    got = {
        table: {
            role: {a for a in ACTIONS if rbac.enforcer.enforce(role, "B", f"data:{table}", a)}
            for role in roles
        }
        for table in SHARED_RIGHTS
    }
    want = {t: {r: SHARED_RIGHTS[t].get(r, set()) for r in roles} for t in SHARED_RIGHTS}
    assert got == want
