"""Every agent the node can run, by id. The chat finds an agent's turn, label and due work
here, so no chat code imports a specific agent."""

from mia.agents.base import AgentSpec
from mia.agents.shift_supervisor.turn import SPEC as SHIFT_SUPERVISOR

AGENTS: dict[str, AgentSpec] = {SHIFT_SUPERVISOR.id: SHIFT_SUPERVISOR}
DEFAULT = SHIFT_SUPERVISOR.id  # ponytail: the agent of a new thread until routing (Task 6)
