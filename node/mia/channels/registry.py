"""Registered channel adapters, and which of them the organisation has switched on."""

from mia.channels.base import ChannelAdapter
from mia.core import orgconfig
from mia.core.orgconfig import OrgSettings

_adapters: dict[str, ChannelAdapter] = {}


def register(adapter: ChannelAdapter) -> None:
    """Make an adapter available under its channel id (replaces one with the same id)."""
    _adapters[adapter.channel_id] = adapter


def get(channel_id: str) -> ChannelAdapter:
    """The adapter for a channel id. Raises KeyError when none is registered."""
    return _adapters[channel_id]


def enabled(org: OrgSettings | None = None) -> list[ChannelAdapter]:
    """Registered adapters the organisation has switched on, in registration order."""
    org = org or orgconfig.load()
    return [a for cid, a in _adapters.items() if (c := org.channels.get(cid)) and c.enabled]
