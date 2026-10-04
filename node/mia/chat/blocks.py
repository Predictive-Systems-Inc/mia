"""Structured reply blocks. Agents answer with these; the apps render them."""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class QuickRepliesBlock(BaseModel):
    type: Literal["quick_replies"] = "quick_replies"
    options: list[str] = Field(max_length=6)


class CardField(BaseModel):
    label: str
    value: str


class CardBlock(BaseModel):
    type: Literal["card"] = "card"
    title: str
    subtitle: str | None = None
    fields: list[CardField] = Field(default_factory=list)


class ApprovalCardBlock(BaseModel):
    type: Literal["approval_card"] = "approval_card"
    approval_id: str
    title: str
    summary: str
    fields: list[CardField] = Field(default_factory=list)
    status: str = "pending"


class FormField(BaseModel):
    name: str
    label: str
    kind: Literal["text", "date", "time", "number", "choice"] = "text"
    choices: list[str] = Field(default_factory=list)
    required: bool = True


class FormBlock(BaseModel):
    type: Literal["form"] = "form"
    form_id: str
    title: str
    fields: list[FormField]


class FileBlock(BaseModel):
    type: Literal["file"] = "file"
    name: str
    url: str
    mime: str = "application/octet-stream"


Block = Annotated[
    TextBlock | QuickRepliesBlock | CardBlock | ApprovalCardBlock | FormBlock | FileBlock,
    Field(discriminator="type"),
]


# Block tags by key: the tag itself, the class name, and the field only that block has.
TAGS = {
    "text": "text",
    "textblock": "text",
    "quick_replies": "quick_replies",
    "quickrepliesblock": "quick_replies",
    "options": "quick_replies",
    "card": "card",
    "cardblock": "card",
    "approval_card": "approval_card",
    "approvalcardblock": "approval_card",
    "approval_id": "approval_card",
    "form": "form",
    "formblock": "form",
    "form_id": "form",
    "file": "file",
    "fileblock": "file",
    "url": "file",
}


def _decoded(value: Any) -> Any:
    """A JSON object or list sent as a string, decoded; anything else unchanged."""
    if isinstance(value, str) and value.strip()[:1] in ("{", "["):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _normalised_block(block: Any) -> Any:
    """Translate the block shapes small models produce into the tagged form.

    Handles a class name as the tag ("TextBlock"), a missing tag (inferred from the field only
    that block has), the block wrapped under its tag ({"card": {...}}) and JSON sent as a
    string. Anything else is returned unchanged and fails validation as before.
    """
    block = _decoded(block)
    if isinstance(block, str):
        return {"type": "text", "text": block}
    if not isinstance(block, dict):
        return block
    tag = block.get("type")
    if isinstance(tag, str) and tag.lower() in TAGS:
        return {**block, "type": TAGS[tag.lower()]}
    if tag is None and len(block) == 1:
        ((key, inner),) = block.items()
        inner = _decoded(inner)
        if key in TAGS and isinstance(inner, dict):
            return {**inner, "type": TAGS[key]}
    if tag is None:
        for key in block:
            if key in TAGS and key not in ("card", "file", "form"):
                return {**block, "type": TAGS[key]}
        if "title" in block:
            return {**block, "type": "card"}
    return block


class AgentReply(BaseModel):
    """What an agent returns: an ordered list of blocks, shortest useful answer first."""

    blocks: list[Block]

    @model_validator(mode="before")
    @classmethod
    def normalise_blocks(cls, data: Any) -> Any:
        """Accept the near-miss shapes small local models produce (see _normalised_block)."""
        data = _decoded(data)
        if isinstance(data, dict) and isinstance(blocks := _decoded(data.get("blocks")), list):
            return {**data, "blocks": [_normalised_block(b) for b in blocks]}
        return data


class ChatReply(BaseModel):
    """What the chat endpoints return."""

    thread_id: str
    message_id: str
    agent_id: str
    blocks: list[Block]

    def text(self) -> str:
        """Plain text rendering, for the terminal and for text-only channels."""
        lines: list[str] = []
        for block in self.blocks:
            if isinstance(block, TextBlock):
                lines.append(block.text)
            elif isinstance(block, QuickRepliesBlock):
                lines.append("  [" + "] [".join(block.options) + "]")
            elif isinstance(block, CardBlock | ApprovalCardBlock):
                head = f"== {block.title} =="
                if isinstance(block, ApprovalCardBlock):
                    head += f" (approval {block.approval_id}, {block.status})"
                lines.append(head)
                if isinstance(block, CardBlock) and block.subtitle:
                    lines.append(block.subtitle)
                if isinstance(block, ApprovalCardBlock):
                    lines.append(block.summary)
                lines.extend(f"  {f.label}: {f.value}" for f in block.fields)
            elif isinstance(block, FormBlock):
                lines.append(f"== {block.title} == (form)")
            elif isinstance(block, FileBlock):
                lines.append(f"[file] {block.name}: {block.url}")
        return "\n".join(lines)
