"""Shared fallback rendering: Mia blocks to parts a channel can show (spec, Graceful fallback).

Guarantees: nothing exceeds the channel's capabilities; approval cards, forms and files become
links to the Mia app and never carry decision buttons; a sensitive message becomes a single link
with no content.
"""

from pydantic import BaseModel

from mia.chat.blocks import (
    ApprovalCardBlock,
    Block,
    CardBlock,
    FileBlock,
    FormBlock,
    QuickRepliesBlock,
    TextBlock,
)
from mia.i18n import t
from mia.settings import get_settings


class TextPart(BaseModel):
    text: str


class ButtonsPart(BaseModel):
    text: str
    buttons: list[str]


class ListPart(BaseModel):
    text: str
    rows: list[str]
    button: str = ""  # label of the button that opens the list, in the reader's language


RenderedPart = TextPart | ButtonsPart | ListPart


class _Caps(BaseModel):
    """The subset of ChannelCapabilities rendering needs (avoids an import cycle with base)."""

    max_text: int
    max_buttons: int
    max_button_label: int
    max_list_rows: int
    max_list_label: int


def app_url(path: str) -> str:
    """Absolute link into the Mia app on this node."""
    return get_settings().MIA_PUBLIC_URL.rstrip("/") + path


def split_text(text: str, limit: int) -> list[str]:
    """Split text into chunks of at most `limit` characters, at whitespace where possible."""
    chunks: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit + 1)
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return chunks


def _block_text(block: Block, lang: str) -> str:
    if isinstance(block, TextBlock):
        return block.text
    if isinstance(block, ApprovalCardBlock):
        url = app_url(f"/approvals/{block.approval_id}")
        return f"*{block.title}*\n{block.summary}\n" + t("channel.open_in_app", lang, url=url)
    if isinstance(block, CardBlock):
        lines = [f"*{block.title}*"] + ([block.subtitle] if block.subtitle else [])
        return "\n".join(lines + [f"{f.label}: {f.value}" for f in block.fields])
    if isinstance(block, FileBlock):
        return t("channel.open_in_app", lang, url=app_url(block.url))
    if isinstance(block, FormBlock):
        return t("channel.open_in_app", lang, url=app_url(f"/forms/{block.form_id}"))
    return ""


def to_parts(
    blocks: list[Block], caps: BaseModel, lang: str, *, sensitive: bool = False
) -> list[RenderedPart]:
    """Render blocks within the channel's capabilities, keeping their order."""
    c = _Caps.model_validate(caps, from_attributes=True)
    if sensitive:
        return [TextPart(text=t("channel.sensitive", lang, url=app_url("/")))]
    has_approval = any(isinstance(b, ApprovalCardBlock) for b in blocks)
    parts: list[RenderedPart] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            parts.extend(TextPart(text=x) for x in split_text("\n\n".join(pending), c.max_text))
            pending.clear()

    for block in blocks:
        if not isinstance(block, QuickRepliesBlock):
            text = _block_text(block, lang)
            if text:
                pending.append(text)
            continue
        if has_approval:
            continue  # decisions happen in the app, never on an outside channel
        options = block.options
        body = "\n\n".join(pending) or t("channel.choose", lang)
        pending.clear()
        if 0 < len(options) <= c.max_buttons and len(body) <= c.max_text:
            parts.append(ButtonsPart(text=body, buttons=[o[: c.max_button_label] for o in options]))
        elif 0 < len(options) <= c.max_list_rows and len(body) <= c.max_text:
            rows = [o[: c.max_list_label] for o in options]
            parts.append(ListPart(text=body, rows=rows, button=t("channel.choose", lang)))
        else:
            numbered = "\n".join(f"{i}. {o}" for i, o in enumerate(options, start=1))
            pending.append(f"{body}\n{numbered}\n{t('channel.reply_with_number', lang)}")
    flush()
    return parts
