"""Role-based access control with Casbin (pycasbin), branches as domains.

check(actor, resource, action) is called before every tool call. It checks the principal and,
when an agent acts for a person, the on_behalf_of person too: both must be allowed. Ownership
rules: `read_own` or `write_own` allow an action on a resource whose owner is the person.
Every decision is written to the events log when a session is given.
"""

from functools import lru_cache
from pathlib import Path

import casbin
from casbin.util import key_match
from pydantic import BaseModel
from sqlmodel import Session

from mia.core import events
from mia.core.models import Actor, Principal
from mia.settings import get_settings

RISKY_ACTIONS = {"request", "approve"}


class PermissionDenied(Exception):
    """The actor may not perform the action. Carries the principal that failed the check."""

    def __init__(self, principal_id: str, permission: str) -> None:
        super().__init__(f"{principal_id} may not {permission}")
        self.principal_id = principal_id
        self.permission = permission


class Resource(BaseModel):
    """What is being accessed: kind (data, tool) plus name, and optionally its owner person."""

    kind: str
    name: str
    owner_id: str | None = None

    @property
    def obj(self) -> str:
        return f"{self.kind}:{self.name}"


def split_permission(permission: str) -> tuple[str, str]:
    """'tool:dispatcher.get_my_visits:execute' -> ('tool:dispatcher.get_my_visits', 'execute')."""
    obj, _, act = permission.rpartition(":")
    if not obj or not act:
        raise ValueError(f"permission must be kind:resource:action, got {permission!r}")
    return obj, act


class Rbac:
    """A Casbin enforcer plus Mia's rules on top of it."""

    def __init__(self, policy_dir: Path) -> None:
        self.enforcer = casbin.Enforcer(
            str(policy_dir / "model.conf"), str(policy_dir / "policy.csv")
        )
        self.enforcer.add_named_domain_matching_func("g", key_match)
        self.enforcer.build_role_links()

    def load_agent_role(self, role: str, grants: list[str], denies: list[str]) -> None:
        """Register an agent role from its manifest. Wildcards are refused for risky actions."""
        for permission in grants:
            obj, act = split_permission(permission)
            if "*" in obj and act in RISKY_ACTIONS:
                raise ValueError(f"risky permissions must be granted one by one: {permission}")
            if not self.enforcer.has_policy(role, "*", obj, act, "allow"):
                self.enforcer.add_policy(role, "*", obj, act, "allow")
        for permission in denies:
            obj, act = split_permission(permission)
            if not self.enforcer.has_policy(role, "*", obj, act, "deny"):
                self.enforcer.add_policy(role, "*", obj, act, "deny")

    def _role_allows(self, roles: list[str], domain: str, obj: str, act: str) -> bool:
        return any(self.enforcer.enforce(role, domain, obj, act) for role in roles)

    def principal_allowed(
        self, principal: Principal, domain: str, resource: Resource, action: str
    ) -> bool:
        """One principal's decision, including the *_own ownership rule."""
        if self._role_allows(principal.roles, domain, resource.obj, action):
            return True
        if resource.owner_id is not None and resource.owner_id == principal.id:
            return self._role_allows(principal.roles, domain, resource.obj, f"{action}_own")
        return False

    def check(
        self,
        actor: Actor,
        resource: Resource,
        action: str,
        *,
        session: Session | None = None,
        tool_call_id: str | None = None,
    ) -> bool:
        """True when the principal and the on_behalf_of person are both allowed."""
        failed_on: str | None = None
        for principal in [actor.principal, actor.on_behalf_of]:
            if principal is None or principal.type == "system":
                continue
            if not self.principal_allowed(principal, actor.branch_id, resource, action):
                failed_on = principal.id
                break
        allowed = failed_on is None
        if session is not None:
            events.emit(
                session,
                "rbac.allow" if allowed else "rbac.deny",
                ("permission", f"{resource.obj}:{action}"),
                None,
                {
                    "resource": resource.obj,
                    "owner_id": resource.owner_id,
                    "action": action,
                    "allowed": allowed,
                    "failed_on": failed_on,
                },
                actor,
                tool_call_id=tool_call_id,
            )
        return allowed

    def require(
        self,
        actor: Actor,
        resource: Resource,
        action: str,
        *,
        session: Session | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        """Like check(), but raises PermissionDenied."""
        if not self.check(actor, resource, action, session=session, tool_call_id=tool_call_id):
            raise PermissionDenied(actor.principal.id, f"{resource.obj}:{action}")


@lru_cache
def get_rbac() -> Rbac:
    """The node's enforcer, built from config/policies."""
    return Rbac(get_settings().config_dir / "policies")


def check(actor: Actor, resource: Resource, action: str, *, session: Session | None = None) -> bool:
    """Module-level shortcut for get_rbac().check()."""
    return get_rbac().check(actor, resource, action, session=session)
