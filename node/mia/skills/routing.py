"""Decide what one turn does from its classification (spec section 7)."""

from typing import Literal

from pydantic import BaseModel, Field

from mia.learning import catalogue
from mia.learning.schema import RoleSpec
from mia.skills.runtime import Classification


class Route(BaseModel):
    kind: Literal["emergency", "template", "agent", "clarify"]
    intent: str | None = None
    options: list[str] = Field(default_factory=list)


def _conversation_handling() -> dict[str, str]:
    return {ci.id: ci.handling for ci in catalogue.conversation_intents()}


def route(c: Classification, role: RoleSpec | None, safety_floor: float = 0.2) -> Route:
    """Return the turn's route: safety first, "other" and a missing role plan never template."""
    if c.safety >= safety_floor:
        return Route(kind="emergency", intent=c.intent)
    if role is None or c.intent == "other":
        return Route(kind="agent")
    if c.band == "medium":
        options = [a.intent for a in c.alternatives if a.intent != "other"][:3]
        return Route(kind="clarify", options=options) if options else Route(kind="agent")
    if c.band == "low":
        return Route(kind="agent")
    spec = role.intent(c.intent)
    template = (spec is not None and spec.handler == "template") or (
        spec is None and _conversation_handling().get(c.intent) == "template"
    )
    return Route(kind="template" if template else "agent", intent=c.intent)
