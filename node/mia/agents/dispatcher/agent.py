"""The dispatcher agent, assembled from its manifest by mia.agents.base."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from pydantic_ai import Agent, RunContext, TextOutput

from mia.agents.base import AgentDeps, Manifest, build_agent, build_model
from mia.agents.dispatcher import cover
from mia.agents.dispatcher.rules import rules_model
from mia.agents.dispatcher.tools import BINDINGS
from mia.chat.blocks import AgentReply, TextBlock
from mia.settings import get_settings

AGENT_DIR = Path(__file__).resolve().parent
MANIFEST = Manifest.load(AGENT_DIR / "manifest.yaml")


def text_reply(text: str) -> AgentReply:
    """A plain-text answer becomes one text block (small models often skip the reply tool)."""
    return AgentReply(blocks=[TextBlock(text=text)])


def create_agent(
    model_name: str | None = None,
    org: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Agent[AgentDeps, Any]:
    """A new dispatcher agent for the given model (default settings.MIA_MODEL)."""
    settings = get_settings()
    model = build_model(model_name or settings.MIA_MODEL, rules_model(), transport=transport)
    return build_agent(
        MANIFEST,
        AGENT_DIR,
        BINDINGS,
        [AgentReply, TextOutput(text_reply)],
        model,
        org or settings.MIA_ORG,
        context=[open_cover_request, classified_intent],
    )


def classified_intent(ctx: RunContext[AgentDeps]) -> str:
    """Task context: the role classifier's reading of the latest message, if confident.

    A hint only: tools still check permissions, and a misread message must not trigger a write.
    """
    if ctx.deps.intent is None:
        return ""
    return (
        f"Classifier: the message is {ctx.deps.intent}; "
        "act on that unless the message says otherwise."
    )


def open_cover_request(ctx: RunContext[AgentDeps]) -> str:
    """Task context: the cover request this user may be answering (see cover.open_request_line)."""
    d = ctx.deps
    return cover.open_request_line(d.session, d.person, d.branch.timezone)


@lru_cache
def get_agent() -> Agent[AgentDeps, Any]:
    """The process-wide dispatcher (tests call get_agent.cache_clear())."""
    return create_agent()
