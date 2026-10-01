"""Egress: nothing leaves without the policy, names never leave in pseudonymised mode."""

import asyncio
import json

import httpx
import pytest
from sqlmodel import Session, select

from mia.agents.dispatcher.agent import create_agent
from mia.chat.service import run_turn
from mia.core import egress
from mia.core.egress import EgressBlocked, EgressContext, EgressTransport, Pseudonymiser
from mia.core.models import Actor, EgressLog, Person, UsageCloudRequest


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
