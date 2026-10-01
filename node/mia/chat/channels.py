"""Outbound channels: in-app notifications now, calls behind an adapter interface.

Mia writes proactive messages (for example "can you cover this visit?") into the person's chat
thread as role "notification"; the apps fetch them from /notifications. Voice calls are deferred
(spec, Voice calls), so CallAdapter has a stub that only logs the request; the LiveKit adapter
replaces it later without changing callers.
"""

from typing import Protocol

from pydantic import BaseModel
from sqlmodel import Session, col, select

from mia.chat.blocks import Block
from mia.core import events, store
from mia.core.models import Actor, Message, Person, Thread

NOTIFICATION = "notification"


def notify(
    session: Session, person: Person, blocks: list[Block], actor: Actor, agent_id: str
) -> Message:
    """Store a proactive message for a person in their latest thread with the agent."""
    thread = session.exec(
        select(Thread)
        .where(Thread.person_id == person.id)
        .where(Thread.agent_id == agent_id)
        .order_by(col(Thread.id).desc())
    ).first()
    if thread is None:
        thread = store.insert(
            session,
            Thread(branch_id=person.branch_id, person_id=person.id, agent_id=agent_id, title="Mia"),
            actor,
        )
    text = "\n".join(b.text for b in blocks if b.type == "text")
    message = Message(
        branch_id=person.branch_id,
        thread_id=thread.id,
        role=NOTIFICATION,
        sender_id=actor.principal.id,
        agent_id=agent_id,
        text=text,
        blocks=[b.model_dump(mode="json") for b in blocks],
    )
    return store.insert(session, message, actor, action="notification.sent")


class CallResult(BaseModel):
    placed: bool
    detail: str


class CallAdapter(Protocol):
    def call(self, session: Session, person: Person, script: str, actor: Actor) -> CallResult:
        """Place a call and speak the script. Must not block waiting for the answer."""
        ...


class StubCallAdapter:
    """Logs the call request as an event. No call is placed until the voice channel exists."""

    def call(self, session: Session, person: Person, script: str, actor: Actor) -> CallResult:
        events.emit(
            session, "call.requested", person, None, {"script": script, "placed": False}, actor
        )
        return CallResult(placed=False, detail="voice channel not enabled; call request logged")


_call_adapter: CallAdapter = StubCallAdapter()


def call_adapter() -> CallAdapter:
    return _call_adapter


def set_call_adapter(adapter: CallAdapter) -> None:
    global _call_adapter
    _call_adapter = adapter
