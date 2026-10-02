"""WhatsApp Cloud API adapter: request bodies, webhook parsing, templates, transport."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from mia.channels.base import ChannelPayload, InboundMessage, StatusUpdate, TemplateCall
from mia.channels.render import ButtonsPart, ListPart, TextPart
from mia.channels.transport import ChannelBlocked, sending
from mia.channels.whatsapp.adapter import WhatsAppAdapter
from mia.settings import get_settings

SAMPLES = Path(__file__).parent / "whatsapp_samples"
ADDR = "358401234567"


def sample(name: str) -> bytes:
    return (SAMPLES / f"{name}.json").read_bytes()


@pytest.fixture
def wa(monkeypatch: pytest.MonkeyPatch) -> WhatsAppAdapter:
    for k, v in {
        "MIA_WA_TOKEN": "tok",
        "MIA_WA_APP_SECRET": "app-secret",
        "MIA_WA_VERIFY_TOKEN": "verify-me",
        "MIA_WA_PHONE_NUMBER_ID": "PNID",
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return WhatsAppAdapter(get_settings())


def test_text_payload(wa: WhatsAppAdapter) -> None:
    (p,) = wa.render(ADDR, [TextPart(text="Hei")])
    assert p.body == {
        "messaging_product": "whatsapp",
        "to": ADDR,
        "type": "text",
        "text": {"body": "Hei"},
    }


def test_buttons_payload(wa: WhatsAppAdapter) -> None:
    (p,) = wa.render(ADDR, [ButtonsPart(text="Kaikki vai aamu?", buttons=["Kaikki", "Vain aamu"])])
    assert p.body["type"] == "interactive"
    inter = p.body["interactive"]
    assert inter["type"] == "button" and inter["body"] == {"text": "Kaikki vai aamu?"}
    assert inter["action"]["buttons"] == [
        {"type": "reply", "reply": {"id": "b0", "title": "Kaikki"}},
        {"type": "reply", "reply": {"id": "b1", "title": "Vain aamu"}},
    ]


def test_list_payload(wa: WhatsAppAdapter) -> None:
    (p,) = wa.render(ADDR, [ListPart(text="Valitse", rows=["a", "b", "c", "d"])])
    action = p.body["interactive"]["action"]
    assert p.body["interactive"]["type"] == "list"
    assert action["sections"][0]["rows"][3] == {"id": "r3", "title": "d"}
    assert action["button"]


def test_template_payload(wa: WhatsAppAdapter) -> None:
    call = TemplateCall(
        name="mia_cover_request", lang="fi", params=["Mikael", "Kamppi", "6.10.", "09:00"]
    )
    p = wa.render_template(ADDR, call)
    assert p.body["type"] == "template"
    tpl = p.body["template"]
    assert tpl["name"] == "mia_cover_request" and tpl["language"] == {"code": "fi"}
    assert [x["text"] for x in tpl["components"][0]["parameters"]] == [
        "Mikael",
        "Kamppi",
        "6.10.",
        "09:00",
    ]


def test_template_without_params_has_no_components(wa: WhatsAppAdapter) -> None:
    p = wa.render_template(ADDR, TemplateCall(name="mia_new_message", lang="en"))
    assert p.body["template"] == {"name": "mia_new_message", "language": {"code": "en"}}


@pytest.mark.parametrize(
    "call",
    [
        TemplateCall(name="mia_marketing", lang="fi"),
        TemplateCall(name="mia_cover_request", lang="fi", params=["only one"]),
    ],
)
def test_unknown_template_or_wrong_params_refused(wa: WhatsAppAdapter, call: TemplateCall) -> None:
    with pytest.raises(ValueError):
        wa.render_template(ADDR, call)


@pytest.mark.parametrize(
    ("name", "text", "button", "media"),
    [
        ("inbound_text", "Olen kipeä huomenna.", None, False),
        ("inbound_button_reply", "", "Kaikki", False),
        ("inbound_list_reply", "", "Mikael Nieminen", False),
        ("inbound_template_button", "", "Hyväksyn", False),
        ("inbound_image", "", None, True),
    ],
)
def test_receive_inbound_shapes(
    wa: WhatsAppAdapter, name: str, text: str, button: str | None, media: bool
) -> None:
    (m,) = wa.receive(sample(name))
    assert isinstance(m, InboundMessage)
    assert (m.channel, m.address, m.text, m.button, m.has_media) == (
        "whatsapp",
        ADDR,
        text,
        button,
        media,
    )
    assert m.received_at.year == 2026


def test_receive_failed_status(wa: WhatsAppAdapter) -> None:
    (s,) = wa.receive(sample("status_failed"))
    assert isinstance(s, StatusUpdate)
    assert (s.channel_message_id, s.status, s.error_code) == ("wamid.S1", "failed", "131047")


def test_subscription_handshake(wa: WhatsAppAdapter) -> None:
    ok = {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "7"}
    assert wa.verify_subscription(ok) == "7"
    assert wa.verify_subscription({**ok, "hub.verify_token": "x"}) is None


def _wa_with(handler: httpx.MockTransport) -> WhatsAppAdapter:
    return WhatsAppAdapter(get_settings(), transport=handler)


def test_send_posts_to_graph_api_and_returns_message_id(wa: WhatsAppAdapter) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}]})

    adapter = _wa_with(httpx.MockTransport(handler))
    payload = ChannelPayload(channel="whatsapp", address=ADDR, body={"type": "text"})
    with sending("t1"):
        result = asyncio.run(adapter.send(payload))
    assert result.ok and result.channel_message_id == "wamid.OUT"
    (req,) = seen
    assert str(req.url) == "https://graph.facebook.com/v26.0/PNID/messages"
    assert req.headers["authorization"] == "Bearer tok"
    assert json.loads(req.content) == {"type": "text"}


def test_send_error_returns_the_meta_code(wa: WhatsAppAdapter) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 131047, "message": "outside window"}})

    adapter = _wa_with(httpx.MockTransport(handler))
    with sending("t1"):
        result = asyncio.run(
            adapter.send(ChannelPayload(channel="whatsapp", address=ADDR, body={}))
        )
    assert (result.ok, result.error_code) == (False, "131047")


def test_network_error_is_a_result_not_an_exception(wa: WhatsAppAdapter) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    adapter = _wa_with(httpx.MockTransport(handler))
    with sending("t1"):
        result = asyncio.run(
            adapter.send(ChannelPayload(channel="whatsapp", address=ADDR, body={}))
        )
    assert (result.ok, result.error_code) == (False, "network")


def test_send_outside_the_outbox_is_blocked(wa: WhatsAppAdapter) -> None:
    adapter = _wa_with(httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(ChannelBlocked):
        asyncio.run(adapter.send(ChannelPayload(channel="whatsapp", address=ADDR, body={})))


def test_registered_only_when_configured(
    wa: WhatsAppAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia.channels import registry
    from mia.channels.whatsapp import register_if_configured

    saved = dict(registry._adapters)
    try:
        registry._adapters.clear()
        assert register_if_configured(get_settings()) is True
        assert registry.get("whatsapp").channel_id == "whatsapp"
        registry._adapters.clear()
        monkeypatch.setenv("MIA_WA_TOKEN", "")
        get_settings.cache_clear()
        assert register_if_configured(get_settings()) is False
        assert "whatsapp" not in registry._adapters
    finally:
        registry._adapters.clear()
        registry._adapters.update(saved)


def test_server_start_registers_whatsapp_when_configured(wa: WhatsAppAdapter) -> None:
    from fastapi.testclient import TestClient

    from mia.api.main import app
    from mia.channels import registry

    saved = dict(registry._adapters)
    try:
        registry._adapters.clear()
        with TestClient(app):
            assert "whatsapp" in registry._adapters
    finally:
        registry._adapters.clear()
        registry._adapters.update(saved)
