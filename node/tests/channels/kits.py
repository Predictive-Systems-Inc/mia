"""Per-adapter test kits for the shared contract suite. Each kit knows its channel's wire format.

A new adapter passes the contract by adding one kit here and its id to KITS.
"""

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mia.channels.base import ChannelAdapter
from mia.channels.simulator import SimAdapter


@dataclass
class Kit:
    adapter: ChannelAdapter
    inbound: Callable[..., bytes]  # (address, text, msg_id, button=None, media=False) -> body
    status: Callable[..., bytes]  # (msg_id, status, error_code=None) -> body
    sign: Callable[[bytes], dict[str, str]]
    sent: Callable[[], list[dict[str, Any]]]
    extra: dict[str, Any] = field(default_factory=dict)


def _hub_sign(secret: str) -> Callable[[bytes], dict[str, str]]:
    def sign(body: bytes) -> dict[str, str]:
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return {"X-Hub-Signature-256": f"sha256={digest}"}

    return sign


def sim_kit() -> Kit:
    adapter = SimAdapter()

    def inbound(
        address: str, text: str, msg_id: str, button: str | None = None, media: bool = False
    ) -> bytes:
        msg = {"from": address, "id": msg_id, "text": text, "button": button, "media": media}
        return json.dumps({"messages": [msg]}).encode()

    def status(msg_id: str, status: str, error_code: str | None = None) -> bytes:
        return json.dumps(
            {"statuses": [{"id": msg_id, "status": status, "error": error_code}]}
        ).encode()

    return Kit(
        adapter, inbound, status, _hub_sign(adapter.secret), lambda: [p.body for p in adapter.sent]
    )


def whatsapp_kit() -> Kit:
    import httpx

    from mia.channels.whatsapp.adapter import WhatsAppAdapter
    from mia.settings import Settings

    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": f"wamid.{len(sent)}"}]})

    settings = Settings(
        MIA_WA_TOKEN="tok", MIA_WA_APP_SECRET="app-secret", MIA_WA_PHONE_NUMBER_ID="PNID"
    )
    adapter = WhatsAppAdapter(settings, transport=httpx.MockTransport(handler))

    def inbound(
        address: str, text: str, msg_id: str, button: str | None = None, media: bool = False
    ) -> bytes:
        m: dict[str, Any] = {"from": address, "id": msg_id, "timestamp": "1790000000"}
        if media:
            m |= {"type": "image", "image": {"id": "MEDIA"}}
        elif button:
            reply = {"type": "button_reply", "button_reply": {"id": "b0", "title": button}}
            m |= {"type": "interactive", "interactive": reply}
        else:
            m |= {"type": "text", "text": {"body": text}}
        return _wa_envelope({"messages": [m]})

    def status(msg_id: str, status: str, error_code: str | None = None) -> bytes:
        s: dict[str, Any] = {"id": msg_id, "status": status, "recipient_id": "x"}
        if error_code:
            s["errors"] = [{"code": int(error_code)}]
        return _wa_envelope({"statuses": [s]})

    return Kit(adapter, inbound, status, _hub_sign("app-secret"), lambda: sent)


def _wa_envelope(value: dict[str, Any]) -> bytes:
    change = {"field": "messages", "value": {"messaging_product": "whatsapp", **value}}
    envelope = {"object": "whatsapp_business_account", "entry": [{"id": "W", "changes": [change]}]}
    return json.dumps(envelope).encode()


KITS: dict[str, Callable[[], Kit]] = {"sim": sim_kit, "whatsapp": whatsapp_kit}
