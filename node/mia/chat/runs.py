"""Live AG-UI runs that outlive their HTTP connection, so a client can reconnect and catch up.

The pattern (an eager run with a replay buffer, a connect endpoint, a stop endpoint, one run per
thread) is adapted from CopilotKit's AgentRunner (MIT); no code was copied. See
docs/research/copilotkit-practices.md.

Guarantees:
- At most one live run per thread; start() raises RunBusy for a second one.
- Every event of a run is kept until the run ends; follow() replays them and then streams live
  ones. A dropped connection never stops the run; only stop() does.
- The server owns the history: the run sees the stored thread plus the newest user message from
  the client (wrapped, rule 8). Client-sent history, frontend tools, state and resume entries are
  ignored, so a client cannot forge past turns or declare tools (rules 3 and 8).
- The output tool's raw arguments (unchecked blocks) never reach the client. The reply follows
  after check_blocks as one text message (id = stored message id) and a CUSTOM "mia.blocks" event.
- RUN_ERROR carries a translated message and a code, never exception text (that goes to the log).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from ag_ui.core import (
    AssistantMessage,
    BaseEvent,
    CustomEvent,
    EventType,
    MessagesSnapshotEvent,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallStartEvent,
    UserMessage,
)
from ag_ui.core import (
    Message as AguiMessage,
)
from pydantic_ai import AgentRunResult, CancellationToken
from pydantic_ai.ui.ag_ui import AGUIAdapter
from sqlmodel import Session, col, select

from mia.agents.dispatcher.agent import get_agent
from mia.chat.blocks import AgentReply, ApprovalCardBlock, ChatReply
from mia.chat.service import _finish, _prepare, wrap_user_text
from mia.core.db import get_engine
from mia.core.egress import egress_context
from mia.core.ids import new_id
from mia.core.models import Approval, Message, Person, Thread
from mia.i18n import t

log = logging.getLogger(__name__)

BLOCKS_EVENT = "mia.blocks"
OUTPUT_TOOL = "final_result"  # Pydantic AI's default output tool name
TEXT_EVENTS = {
    EventType.TEXT_MESSAGE_START,
    EventType.TEXT_MESSAGE_CONTENT,
    EventType.TEXT_MESSAGE_END,
    EventType.TEXT_MESSAGE_CHUNK,
}


class RunBusy(Exception):
    """The thread already has a live run."""


@dataclass
class LiveRun:
    thread_id: str
    run_id: str
    person_id: str
    events: list[str] = field(default_factory=list)  # JSON of each event, in order
    done: bool = False
    token: CancellationToken = field(default_factory=CancellationToken)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    # Ids are monotonic: every row this run stores sorts after `since` (see rejoin_rows).
    since: str = field(default_factory=new_id)

    async def push(self, event: BaseEvent) -> None:
        async with self.changed:
            self.events.append(event.model_dump_json(by_alias=True))
            self.changed.notify_all()

    async def close(self) -> None:
        async with self.changed:
            self.done = True
            self.changed.notify_all()


# ponytail: in-process registry, fine for one uvicorn worker per node (mia serve); with several
# workers, live runs need a shared store (CopilotKit's SqliteAgentRunner keeps a run_state table).
_live: dict[str, LiveRun] = {}


def live(thread_id: str) -> LiveRun | None:
    """The thread's live run, if any."""
    return _live.get(thread_id)


def frame(data: str) -> str:
    """One SSE frame. No `id:` field: the AG-UI HTTP binding has no Last-Event-ID resumption,
    so a reconnect restates history as a snapshot instead (see connect_events)."""
    return f"data: {data}\n\n"


async def follow(run: LiveRun, after: int = 0) -> AsyncIterator[str]:
    """SSE frames of the run's events after position `after`, live until the run ends."""
    seen = after

    def ready() -> bool:
        return run.done or len(run.events) > seen

    while True:
        async with run.changed:
            await run.changed.wait_for(ready)
            batch, finished = run.events[seen:], run.done
        for data in batch:
            seen += 1
            yield frame(data)
        if finished and seen >= len(run.events):
            return


