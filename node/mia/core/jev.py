"""One request to Jev (TypeSafe System One). It leaves only through the egress transport
(rule 6), which logs, meters and enforces the egress level; callers pseudonymise the body
and set the egress context, and hold no write lock (rule 11)."""

import asyncio
from typing import Any

import httpx

from mia.core.egress import EgressBlocked, EgressTransport, current_context
from mia.settings import get_settings

RETRY_STATUS = {429, 529}
RETRIES = 2
BACKOFF = 0.5  # seconds, doubled per retry
TIMEOUT = 10.0


class JevError(Exception):
    """No usable answer, and waiting will not fix it: no key, egress blocked by
    configuration, a 4xx status, or an answer of the wrong shape."""


class JevUnreachable(JevError):
    """Jev could not be reached: a network error, a timeout, a 5xx, or 429/529 after the
    retries. Waiting may fix it (the chat defers the turn)."""


def _inner() -> httpx.AsyncBaseTransport | None:
    """The network below egress; tests replace this with an httpx.MockTransport."""
    return None


async def ask(body: dict[str, Any]) -> dict[str, Any]:
    """One request with an already pseudonymised body; returns its `answers`. Raises
    JevUnreachable when waiting may help, JevError otherwise."""
    settings = get_settings()
    if not settings.MIA_TYPESAFE_KEY:
        raise JevError("MIA_TYPESAFE_KEY is not set")
    try:
        current_context()
    except EgressBlocked as exc:
        raise JevError(str(exc)) from exc
    headers = {"Authorization": f"Bearer {settings.MIA_TYPESAFE_KEY}"}
    transport = EgressTransport(_inner(), pseudonymise=False)
    async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT) as client:
        for attempt in range(RETRIES + 1):
            try:
                response = await client.post(settings.MIA_TYPESAFE_URL, json=body, headers=headers)
            except EgressBlocked as exc:
                raise JevError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise JevUnreachable(type(exc).__name__) from exc
            retry = response.status_code in RETRY_STATUS or response.status_code >= 500
            if retry and attempt < RETRIES:
                await asyncio.sleep(BACKOFF * 2**attempt)
                continue
            if retry:
                raise JevUnreachable(f"status {response.status_code}")
            if response.status_code != 200:
                raise JevError(f"status {response.status_code}: {response.text[:300]}")
            try:
                answers = response.json()["answers"]
            except (KeyError, TypeError, ValueError) as exc:
                raise JevError(f"unexpected answer: {exc!r}") from exc
            if not isinstance(answers, dict):
                raise JevError("answers is not an object")
            return answers
    raise JevUnreachable("no answer")  # not reached: the loop returns or raises
