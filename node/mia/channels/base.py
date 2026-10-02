"""The channel adapter interface (spec, Channel adapter interface) and its message models.

Agents and services never see channel formats: they hand Mia blocks to channels.service, which
renders them with channels.render and passes the result to the adapter.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from mia.channels.render import RenderedPart


class ChannelCapabilities(BaseModel):
    """What a channel can show. Rendering stays inside these limits."""

    max_text: int
    max_buttons: int
    max_button_label: int
    max_list_rows: int
    max_list_label: int
    session_window_hours: int | None  # None: the channel has no messaging window
    supports_templates: bool


class InboundMessage(BaseModel):
    """One message a person sent on a channel."""

    channel: str
    address: str
    channel_message_id: str
    text: str = ""
    button: str | None = None  # label of a tapped button or list row
    has_media: bool = False
    received_at: datetime


class StatusUpdate(BaseModel):
    """A delivery status for a message Mia sent."""

    channel: str
    channel_message_id: str
    status: str  # sent, delivered, read, failed
    error_code: str | None = None


class TemplateCall(BaseModel):
    """A pre-approved template message (for channels with a messaging window)."""

    name: str
    lang: str
    params: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)


class ChannelPayload(BaseModel):
    """One request body for the channel's API, addressed to one recipient."""

    channel: str
    address: str
    body: dict[str, Any]


class DeliveryResult(BaseModel):
    """What the channel answered when Mia sent a payload."""

    ok: bool
    channel_message_id: str | None = None
    error_code: str | None = None


class ChannelAdapter(Protocol):
    """Translate between one messaging channel and Mia's message model."""

    channel_id: str
    capabilities: ChannelCapabilities

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        """True only when the webhook request is signed by the channel."""
        ...

    def verify_subscription(self, params: Mapping[str, str]) -> str | None:
        """The challenge to echo when the channel's subscription handshake is valid, else None."""
        ...

    def receive(self, body: bytes) -> list[InboundMessage | StatusUpdate]:
        """Parse a verified webhook body."""
        ...

    def render(self, address: str, parts: list[RenderedPart]) -> list[ChannelPayload]:
        """Channel payloads for rendered parts, in order."""
        ...

    def render_template(self, address: str, call: TemplateCall) -> ChannelPayload:
        """The payload for a registered template. Raises ValueError for unknown templates."""
        ...

    async def send(self, payload: ChannelPayload) -> DeliveryResult:
        """Send one payload. Never raises for channel errors; they come back in the result."""
        ...
