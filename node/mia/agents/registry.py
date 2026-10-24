"""Every agent the node can run, by id. The chat finds an agent's turn, label and due work
here, so no chat code imports a specific agent. `mia agent scaffold` adds to BUILT."""

from mia.agents.base import AgentSpec
from mia.agents.bookkeeper.turn import SPEC as BOOKKEEPER
from mia.agents.branch_manager.turn import SPEC as BRANCH_MANAGER
from mia.agents.customer_service.turn import SPEC as CUSTOMER_SERVICE
from mia.agents.hr_officer.turn import SPEC as HR_OFFICER
from mia.agents.inventory_manager.turn import SPEC as INVENTORY_MANAGER
from mia.agents.production_planner.turn import SPEC as PRODUCTION_PLANNER
from mia.agents.sales_supervisor.turn import SPEC as SALES_SUPERVISOR
from mia.agents.shift_supervisor.turn import SPEC as SHIFT_SUPERVISOR
from mia.agents.stubs import STUBS
from mia.core.rbac import get_rbac

BUILT = [
    SHIFT_SUPERVISOR,
    SALES_SUPERVISOR,
    INVENTORY_MANAGER,
    HR_OFFICER,
    CUSTOMER_SERVICE,
    BRANCH_MANAGER,
    BOOKKEEPER,
    PRODUCTION_PLANNER,
]
AGENTS: dict[str, AgentSpec] = {s.id: s for s in [*BUILT, *STUBS]}
DEFAULT = SHIFT_SUPERVISOR.id  # ponytail: the agent of a new thread until routing (Task 6)


def load_roles() -> None:
    """Load every built agent's manifest roles into the node's enforcer, so an approval decided
    outside any turn (its handler re-runs the agent's tool) finds the agent role's grants.
    Idempotent: a grant already loaded is skipped. Called at app startup."""
    rbac = get_rbac()
    for spec in BUILT:
        roles = spec.manifest.roles
        rbac.load_agent_role(roles.agent_role, roles.grants, roles.denies)
