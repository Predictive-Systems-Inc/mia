"""Contract suite: every registered adapter must pass these, whatever its wire format."""

import asyncio

import pytest

from mia.channels.base import InboundMessage, StatusUpdate
from mia.channels.render import to_parts
from mia.channels.transport import sending
from mia.chat.blocks import (
    ApprovalCardBlock,
    Block,
    CardBlock,
    CardField,
    QuickRepliesBlock,
    TextBlock,
)
from tests.channels.kits import KITS, Kit


@pytest.fixture(params=sorted(KITS))
def kit(request: pytest.FixtureRequest) -> Kit:
    return KITS[request.param]()


def test_signed_webhook_verifies(kit: Kit) -> None:
    body = kit.inbound("358401234567", "hei", "m1")
    assert kit.adapter.verify_webhook(kit.sign(body), body)


def test_bad_or_missing_signature_fails(kit: Kit) -> None:
    body = kit.inbound("358401234567", "hei", "m1")
    tampered = kit.inbound("358401234567", "hei!", "m1")
    assert not kit.adapter.verify_webhook(kit.sign(body), tampered)
    assert not kit.adapter.verify_webhook({}, body)
    assert not kit.adapter.verify_webhook({"X-Hub-Signature-256": "sha256=00"}, body)


def test_text_message_parses(kit: Kit) -> None:
    (msg,) = kit.adapter.receive(kit.inbound("358401234567", "Olen kipeä", "m1"))
    assert isinstance(msg, InboundMessage)
    assert (msg.channel, msg.address, msg.channel_message_id, msg.text) == (
        kit.adapter.channel_id,
        "358401234567",
        "m1",
        "Olen kipeä",
    )
    assert msg.button is None and not msg.has_media


def test_button_tap_parses(kit: Kit) -> None:
    (msg,) = kit.adapter.receive(kit.inbound("358401234567", "", "m2", button="Hyväksyn"))
    assert isinstance(msg, InboundMessage) and msg.button == "Hyväksyn"


def test_media_message_is_flagged(kit: Kit) -> None:
    (msg,) = kit.adapter.receive(kit.inbound("358401234567", "", "m3", media=True))
    assert isinstance(msg, InboundMessage) and msg.has_media


def test_status_parses(kit: Kit) -> None:
    (st,) = kit.adapter.receive(kit.status("wamid.1", "failed", "131047"))
    assert isinstance(st, StatusUpdate)
    assert (st.channel_message_id, st.status, st.error_code) == ("wamid.1", "failed", "131047")


def test_every_block_type_renders_to_payloads(kit: Kit) -> None:
    blocks: list[Block] = [
        TextBlock(text="Hei"),
        QuickRepliesBlock(options=["Kaikki", "Vain aamu"]),
        CardBlock(title="Kamppi", fields=[CardField(label="Klo", value="9:00")]),
        ApprovalCardBlock(approval_id="A1", title="Hyväksyntä", summary="Liisa"),
    ]
    parts = to_parts(blocks, kit.adapter.capabilities, "fi")
    payloads = kit.adapter.render("358401234567", parts)
    assert len(payloads) == len(parts)
    assert all(
        p.channel == kit.adapter.channel_id and p.address == "358401234567" for p in payloads
    )


def test_send_returns_a_channel_message_id(kit: Kit) -> None:
    (payload,) = kit.adapter.render(
        "358401234567", to_parts([TextBlock(text="Hei")], kit.adapter.capabilities, "fi")
    )
    with sending("contract"):  # adapters send only inside an outbox send
        result = asyncio.run(kit.adapter.send(payload))
    assert result.ok and result.channel_message_id
    assert len(kit.sent()) == 1
