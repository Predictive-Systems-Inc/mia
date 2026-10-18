"""Reply blocks for the inventory manager: the conversation replies, worded from i18n keys. Code
words every reply; no model writes one."""

from mia.chat.blocks import Block, TextBlock
from mia.i18n import t

# ponytail: reply.not_built stands in for the agent's own capabilities key until it has tools
CAPABILITIES = "reply.not_built"
CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
}


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action: a greeting, thanks or goodbye, else (an
    injection included) what the agent can do; a greeting is followed by what it can do."""
    blocks: list[Block] = [TextBlock(text=t(CONVERSATION_KEYS.get(kind, CAPABILITIES), lang))]
    if kind == "greeting":
        blocks.append(TextBlock(text=t(CAPABILITIES, lang)))
    return blocks
