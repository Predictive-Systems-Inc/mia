"""Find a role's approved plan next to its agent (node/mia/agents/<role>/skill/role.yaml)."""

from functools import lru_cache
from pathlib import Path

from mia.learning.schema import RoleSpec, load_role

AGENTS = Path(__file__).resolve().parent.parent / "agents"


@lru_cache
def load_role_plan(role_id: str) -> RoleSpec | None:
    """The role's plan, or None when the role has no skill/role.yaml (cached per process)."""
    path = AGENTS / role_id / "skill" / "role.yaml"
    return load_role(path) if path.exists() else None
