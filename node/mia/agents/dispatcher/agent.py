"""The dispatcher agent, assembled from its manifest by mia.agents.base."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from pydantic_ai import Agent

from mia.agents.base import AgentDeps, Manifest, build_agent, build_model
from mia.agents.dispatcher.rules import rules_model
from mia.agents.dispatcher.tools import BINDINGS
from mia.chat.blocks import AgentReply
from mia.settings import get_settings

AGENT_DIR = Path(__file__).resolve().parent
MANIFEST = Manifest.load(AGENT_DIR / "manifest.yaml")


def create_agent(
    model_name: str | None = None,
    org: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Agent[AgentDeps, Any]:
    """A new dispatcher agent for the given model (default settings.MIA_MODEL)."""
    settings = get_settings()
    model = build_model(model_name or settings.MIA_MODEL, rules_model(), transport=transport)
    return build_agent(MANIFEST, AGENT_DIR, BINDINGS, AgentReply, model, org or settings.MIA_ORG)


@lru_cache
def get_agent() -> Agent[AgentDeps, Any]:
    """The process-wide dispatcher (tests call get_agent.cache_clear())."""
    return create_agent()
