"""Shared fallback rendering: Mia blocks to what a channel can show."""

from mia.channels.base import ChannelCapabilities
from mia.channels.render import ButtonsPart, ListPart, TextPart, to_parts
from mia.chat.blocks import (
    ApprovalCardBlock,
    Block,
    CardBlock,
    CardField,
    FileBlock,
    QuickRepliesBlock,
    TextBlock,
)

RICH = ChannelCapabilities(
    max_text=50,
    max_buttons=3,
    max_button_label=20,
    max_list_rows=10,
    max_list_label=24,
    session_window_hours=24,
    supports_templates=True,
)
TEXT_ONLY = RICH.model_copy(update={"max_text": 1600, "max_buttons": 0, "max_list_rows": 0})
WIDE = RICH.model_copy(update={"max_text": 4096})


def test_up_to_three_options_become_buttons_on_the_preceding_text() -> None:
    blocks: list[Block] = [
        TextBlock(text="Kaikki vai aamu?"),
        QuickRepliesBlock(options=["Kaikki", "Vain aamu"]),
    ]
    assert to_parts(blocks, RICH, "fi") == [
        ButtonsPart(text="Kaikki vai aamu?", buttons=["Kaikki", "Vain aamu"])
    ]


def test_button_labels_are_cut_to_the_channel_limit() -> None:
    blocks: list[Block] = [TextBlock(text="?"), QuickRepliesBlock(options=["x" * 30])]
    (part,) = to_parts(blocks, RICH, "en")
    assert isinstance(part, ButtonsPart) and part.buttons == ["x" * 20]


def test_four_to_ten_options_become_a_list() -> None:
    options = ["a", "b", "c", "d", "e"]
    blocks: list[Block] = [TextBlock(text="Pick"), QuickRepliesBlock(options=options)]
    assert to_parts(blocks, RICH, "en") == [ListPart(text="Pick", rows=options, button="Choose")]


def test_text_only_channel_gets_numbered_options() -> None:
    blocks: list[Block] = [TextBlock(text="Pick"), QuickRepliesBlock(options=["Yes", "No"])]
    (part,) = to_parts(blocks, TEXT_ONLY, "en")
    assert isinstance(part, TextPart)
    assert "1. Yes" in part.text and "2. No" in part.text and "number" in part.text


def test_long_text_is_split_at_the_channel_limit() -> None:
    parts = to_parts([TextBlock(text="word " * 30)], RICH, "en")
    assert len(parts) > 1
    assert all(isinstance(p, TextPart) and len(p.text) <= 50 for p in parts)
    assert " ".join(p.text for p in parts if isinstance(p, TextPart)).split() == ["word"] * 30


def test_card_becomes_bold_title_and_field_lines() -> None:
    card = CardBlock(title="Kamppi", fields=[CardField(label="Klo", value="09:00")])
    assert to_parts([card], RICH, "fi") == [TextPart(text="*Kamppi*\nKlo: 09:00")]


def test_approval_card_is_a_link_never_buttons() -> None:
    card = ApprovalCardBlock(approval_id="A1", title="Hyväksyntä", summary="Liisa Kampissa")
    parts = to_parts([card, QuickRepliesBlock(options=["Approve"])], RICH, "en")
    assert not any(isinstance(p, ButtonsPart | ListPart) for p in parts)
    text = " ".join(p.text for p in parts if isinstance(p, TextPart))
    assert "Liisa Kampissa" in text and "/approvals/A1" in text


def test_file_becomes_an_app_link() -> None:
    (part,) = to_parts([FileBlock(name="p.pdf", url="/files/p.pdf")], WIDE, "en")
    assert isinstance(part, TextPart) and "/files/p.pdf" in part.text


def test_sensitive_message_carries_no_content() -> None:
    blocks: list[Block] = [TextBlock(text="Palkka 2 345,00 EUR")]
    (part,) = to_parts(blocks, WIDE, "fi", sensitive=True)
    assert isinstance(part, TextPart) and "2 345" not in part.text and "http" in part.text
