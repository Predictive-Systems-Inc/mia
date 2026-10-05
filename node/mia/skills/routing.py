"""Decide what one turn does from its classification (spec section 7)."""

from functools import cache
from typing import Literal

from pydantic import BaseModel, Field

from mia.learning import catalogue
from mia.learning.schema import RoleSpec
from mia.skills.runtime import Classification


class Route(BaseModel):
    kind: Literal["emergency", "template", "agent", "clarify"]
    intent: str | None = None
    options: list[str] = Field(default_factory=list)


@cache
def _conversation_handling() -> dict[str, str]:
    return {ci.id: ci.handling for ci in catalogue.conversation_intents()}


_NOT_OFFERED = {"decline_redirect", "handoff", "emergency"}


def _clarify_options(c: Classification, role: RoleSpec) -> list[str]:
    """Up to 3 alternatives a user may pick: role intents and offerable conversation intents."""
    handling = _conversation_handling()

    def offered(intent: str) -> bool:
        if intent.startswith("conversation."):
            return intent in handling and handling[intent] not in _NOT_OFFERED
        return role.intent(intent) is not None

    return [a.intent for a in c.alternatives if offered(a.intent)][:3]


def route(c: Classification, role: RoleSpec | None, safety_floor: float = 0.2) -> Route:
    """Return the turn's route. Safety wins; "other", decline_redirect intents and a missing role
    plan never template or act (agent with no intent); conversation.* ids resolve against the
    catalogue only, so a role cannot shadow them."""
    if c.safety >= safety_floor:
        return Route(kind="emergency", intent=c.intent)
    handling = _conversation_handling()
    if role is None or c.intent == "other" or handling.get(c.intent) == "decline_redirect":
        return Route(kind="agent")
    if c.band == "medium":
        options = _clarify_options(c, role)
        return Route(kind="clarify", options=options) if options else Route(kind="agent")
    if c.band == "high":
        if c.intent.startswith("conversation."):
            template = handling.get(c.intent) == "template"
        else:
            spec = role.intent(c.intent)
            template = spec is not None and spec.handler == "template"
        return Route(kind="template" if template else "agent", intent=c.intent)
    return Route(kind="agent")
