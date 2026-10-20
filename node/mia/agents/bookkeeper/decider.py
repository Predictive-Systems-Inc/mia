"""Ask Jev which bookkeeper action a message wants and with which inputs (see
mia.agents.decider). decide() runs no tool."""

from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.bookkeeper.actions import ACTIONS, CONVERSATION, Query, build_request
from mia.agents.decider import Decision, Reader


def _args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required input that is missing, if any."""
    if action == "reply_only":
        return {"kind": r.pick("conversation", set(CONVERSATION)) or "other"}, None
    return {}, None  # clarify


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for an answer outside the options) when no usable answer came."""
    parse = partial(shared.parse, q=q, actions=ACTIONS, args=_args)
    return await shared.decide(q, build_request=build_request, parse=parse)
