"""Egress: nothing leaves without the policy, names never leave in pseudonymised mode."""

import asyncio
import json
import sqlite3
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from pydantic_ai import models
from sqlmodel import Session, select

from mia.agents.dispatcher.agent import create_agent
from mia.chat.service import run_turn
from mia.core import egress
from mia.core.egress import EgressBlocked, EgressContext, EgressTransport, Pseudonymiser
from mia.core.models import Actor, EgressLog, Person, UsageCloudRequest
from mia.settings import get_settings


class Recorder:
    """A fake network: records what would have been sent, answers like an OpenAI endpoint."""

    def __init__(self, reply_text: str = "ok") -> None:
        self.bodies: list[str] = []
        self.reply_text = reply_text

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(request.content.decode())
        args = json.dumps({"blocks": [{"type": "text", "text": self.reply_text}]})
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 0,
                "model": "dispatcher-default",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {"name": "final_result", "arguments": args},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
            },
        )


@pytest.fixture
def mock_network() -> Iterator[None]:
    """Let a gateway model run; these tests replace the network with httpx.MockTransport."""
    with models.override_allow_model_requests(True):
        yield


def _all_name_parts(people: dict[str, Person]) -> set[str]:
    return {part for p in people.values() for part in p.name.split()}


def test_level_none_raises_before_any_http_call(
    session: Session, people: dict[str, Person]
) -> None:
    recorder = Recorder()
    transport = EgressTransport(httpx.MockTransport(recorder))
    ctx = EgressContext(session, Actor.person(people["Juha"]), "ORG", "dispatcher", "chat", "none")

    async def go() -> None:
        async with httpx.AsyncClient(transport=transport) as client:
            with egress.egress_context(ctx):
                await client.post("http://gateway.test/v1/chat", json={"text": "hi"})

    with pytest.raises(EgressBlocked):
        asyncio.run(go())
    assert recorder.bodies == []
    assert session.exec(select(EgressLog)).all() == []


def test_send_with_level_none_raises(session: Session, people: dict[str, Person]) -> None:
    with pytest.raises(EgressBlocked):
        egress.send(
            session, "chat", "Juha Laine", "none", actor=Actor.person(people["Juha"]), agent_id="d"
        )


def test_no_context_means_nothing_leaves() -> None:
    with pytest.raises(EgressBlocked, match="no egress context"):
        egress.current_context()


def test_pseudonymised_payload_contains_no_seed_names(
    session: Session, people: dict[str, Person]
) -> None:
    text = " ".join(p.name for p in people.values()) + " Mikaelin vuoro, soita Sannalle."
    out, pseudo = egress.send(
        session,
        "chat",
        text,
        "pseudonymised",
        actor=Actor.person(people["Juha"]),
        agent_id="dispatcher",
    )
    lowered = out.lower()
    for part in _all_name_parts(people):
        assert part.lower() not in lowered, part
    assert "Person_" in out
    log = session.exec(select(EgressLog)).one()
    assert log.level == "pseudonymised" and log.payload_hash == egress.payload_hash(out)
    assert pseudo.restore("Person_1") in {p.name for p in people.values()}


def test_pseudonymiser_is_stable_and_reversible(
    session: Session, people: dict[str, Person]
) -> None:
    branch_id = people["Juha"].branch_id
    a = Pseudonymiser.for_branch(session, branch_id)
    b = Pseudonymiser.for_branch(session, branch_id)
    assert a.apply("Juha Laine") == b.apply("Juha Laine")
    assert a.restore(a.apply("Juha Laine")) == "Juha Laine"
    assert Pseudonymiser().apply("Juha") == "Juha"


@pytest.mark.usefixtures("mock_network")
def test_gateway_model_goes_through_egress(session: Session, people: dict[str, Person]) -> None:
    """Switching MIA_MODEL to a gateway route needs no code change and is logged pseudonymised."""
    recorder = Recorder(reply_text="Hei Person_3, kiitos.")
    agent = create_agent("gateway/dispatcher-default", transport=httpx.MockTransport(recorder))
    juha = people["Juha"]
    reply = asyncio.run(run_turn(session, agent, juha, "Moi, olen Juha Laine. Mikael on kipeä."))

    assert len(recorder.bodies) == 1
    sent = recorder.bodies[0].lower()
    for part in _all_name_parts(people):
        assert part.lower() not in sent, f"{part} left the node"
    assert json.loads(recorder.bodies[0])["model"] == "dispatcher-default"

    log = session.exec(select(EgressLog)).one()
    assert (log.level, log.agent_id, log.purpose) == ("pseudonymised", "dispatcher", "chat")
    usage = session.exec(select(UsageCloudRequest)).one()
    assert (usage.input_tokens, usage.output_tokens, usage.model) == (120, 30, "dispatcher-default")
    # Tokens in the reply are restored on the node.
    ordered = sorted(people.values(), key=lambda p: p.id)
    assert reply.blocks[0].type == "text"
    assert ordered[2].name in reply.blocks[0].text


@pytest.mark.usefixtures("mock_network")
def test_no_write_lock_is_held_during_the_model_call(
    session: Session, people: dict[str, Person]
) -> None:
    """SQLite has one writer: a model call must not keep every other writer waiting."""
    db_path = get_settings().MIA_DB_PATH
    lock_free: list[bool] = []

    class LockProbe(Recorder):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            other = sqlite3.connect(db_path, timeout=0)
            try:
                other.execute("BEGIN IMMEDIATE")
                other.rollback()
                lock_free.append(True)
            except sqlite3.OperationalError:
                lock_free.append(False)
            finally:
                other.close()
            return super().__call__(request)

    agent = create_agent("gateway/dispatcher-default", transport=httpx.MockTransport(LockProbe()))
    asyncio.run(run_turn(session, agent, people["Juha"], "Moi"))
    assert lock_free == [True]
    # What left the node stays logged even though the turn's transaction committed in parts.
    assert len(session.exec(select(EgressLog)).all()) == 1


@pytest.mark.usefixtures("mock_network")
def test_egress_db_work_is_off_the_event_loop(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 12: the egress log and usage record are written in worker threads."""
    import threading

    from mia.core import usage

    on_loop: list[bool] = []
    real_send, real_record = egress.send, usage.record

    def spy_send(*args: Any, **kwargs: Any) -> Any:
        on_loop.append(threading.current_thread() is threading.main_thread())
        return real_send(*args, **kwargs)

    def spy_record(*args: Any, **kwargs: Any) -> Any:
        on_loop.append(threading.current_thread() is threading.main_thread())
        return real_record(*args, **kwargs)

    monkeypatch.setattr(egress, "send", spy_send)
    monkeypatch.setattr(usage, "record", spy_record)
    agent = create_agent("gateway/dispatcher-default", transport=httpx.MockTransport(Recorder()))
    asyncio.run(run_turn(session, agent, people["Juha"], "Moi"))
    assert len(on_loop) == 2 and not any(on_loop)
