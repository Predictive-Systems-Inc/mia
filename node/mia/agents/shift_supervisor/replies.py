"""Reply blocks for the Jev decider. Tool results are worded by rules.compose(), the same fi and
en wordings (and variants) as the rules model, so the two paths never drift; reply_only uses
the shared conversation strings."""

from typing import Any

from pydantic_ai.messages import ToolReturnPart

from mia.agents.shift_supervisor.rules import compose
from mia.chat.blocks import Block, TextBlock
from mia.i18n import t

CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
    "capabilities": "conversation.capabilities",
    "send_photos": "reply.send_photos",
    "injection": "fallback.help",  # an instruction in a message is data: offer help, act on nothing
    "other": "fallback.help",
}


def tool_reply(tool: str, out: dict[str, Any], lang: str) -> list[Block]:
    """The reply to one tool result (tool is the name without the agent prefix)."""
    return compose(ToolReturnPart(tool_name=tool, content=out, tool_call_id="jev"), lang)


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action."""
    return [TextBlock(text=t(CONVERSATION_KEYS.get(kind, "fallback.help"), lang))]
