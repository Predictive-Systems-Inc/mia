"""Which agents a person can talk to: those their organisation runs (org config `agents`, in
that order) that their roles may use (policy `agent:<id>`, action `use`)."""

from sqlmodel import Session

from mia.agents.base import AgentSpec
from mia.agents.registry import AGENTS
from mia.core import orgconfig
from mia.core.models import Actor, Person
from mia.core.rbac import Resource, get_rbac


def agents_for(session: Session, person: Person) -> list[AgentSpec]:
    """The person's agents in the organisation's order. Unknown ids are skipped. This filters
    what is offered; each tool still runs rbac.require (rule 4)."""
    actor = Actor.person(person)
    rbac = get_rbac()
    return [
        AGENTS[agent_id]
        for agent_id in orgconfig.load().agents
        if agent_id in AGENTS and rbac.check(actor, Resource(kind="agent", name=agent_id), "use")
    ]