def rejoin_rows(run: LiveRun, rows: list[Message]) -> list[Message]:
    """Stored rows for a rejoin snapshot, without this run's own reply: the replayed events carry
    it (same message id), so including a reply committed before the run ended would show it twice.
    """
    return [r for r in rows if r.role == "user" or r.id < run.since]


async def rejoin(run: LiveRun, history: MessagesSnapshotEvent) -> AsyncIterator[str]:
    """A reconnect to a live run: its RUN_STARTED, the stored history as MESSAGES_SNAPSHOT, then
    the run's events after its own RUN_STARTED (every stream must open with RUN_STARTED, and
    replayed history must be a snapshot, per the AG-UI lifecycle spec)."""
    yield frame(
        RunStartedEvent(thread_id=run.thread_id, run_id=run.run_id).model_dump_json(by_alias=True)
    )
    yield frame(history.model_dump_json(by_alias=True))
    async for chunk in follow(run, after=1):
        yield chunk


def user_text(run_input: RunAgentInput) -> str:
    """Text of the newest user message ("" when there is none). Non-text content is dropped."""
    for message in reversed(run_input.messages):
        if isinstance(message, UserMessage):
            if isinstance(message.content, str):
                return message.content.strip()
            parts = [getattr(c, "text", "") for c in message.content if c.type == "text"]
            return "\n".join(parts).strip()
    return ""


def start(person_id: str, run_input: RunAgentInput, text: str) -> LiveRun:
    """Register a live run and start it. Raises RunBusy when the thread already has one."""
    if run_input.thread_id in _live:
        raise RunBusy(run_input.thread_id)
    run = LiveRun(thread_id=run_input.thread_id, run_id=run_input.run_id, person_id=person_id)
    _live[run.thread_id] = run
    run.task = asyncio.create_task(_drive(run, run_input, text))
    return run


def stop(thread_id: str, person_id: str) -> bool:
    """Cancel the person's live run on the thread. False when there is none."""
    run = _live.get(thread_id)
    if run is None or run.person_id != person_id:
        return False
    run.token.cancel()
    return True


def _reply_events(reply: ChatReply) -> list[BaseEvent]:
    """The checked reply as AG-UI events: one text message, then the blocks."""
    events: list[BaseEvent] = []
    text = "\n".join(b.text for b in reply.blocks if b.type == "text")
    if text:
        events += [
            TextMessageStartEvent(message_id=reply.message_id, role="assistant"),
            TextMessageContentEvent(message_id=reply.message_id, delta=text),
            TextMessageEndEvent(message_id=reply.message_id),
        ]
    events.append(CustomEvent(name=BLOCKS_EVENT, value=reply.model_dump(mode="json")))
    return events


def _error(code: str, lang: str) -> RunErrorEvent:
    return RunErrorEvent(message=t("chat.error", lang), code=code)


