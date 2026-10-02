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


KITS: dict[str, Callable[[], Kit]] = {"sim": sim_kit}
