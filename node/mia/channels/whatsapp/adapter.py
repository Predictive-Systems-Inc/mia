"""WhatsApp Business Platform (Meta Cloud API) adapter.

Guarantees: webhooks are accepted only with a valid X-Hub-Signature-256 from the app secret;
requests go out only through ChannelTransport (so only from the outbox); only registered
templates with the right parameter count are sent; channel errors come back as results.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from mia.channels.base import (
    ChannelCapabilities,
    ChannelPayload,
    DeliveryResult,
    InboundMessage,
    StatusUpdate,
    TemplateCall,
)
from mia.channels.render import ButtonsPart, ListPart, RenderedPart
from mia.channels.simulator import hub_signature_ok
from mia.channels.transport import ChannelTransport
from mia.channels.whatsapp.templates import TEMPLATES
from mia.i18n import t
from mia.settings import Settings

CAPABILITIES = ChannelCapabilities(
    max_text=4096,
    max_buttons=3,
    max_button_label=20,
    max_list_rows=10,
    max_list_label=24,
    session_window_hours=24,
    supports_templates=True,
)


class WhatsAppAdapter:
    """One WhatsApp Business phone number on the Meta Cloud API."""

    channel_id = "whatsapp"
    capabilities = CAPABILITIES

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.app_secret = settings.MIA_WA_APP_SECRET
        self.verify_token = settings.MIA_WA_VERIFY_TOKEN
        url = f"{settings.MIA_WA_GRAPH_URL.rstrip('/')}/{settings.MIA_WA_PHONE_NUMBER_ID}/messages"
        self.messages_url = url
        self.client = httpx.AsyncClient(
            transport=ChannelTransport(transport),
            headers={"Authorization": f"Bearer {settings.MIA_WA_TOKEN}"},
            timeout=30,
        )

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        """Valid only with Meta's signature over the raw body."""
        return hub_signature_ok(self.app_secret, headers, body)

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        """Meta's GET handshake: echo hub.challenge when the verify token matches."""
        token_ok = bool(self.verify_token) and params.get("hub.verify_token") == self.verify_token
        if params.get("hub.mode") == "subscribe" and token_ok:
            return params.get("hub.challenge")
        return None

    def receive(self, body: bytes) -> list[InboundMessage | StatusUpdate]:
        """Messages and statuses from every entry and change in the webhook."""
        import json

        data = json.loads(body)
        out: list[InboundMessage | StatusUpdate] = []
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                out.extend(self._message(m) for m in value.get("messages", []))
                out.extend(self._status(s) for s in value.get("statuses", []))
        return out

    def _message(self, m: dict[str, Any]) -> InboundMessage:
        kind = m.get("type")
        text, button, media = "", None, False
        if kind == "text":
            text = m.get("text", {}).get("body", "")
        elif kind == "interactive":
            inter = m.get("interactive", {})
            reply = inter.get("button_reply") or inter.get("list_reply") or {}
            button = reply.get("title")
        elif kind == "button":
            button = m.get("button", {}).get("text")
        else:
            media = True
        return InboundMessage(
            channel=self.channel_id,
            address=m["from"],
            channel_message_id=m["id"],
            text=text,
            button=button,
            has_media=media,
            received_at=datetime.fromtimestamp(int(m.get("timestamp", 0)), UTC),
        )

    def _status(self, s: dict[str, Any]) -> StatusUpdate:
        errors = s.get("errors") or [{}]
        code = errors[0].get("code")
        return StatusUpdate(
            channel=self.channel_id,
            channel_message_id=s["id"],
            status=s["status"],
            error_code=str(code) if code is not None else None,
        )

    def _base(self, address: str) -> dict[str, Any]:
        return {"messaging_product": "whatsapp", "to": address}

    def render(self, address: str, parts: list[RenderedPart]) -> list[ChannelPayload]:
        """Text, reply buttons or a list message per part."""
        out = []
        for part in parts:
            body = self._base(address)
            if isinstance(part, ButtonsPart):
                buttons = [
                    {"type": "reply", "reply": {"id": f"b{i}", "title": label}}
                    for i, label in enumerate(part.buttons)
                ]
                body |= {
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {"text": part.text},
                        "action": {"buttons": buttons},
                    },
                }
            elif isinstance(part, ListPart):
                rows = [{"id": f"r{i}", "title": label} for i, label in enumerate(part.rows)]
                body |= {
                    "type": "interactive",
                    "interactive": {
                        "type": "list",
                        "body": {"text": part.text},
                        "action": {
                            "button": part.button or t("channel.choose", "en"),
                            "sections": [{"rows": rows}],
                        },
                    },
                }
            else:
                body |= {"type": "text", "text": {"body": part.text}}
            out.append(ChannelPayload(channel=self.channel_id, address=address, body=body))
        return out

    def render_template(self, address: str, call: TemplateCall) -> ChannelPayload:
        """A registered template. Raises ValueError for unknown names or wrong parameter counts."""
        spec = TEMPLATES.get(call.name)
        if spec is None:
            raise ValueError(f"template {call.name!r} is not registered")
        if len(call.params) != spec.params:
            raise ValueError(f"template {call.name!r} takes {spec.params} parameters")
        lang = call.lang if call.lang in spec.langs else spec.langs[0]
        template: dict[str, Any] = {"name": call.name, "language": {"code": lang}}
        if call.params:
            params = [{"type": "text", "text": p} for p in call.params]
            template["components"] = [{"type": "body", "parameters": params}]
        body = self._base(address) | {"type": "template", "template": template}
        return ChannelPayload(channel=self.channel_id, address=address, body=body)

    async def send(self, payload: ChannelPayload) -> DeliveryResult:
        """POST to the Graph API. Meta errors and network errors come back as results."""
        try:
            response = await self.client.post(self.messages_url, json=payload.body)
        except httpx.HTTPError:
            return DeliveryResult(ok=False, error_code="network")
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code < 400 and data.get("messages"):
            return DeliveryResult(ok=True, channel_message_id=data["messages"][0].get("id"))
        code = (data.get("error") or {}).get("code", response.status_code)
        return DeliveryResult(ok=False, error_code=str(code))