async def _drive(run: LiveRun, run_input: RunAgentInput, text: str) -> None:
    """Run the agent to the end, pushing every visible event; store the reply."""
    session = Session(get_engine(), expire_on_commit=False)
    last = ""  # type of the last event pushed
    hidden: set[str] = set()  # tool call ids of the output tool
    replying = False  # True once on_complete sends the checked reply
    lang = "en"
    try:
        person = await asyncio.to_thread(session.get, Person, run.person_id)
        if person is None:
            raise LookupError("person vanished")
        lang = person.language
        thread, past, deps, ctx = await asyncio.to_thread(
            _prepare, session, person, text, run.thread_id, create=True
        )
        lang = deps.lang
        # The wrapped text is the run's user prompt, so new_messages() (and the stored turn)
        # include it, as in chat.service.run_turn. run_input only supplies thread and run ids.
        clean = run_input.model_copy(
            update={"messages": [], "tools": [], "state": None, "context": [], "resume": None}
        )
        agent = get_agent()
        adapter = AGUIAdapter(agent=agent, run_input=clean)

        async def on_complete(result: AgentRunResult[AgentReply]) -> AsyncIterator[BaseEvent]:
            nonlocal replying
            reply = await asyncio.to_thread(_finish, session, deps, thread, result)
            await asyncio.to_thread(session.commit)
            replying = True
            for event in _reply_events(reply):
                yield event

        async def native() -> AsyncIterator[Any]:
            async with agent.run_stream_events(
                wrap_user_text(text, person),
                message_history=past,
                deps=deps,
                cancellation_token=run.token,
            ) as events:
                async for item in events:
                    yield item

        with egress_context(ctx):
            stream = adapter.transform_stream(native(), on_complete=on_complete)
            async for event in stream:
                if isinstance(event, ToolCallStartEvent) and event.tool_call_name == OUTPUT_TOOL:
                    hidden.add(event.tool_call_id)
                if getattr(event, "tool_call_id", None) in hidden:
                    continue
                # A plain-text answer (text_reply fallback) streams as model text; the client
                # gets only the checked, stored reply that on_complete sends.
                if event.type in TEXT_EVENTS and not replying:
                    continue
                if isinstance(event, RunErrorEvent):
                    log.error("AG-UI run %s failed: %s", run.run_id, event.message)
                    event = _error("agent_error", lang)
                last = event.type
                await run.push(event)
    except Exception:
        log.exception("AG-UI run %s failed", run.run_id)
        await asyncio.to_thread(session.rollback)
        if not last:
            await run.push(RunStartedEvent(thread_id=run.thread_id, run_id=run.run_id))
        if last != EventType.RUN_ERROR:  # nothing may follow RUN_ERROR (AG-UI lifecycle)
            await run.push(_error("internal_error", lang))
    finally:
        await asyncio.to_thread(session.close)
        _live.pop(run.thread_id, None)
        await run.close()


def stored_messages(session: Session, thread_id: str) -> list[Message]:
    """The thread's stored messages in order."""
    return list(
        session.exec(
            select(Message).where(Message.thread_id == thread_id).order_by(col(Message.id))
        ).all()
    )


def snapshot(session: Session, thread: Thread, run_id: str) -> list[BaseEvent]:
    """Catch-up for a thread with no live run: its stored messages and blocks, framed as a run.

    Approval cards show the approval's current status, not the status when the card was sent.
    """
    rows = stored_messages(session, thread.id)
    return [
        RunStartedEvent(thread_id=thread.id, run_id=run_id),
        messages_snapshot(rows),
        *blocks_events(session, thread, rows),
        RunFinishedEvent(thread_id=thread.id, run_id=run_id),
    ]


def messages_snapshot(rows: list[Message]) -> MessagesSnapshotEvent:
    """MESSAGES_SNAPSHOT of stored messages: the person's own words, never the wrapped prompt."""
    messages: list[AguiMessage] = []
    for row in rows:
        if row.role == "user":
            messages.append(UserMessage(id=row.id, content=row.text))
        else:
            messages.append(AssistantMessage(id=row.id, content=row.text))
    return MessagesSnapshotEvent(messages=messages)


def blocks_events(session: Session, thread: Thread, rows: list[Message]) -> list[BaseEvent]:
    """One CUSTOM mia.blocks event per stored assistant message, approval status refreshed."""
    events: list[BaseEvent] = []
    for row in rows:
        if row.role != "assistant" or not row.blocks:
            continue
        reply = ChatReply.model_validate(
            {
                "thread_id": thread.id,
                "message_id": row.id,
                "agent_id": row.agent_id or "",
                "blocks": row.blocks,
            }
        )
        for block in reply.blocks:
            if isinstance(block, ApprovalCardBlock):
                approval = session.get(Approval, block.approval_id)
                if approval is not None:
                    block.status = approval.status
        events.append(CustomEvent(name=BLOCKS_EVENT, value=reply.model_dump(mode="json")))
    return events
