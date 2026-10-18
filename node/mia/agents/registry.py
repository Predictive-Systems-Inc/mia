"""Every agent the node can run, by id. The chat finds an agent's turn, label and due work
here, so no chat code imports a specific agent. `mia agent scaffold` adds to BUILT."""

from mia.agents.base import AgentSpec
from mia.agents.hr_officer.turn import SPEC as HR_OFFICER
from mia.agents.inventory_manager.turn import SPEC as INVENTORY_MANAGER
from mia.agents.sales_supervisor.turn import SPEC as SALES_SUPERVISOR
from mia.agents.shift_supervisor.turn import SPEC as SHIFT_SUPERVISOR
from mia.agents.stubs import STUBS

BUILT = [
    SHIFT_SUPERVISOR,
    SALES_SUPERVISOR,
    INVENTORY_MANAGER,
    HR_OFFICER,
]
AGENTS: dict[str, AgentSpec] = {s.id: s for s in [*BUILT, *STUBS]}
DEFAULT = SHIFT_SUPERVISOR.id  # ponytail: the agent of a new thread until routing (Task 6)
