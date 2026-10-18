"""Every agent the node can run, by id. The chat finds an agent's turn, label and due work
here, so no chat code imports a specific agent."""

from mia.agents.base import AgentSpec
from mia.agents.shift_supervisor.turn import SPEC as SHIFT_SUPERVISOR
from mia.agents.stubs import STUBS

AGENTS: dict[str, AgentSpec] = {s.id: s for s in [SHIFT_SUPERVISOR, *STUBS]}
DEFAULT = SHIFT_SUPERVISOR.id  # ponytail: the agent of a new thread until routing (Task 6)
