"""ChannelTransport: the only HTTP exit for messaging channels (rule 6).

Adapters build their httpx client on this transport. A request is refused unless it happens
inside outbox.send_due's `sending()` block (anything) or an inbound handler's `fetching()`
block (GET only: downloading an attachment a person sent), so nothing reaches a channel except
a queued, logged outbox row or the fetch of a logged inbound attachment.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

_sending: ContextVar[str | None] = ContextVar("mia_channel_sending", default=None)
_fetching: ContextVar[str | None] = ContextVar("mia_channel_fetching", default=None)


class ChannelBlocked(Exception):
    """A channel request was made outside an outbox send."""


@contextmanager
def sending(outbox_id: str) -> Iterator[None]:
    """Allow channel requests for one outbox row; restored on exit even after errors."""
    token = _sending.set(outbox_id)
    try:
        yield
    finally:
        _sending.reset(token)


@contextmanager
def fetching(inbound_id: str) -> Iterator[None]:
    """Allow GET requests for one inbound attachment; restored on exit even after errors."""
    token = _fetching.set(inbound_id)
    try:
        yield
    finally:
        _fetching.reset(token)


class ChannelTransport(httpx.AsyncBaseTransport):
    """httpx transport that only forwards requests made inside `sending()` or, for GETs,
    `fetching()`."""

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self.inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if _sending.get() is None and not (_fetching.get() is not None and request.method == "GET"):
            raise ChannelBlocked("channel requests leave the node only through the outbox")
        return await self.inner.handle_async_request(request)
