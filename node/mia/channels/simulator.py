"""The "sim" channel: an in-memory adapter for tests, the contract suite and local trials.

It signs webhooks like WhatsApp (X-Hub-Signature-256) and has WhatsApp-like limits, so code
exercised against it behaves the same on the real channel. Nothing leaves the process.
"""

import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import UTC, datetime

from mia.channels.base import (
    ChannelCapabilities,
    ChannelPayload,
    DeliveryResult,
    InboundMessage,
    StatusUpdate,
    TemplateCall,
)
from mia.channels.render import ButtonsPart, ListPart, RenderedPart
from mia.core.ids import new_id

WHATSAPP_LIKE = ChannelCapabilities(
    max_text=4096,
    max_buttons=3,
    max_button_label=20,
    max_list_rows=10,
    max_list_label=24,
    session_window_hours=24,
    supports_templates=True,
)


def hub_signature_ok(secret: str, headers: Mapping[str, str], body: bytes) -> bool:
    """True when X-Hub-Signature-256 is the HMAC-SHA256 of the raw body with the secret."""
    given = {k.lower(): v for k, v in headers.items()}.get("x-hub-signature-256", "")
    if not secret or not given.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(given.removeprefix("sha256="), expected)


class SimAdapter:
    """In-memory channel. `sent` records payloads; `fail_next` makes the next send fail."""

    channel_id = "sim"

    def __init__(
        self, capabilities: ChannelCapabilities = WHATSAPP_LIKE, secret: str = "sim-secret"
    ) -> None:
        self.capabilities = capabilities
        self.secret = secret
        self.sent: list[ChannelPayload] = []
        self.fail_next: str | None = None

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        """Signed with the sim secret, like WhatsApp."""
        return hub_signature_ok(self.secret, headers, body)

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        """Echo the challenge when the verify token is the sim secret."""
        if params.get("hub.verify_token") == self.secret:
            return params.get("hub.challenge")
        return None

    def receive(self, body: bytes) -> list[InboundMessage | StatusUpdate]:
        """Parse {"messages": [...], "statuses": [...]}."""
        data = json.loads(body)
        out: list[InboundMessage | StatusUpdate] = []
        for m in data.get("messages", []):
            out.append(
                InboundMessage(
                    channel=self.channel_id,
                    address=m["from"],
                    channel_message_id=m["id"],
                    text=m.get("text") or "",
                    button=m.get("button"),
                    has_media=bool(m.get("media")),
                    received_at=datetime.now(UTC),
                )
            )
        for s in data.get("statuses", []):
            out.append(
                StatusUpdate(
                    channel=self.channel_id,
                    channel_message_id=s["id"],
                    status=s["status"],
                    error_code=s.get("error"),
                )
            )
        return out

    def render(self, address: str, parts: list[RenderedPart]) -> list[ChannelPayload]:
        """One payload per part: the part's fields plus its kind."""
        out = []
        for part in parts:
            kind = (
                "buttons"
                if isinstance(part, ButtonsPart)
                else "list"
                if isinstance(part, ListPart)
                else "text"
            )
            out.append(
                ChannelPayload(
                    channel=self.channel_id,
                    address=address,
                    body={"kind": kind, **part.model_dump()},
                )
            )
        return out

    def render_template(self, address: str, call: TemplateCall) -> ChannelPayload:
        """Any template name is accepted; the payload carries the call."""
        return ChannelPayload(
            channel=self.channel_id, address=address, body={"kind": "template", **call.model_dump()}
        )

    async def send(self, payload: ChannelPayload) -> DeliveryResult:
        """Record the payload; fail with `fail_next` once if set."""
        if self.fail_next is not None:
            code, self.fail_next = self.fail_next, None
            return DeliveryResult(ok=False, error_code=code)
        self.sent.append(payload)
        return DeliveryResult(ok=True, channel_message_id=new_id())
