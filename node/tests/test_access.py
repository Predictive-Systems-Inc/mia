import asyncio

import pytest
from sqlmodel import Session

from mia import i18n
from mia.agents import stubs
from mia.agents.base import AgentSpec, Turn
from mia.agents.registry import AGENTS, BUILT
from mia.agents.stubs import STUBS
from mia.chat import service
from mia.chat.access import agents_for
from mia.core import orgconfig
from mia.core.models import Person
from mia.i18n import t

ROSTER = list(AGENTS)  # built agents and stubs: a scaffolded agent needs no edit here
# The org the per-role tests run: the six agents whose policy lines they assert.
SIX = [
    "sales_supervisor",
    "shift_supervisor",
    "inventory_manager",
    "bookkeeper",
    "hr_officer",
    "branch_manager",
]
# The HR officer serves every employee (staff and up), so it joins each list below; the branch
# manager coaches the sales staff, so clerks and supervisors get it too. The bookkeeper serves
# head staff and up (supervisor, owner, admin), never a clerk.
SALES_SHIFT_STOCK = [
    "sales_supervisor",
    "shift_supervisor",
    "inventory_manager",
    "hr_officer",
    "branch_manager",
]
STAFF_AGENTS = ["shift_supervisor", "hr_officer"]


def _run_org(monkeypatch: pytest.MonkeyPatch, agents: list[str]) -> None:
    monkeypatch.setattr(orgconfig, "load", lambda org=None: orgconfig.OrgSettings(agents=agents))


@pytest.fixture
def all_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_org(monkeypatch, SIX)


def _ids(session: Session, person: Person) -> list[str]:
    return [a.id for a in agents_for(session, person)]


def test_the_roster_is_registered() -> None:
    assert set(SIX) <= set(AGENTS)


def test_by_default_everyone_has_only_the_shift_supervisor(
    session: Session, people: dict[str, Person]
) -> None:
    assert _ids(session, people["Helena"]) == ["shift_supervisor"]
    assert _ids(session, people["Juha"]) == ["shift_supervisor"]


def test_access_per_role(session: Session, people: dict[str, Person], all_enabled: None) -> None:
    assert _ids(session, people["Helena"]) == SIX  # owner: all six
    assert _ids(session, people["Sanna"]) == SIX  # supervisor: the clerk's five and the bookkeeper
    assert _ids(session, people["Juha"]) == STAFF_AGENTS  # staff


def test_a_clerk_gets_sales_shift_and_inventory(
    session: Session, people: dict[str, Person], all_enabled: None
) -> None:
    juha = people["Juha"]
    clerk = Person(name=juha.name, branch_id=juha.branch_id, roles=["clerk"])
    assert _ids(session, clerk) == SALES_SHIFT_STOCK


def test_an_agent_the_org_does_not_run_is_never_offered(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_org(monkeypatch, ["bookkeeper", "nonexistent"])
    assert _ids(session, people["Juha"]) == []  # staff may not use the bookkeeper
    assert _ids(session, people["Helena"]) == ["bookkeeper"]  # unknown ids are skipped


def test_a_stub_answers_that_it_is_not_available(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert {s.id for s in STUBS} == set(ROSTER) - {s.id for s in BUILT}
    assert all(s.router_description and s.run_due is None for s in STUBS)
    test_stub = AgentSpec(  # every roster agent is built: a test stub in STUBS
        manifest=stubs._manifest("test_stub"),
        label_key="agent.test_stub.label",
        router_description="A test stub",
        handle_turn=stubs._not_built,
    )
    monkeypatch.setattr(stubs, "STUBS", [*STUBS, test_stub])

    person = people["Juha"]
    thread, past, deps, ctx = service._prepare(session, person, "how many did we sell?", None)
    stub = stubs.STUBS[-1]
    deps.manifest = stub.manifest
    reply = asyncio.run(stub.handle_turn(Turn(session, deps, thread, "hi", past, ctx)))
    assert reply.text() == t("reply.not_built", person.language) != t("reply.not_built", "en")
    assert "reply.not_built" in i18n.NEW_KEYS  # every language has it


def test_ferinos_clerks_are_offered_what_the_policy_lets_them_use(
    session: Session, ferinos: tuple[object, dict[str, Person]]
) -> None:
    """Smoke test 21 Oct: Ana, Liza and Pao were offered Branch Manager and HR Officer. That
    is the policy: the hr officer spec (section 3, staff and clerk request leave and ask their
    payslip) and the branch manager spec (section 3, a clerk asks how to sell more and reads
    their own numbers; Policy: agent:branch_manager use for clerk). Never the bookkeeper (head
    staff and up) or the production planner (denied to clerks); the offer is exactly the
    agents of the org the clerk may use."""
    from mia.core.models import Actor
    from mia.core.rbac import Resource, get_rbac

    _, people = ferinos
    rbac = get_rbac()
    for name in ("Ana", "Liza", "Pao"):
        clerk = people[name]
        offered = _ids(session, clerk)
        may = [
            a
            for a in orgconfig.load().agents
            if rbac.check(Actor.person(clerk), Resource(kind="agent", name=a), "use")
        ]
        assert offered == may
        assert {"hr_officer", "branch_manager"} <= set(offered)
        assert not {"bookkeeper", "production_planner"} & set(offered)


def test_only_admin_and_owner_are_offered_the_people_tools() -> None:
    """Q117: adding a user and linking a number are admin tools; the owner inherits admin."""
    from mia.core.models import Actor
    from mia.core.people import HUMAN_ROLES
    from mia.core.rbac import Resource, get_rbac

    for tool in ("add_person", "set_phone"):
        res = Resource(kind="tool", name=f"branch_manager.{tool}")
        may = {
            r
            for r in HUMAN_ROLES
            if get_rbac().check(
                Actor.person(Person(name="x", roles=[r], branch_id="b")), res, "execute"
            )
        }
        assert may == {"owner", "admin"}, tool
