"""WhatsApp Cloud API adapter: request bodies, webhook parsing, templates, transport."""

import asyncio
import datetime as dt
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


def test_fil_and_ceb_templates_are_sent_only_once_approved(
    wa: WhatsAppAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fil and ceb are registered (drafts in docs/whatsapp-setup.md) but Meta must approve them
    first: until MIA_WA_TEMPLATE_LANGS lists them, a fil call falls back to an approved one."""
    call = TemplateCall(name="mia_new_message", lang="fil")
    assert wa.render_template(ADDR, call).body["template"]["language"] == {"code": "fi"}
    monkeypatch.setenv("MIA_WA_TEMPLATE_LANGS", "fil,ceb")
    get_settings.cache_clear()
    approved = WhatsAppAdapter(get_settings())
    assert approved.render_template(ADDR, call).body["template"]["language"] == {"code": "fil"}
    ceb = TemplateCall(name="mia_login_code", lang="ceb", params=["123456"])
    assert approved.render_template(ADDR, ceb).body["template"]["language"] == {"code": "ceb"}
    english = TemplateCall(name="mia_new_message", lang="en")  # not approved on this number
    assert approved.render_template(ADDR, english).body["template"]["language"] == {"code": "fil"}


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


def test_image_message_carries_the_media_id(wa: WhatsAppAdapter) -> None:
    (m,) = wa.receive(SAMPLES.joinpath("inbound_image.json").read_bytes())
    assert isinstance(m, InboundMessage)
    assert (m.has_media, m.media_id, m.media_kind) == (True, "MEDIA_ID", "image")


def test_fetch_media_resolves_the_url_then_downloads(wa: WhatsAppAdapter) -> None:
    import asyncio

    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("authorization")))
        if request.url.path.endswith("/MEDIA_ID"):
            return httpx.Response(
                200, json={"url": "https://lookaside.fbsbx.com/whatsapp/file.jpg", "file_size": 9}
            )
        return httpx.Response(200, content=b"JPEGBYTES")

    from mia.channels import transport

    adapter = _wa_with(httpx.MockTransport(handler))
    with pytest.raises(transport.ChannelBlocked):  # outside fetching(): rule 6 holds
        asyncio.run(adapter.fetch_media("MEDIA_ID"))
    with transport.fetching("inbound-1"):
        assert asyncio.run(adapter.fetch_media("MEDIA_ID")) == b"JPEGBYTES"
    assert len(seen) == 2 and all(auth == "Bearer tok" for _, auth in seen)
    assert (
        seen[0][0].endswith("/MEDIA_ID")
        and seen[1][0] == "https://lookaside.fbsbx.com/whatsapp/file.jpg"
    )

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with transport.fetching("inbound-2"):
        assert asyncio.run(_wa_with(httpx.MockTransport(broken)).fetch_media("MEDIA_ID")) is None


@pytest.mark.parametrize(
    ("meta", "why"),
    [
        (
            {"url": "https://evil.example/file.jpg", "file_size": 9},
            "an off-domain host never sees the token",
        ),
        ({"url": "http://lookaside.fbsbx.com/file.jpg", "file_size": 9}, "plain http is refused"),
        (
            {"url": "https://lookaside.fbsbx.com/file.jpg", "file_size": 10**9},
            "too large by the metadata",
        ),
    ],
)
def test_fetch_media_refuses_unsafe_metadata(
    wa: WhatsAppAdapter, meta: dict[str, object], why: str
) -> None:
    import asyncio

    from mia.channels import transport

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path.endswith("/MEDIA_ID"):
            return httpx.Response(200, json=meta)
        return httpx.Response(200, content=b"x")

    with transport.fetching("i"):
        assert (
            asyncio.run(_wa_with(httpx.MockTransport(handler)).fetch_media("MEDIA_ID")) is None
        ), why
    assert len(seen) == 1, why  # the second GET never happens


def test_fetch_media_refuses_a_crafted_id_and_an_oversized_body(wa: WhatsAppAdapter) -> None:
    import asyncio

    from mia.channels import transport

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/MEDIA_ID"):
            return httpx.Response(
                200, json={"url": "https://lookaside.fbsbx.com/f.jpg", "file_size": 9}
            )
        return httpx.Response(200, content=b"x" * (wa.MAX_MEDIA_BYTES + 1))

    adapter = _wa_with(httpx.MockTransport(handler))
    with transport.fetching("i"):
        assert asyncio.run(adapter.fetch_media("../PNID/messages")) is None
        assert asyncio.run(adapter.fetch_media("MEDIA_ID")) is None  # the body lied about its size


def test_location_message_carries_coordinates(wa: WhatsAppAdapter) -> None:
    (m,) = wa.receive(SAMPLES.joinpath("inbound_location.json").read_bytes())
    assert isinstance(m, InboundMessage)
    assert (m.lat, m.lon, m.has_media, m.text) == (60.169, 24.932, False, "")


@pytest.mark.parametrize("latitude", ['"abc"', "1e400", "91", "true"])
def test_crafted_coordinates_are_dropped_not_crashed(wa: WhatsAppAdapter, latitude: str) -> None:
    sample = (
        SAMPLES.joinpath("inbound_location.json")
        .read_text()
        .replace('"latitude": 60.169', f'"latitude": {latitude}')
    )
    (m,) = wa.receive(sample.encode())
    assert isinstance(m, InboundMessage)
    assert (m.lat, m.lon, m.has_media) == (None, None, False)


def test_a_place_with_a_name_is_a_picked_place(wa: WhatsAppAdapter) -> None:
    (m,) = wa.receive(SAMPLES.joinpath("inbound_location.json").read_bytes())
    assert isinstance(m, InboundMessage) and m.picked_place
    bare = (
        SAMPLES.joinpath("inbound_location.json")
        .read_text()
        .replace(', "name": "Kamppi", "address": "Urho Kekkosen katu 1"', "")
    )
    (m,) = wa.receive(bare.encode())
    assert isinstance(m, InboundMessage) and not m.picked_place


def test_inbound_message_refuses_infinite_coordinates() -> None:

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InboundMessage(
            channel="sim",
            address="1",
            channel_message_id="1",
            received_at=dt.datetime.now(dt.UTC),
            lat=float("inf"),
            lon=0.0,
        )
