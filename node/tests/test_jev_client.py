import asyncio
import dataclasses
from typing import Any

import httpx
import pytest
from sqlmodel import Session

from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch
from mia.settings import get_settings

BODY: dict[str, Any] = {"model": "jev-1.13.0", "state": {}, "questions": {}}


@pytest.fixture
def ctx(session: Session, branch: Branch, monkeypatch: pytest.MonkeyPatch) -> EgressContext:
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setattr(jev, "BACKOFF", 0)
    get_settings.cache_clear()
    return EgressContext(
        session=session,
        actor=Actor.system(branch.id),
        organisation_id=branch.organisation_id,
        agent_id="test",
        purpose="test",
        level="pseudonymised",
        provider="typesafe",
    )


def _status(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"answers": {}})

    monkeypatch.setattr(jev, "_inner", lambda: httpx.MockTransport(handler))


def _ask(ctx: EgressContext) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        with egress_context(ctx):
            return await jev.ask(BODY)

    return asyncio.run(go())


@pytest.mark.parametrize("status", [500, 503, 429, 529])
def test_server_errors_and_overload_are_unreachable(
    ctx: EgressContext, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    _status(monkeypatch, status)
    with pytest.raises(jev.JevUnreachable):
        _ask(ctx)


def test_a_timeout_is_unreachable(ctx: EgressContext, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    monkeypatch.setattr(jev, "_inner", lambda: httpx.MockTransport(handler))
    with pytest.raises(jev.JevUnreachable):
        _ask(ctx)


def test_a_client_error_is_unusable_not_unreachable(
    ctx: EgressContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _status(monkeypatch, 400)
    with pytest.raises(jev.JevError) as info:
        _ask(ctx)
    assert not isinstance(info.value, jev.JevUnreachable)


def test_no_key_is_unusable(ctx: EgressContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(jev.JevError) as info:
        _ask(ctx)
    assert not isinstance(info.value, jev.JevUnreachable)


def test_egress_none_is_unusable(ctx: EgressContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _status(monkeypatch, 200)
    blocked = dataclasses.replace(ctx, level="none")
    with pytest.raises(jev.JevError) as info:
        _ask(blocked)
    assert not isinstance(info.value, jev.JevUnreachable)
