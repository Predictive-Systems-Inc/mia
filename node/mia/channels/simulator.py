"""The "sim" channel: an in-memory adapter for tests, the contract suite and local trials.

It signs webhooks like WhatsApp (X-Hub-Signature-256) and has WhatsApp-like limits, so code
exercised against it behaves the same on the real channel. Nothing leaves the process.
"""

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from mia.channels.base import (
    ChannelCapabilities,
    ChannelPayload,
    DeliveryResult,
    InboundMessage,
    StatusUpdate,
    TemplateCall,
    coordinates,
)
from mia.channels.render import ButtonsPart, ListPart, RenderedPart
from mia.core.db import utcnow
from mia.core.ids import new_id


def hub_signature_ok(secret: str, headers: Mapping[str, str], body: bytes) -> bool:
    """True when X-Hub-Signature-256 is the HMAC-SHA256 of the raw body with the secret."""
    given = {k.lower(): v for k, v in headers.items()}.get("x-hub-signature-256", "")
    if not secret or not given.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(given.removeprefix("sha256="), expected)


def _point(m: dict[str, Any]) -> tuple[float, float] | tuple[None, None]:
    where = m.get("location")
    if not isinstance(where, list) or len(where) != 2:
        return None, None
    return coordinates(where[0], where[1])


class SimAdapter:
    """In-memory channel. `sent` records payloads; `fail_next` makes the next send fail.

    `on_demand=True` (how `mia` and `mia serve` register it): its messages are sent only by
    `mia channels sim` for the number asked, never by the ticker or a background task, which
    would send them into a process's memory where nobody sees them.
    """

    channel_id = "sim"

    def __init__(
        self,
        capabilities: ChannelCapabilities | None = None,
        secret: str | None = None,
        *,
        on_demand: bool = False,
    ) -> None:
        from mia.channels.whatsapp.adapter import CAPABILITIES  # same limits as WhatsApp

        self.capabilities = capabilities or CAPABILITIES
        self.secret = secret or "sim-secret"  # public default: registered in dev mode only
        self.media: dict[str, bytes] = {}  # media id -> bytes, for fetch_media
        self.sent: list[ChannelPayload] = []
        self.fail_next: str | None = None
        self.on_demand = on_demand

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
                    name=m.get("name"),
                    button=m.get("button"),
                    has_media=bool(m.get("media")),
                    media_id=m["media"] if isinstance(m.get("media"), str) else None,
                    media_kind="image" if m.get("media") else None,
                    lat=_point(m)[0],
                    lon=_point(m)[1],
                    picked_place=bool(m.get("place")),
                    received_at=utcnow(),
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

    async def fetch_media(self, media_id: str) -> bytes | None:
        """The bytes registered in `media` for the id (None when there are none)."""
        return self.media.get(media_id)

    async def send(self, payload: ChannelPayload) -> DeliveryResult:
        """Record the payload; fail with `fail_next` once if set."""
        if self.fail_next is not None:
            code, self.fail_next = self.fail_next, None
            return DeliveryResult(ok=False, error_code=code)
        self.sent.append(payload)
        return DeliveryResult(ok=True, channel_message_id=new_id())
