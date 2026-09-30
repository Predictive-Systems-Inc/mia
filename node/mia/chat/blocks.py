"""Structured reply blocks. Agents answer with these; the apps render them."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


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


class AgentReply(BaseModel):
    """What an agent returns: an ordered list of blocks, shortest useful answer first."""

    blocks: list[Block]


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
