"""Conversation intents shared by every role (greetings, help, safety, privacy, out of scope)."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

PATH = Path(__file__).parent / "catalogue" / "conversation.yaml"


class ConversationIntent(BaseModel):
    id: str
    category: str
    handling: str
    description: str = ""
    examples: list[str] = []


@lru_cache
def conversation_intents() -> list[ConversationIntent]:
    data = yaml.safe_load(PATH.read_text(encoding="utf-8"))
    return [ConversationIntent.model_validate(i) for i in data["intents"]]


def safety_ids() -> set[str]:
    """Intents with the emergency script (spec section 7, step 1)."""
    return {c.id for c in conversation_intents() if c.handling == "emergency"}
