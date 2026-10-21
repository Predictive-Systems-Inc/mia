"""The hr officer's answer to one chat turn: Jev picks the action (MIA_DECIDER=jev), code
runs the tool and words the reply. The emergency script runs before this, in chat.service, for
every agent. Decisions of a sensitive action (pay, hours, leave) are logged with their args
hidden; a button's decision is kept on its message row, not in the log."""

import asyncio
import datetime as dt
import html
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlmodel import Session, col, select

from mia.agents.base import REDACTED, AgentDeps, AgentSpec, Turn, call_tool
from mia.agents.decider import THRESHOLD, Decision
from mia.agents.hr_officer import MANIFEST, actions, decider, due, replies, tools
from mia.agents.shift_supervisor.classifier import classify
from mia.chat.blocks import Block, ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import reply_text, store_reply
from mia.core import events
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError, JevUnreachable
from mia.core.models import Event, Message, Thread
from mia.core.rbac import PermissionDenied, Resource, get_rbac
from mia.i18n import t
from mia.settings import get_settings

_BINDINGS = {b.tool_id: b for b in tools.BINDINGS}  # importing tools registers its handlers
_CERTIFICATE_TOOL = Resource(kind="tool", name=f"{MANIFEST.id}.certificate_text")
_SENSITIVE_TOOLS = {s.name for s in MANIFEST.tools if s.sensitive}


def _sensitive(action: str) -> bool:
    spec = actions.ACTIONS.get(action)
    return spec is not None and spec.tool in _SENSITIVE_TOOLS


def _logged(decision: dict[str, Any]) -> dict[str, Any]:
    """A decision dump as the log keeps it: the args of an action whose tool is sensitive (pay,
    hours, leave) hidden with their keys kept, in the alternatives too."""

    def hide(d: dict[str, Any]) -> dict[str, Any]:
        if _sensitive(d["action"]) or _sensitive(d.get("raw_action", "")):
            return {**d, "args": {k: REDACTED for k in d.get("args", {})}}
        return d

    out = hide(decision)
    return {**out, "alternatives": [hide(a) for a in out.get("alternatives", [])]}


def _last_question(session: Session, thread: Thread) -> Message | None:
    """The thread's last Mia message, questions included (chat.service._last_mia)."""
    from mia.chat.service import _last_mia  # chat.service imports the registry, so this module

    return _last_mia(session, thread, questions=True)


def _tapped(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Decision | None:
    """The decision behind a tapped button of the thread's last Mia message, asked today."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "decision.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = _last_question(session, thread)
    if asked is None or last is None or (asked.after or {}).get("message_id") != last.id:
        return None
    if asked.timestamp.astimezone(ZoneInfo(deps.branch.timezone)).date() != deps.today:
        return None
    chosen = replies.button_decisions(last.blocks).get(text.strip())
    return Decision.model_validate(chosen) if chosen else None


def _query(
    session: Session, deps: AgentDeps, thread: Thread, text: str
) -> tuple[Decision | None, actions.Query | None]:
    """A decision already made (a tapped button, an injection), or the query for Jev."""
    tapped = _tapped(session, deps, thread, text)
    if tapped is not None:
        return tapped, None
    if classify(html.unescape(text), deps.today, deps.lang).injection:
        return Decision(action="reply_only", args={"kind": "injection"}, confidence=1), None
    last = _last_question(session, thread)
    return None, actions.build_query(deps, text, last.text if last else "")


def _did_you_mean(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply:
    """Ask "Did you mean" with a button per offerable alternative; with none, ask to rephrase."""
    options: dict[str, dict[str, object]] = {}  # label -> the decision a tap runs
    for alt in decision.alternatives:
        spec = actions.ACTIONS.get(alt.action)
        if spec is None or spec.label_key is None or alt.missing is not None:
            continue
        label = t(spec.label_key, deps.lang)
        if label not in options:
            chosen = Decision(action=alt.action, args=alt.args, confidence=alt.probability)
            options[label] = chosen.model_dump(mode="json")
    if not options:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    other = t("clarify.something_else", deps.lang)
    blocks: list[Block] = [
        TextBlock(text=t("clarify.question", deps.lang)),
        QuickRepliesBlock(options=[*options, other]),
    ]
    options[other] = Decision(action="clarify", confidence=1.0).model_dump(mode="json")
    return _ask(session, deps, thread, blocks, options)


def _ask(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    blocks: list[Block],
    options: replies.Options,
) -> ChatReply:
    """Store a question with buttons; what each button runs is kept on the message row (the
    event logs it with sensitive args hidden, and then the reply is sensitive too)."""
    logged = {label: _logged(d) for label, d in options.items()}
    blocks = replies.with_decisions(blocks, options, sensitive=logged != options)
    reply = store_reply(session, deps, thread, blocks)
    after = {"options": logged, "message_id": reply.message_id}
    events.emit(session, "decision.clarify_asked", ("thread", thread.id), None, after, deps.actor)
    return reply


def _refusal(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    tool: str,
    out: dict[str, Any],
    args: dict[str, Any],
) -> ChatReply:
    """The reply to a refused tool call: a leave refused before approval says why; another
    person's records (or a certificate by someone who may not issue one) is not allowed;
    nothing on record yet says so."""
    if tool == "request_leave" and out["status"] == "invalid":
        refused = replies.leave_refused(out["message"], args, deps.lang)
        if refused is not None:
            return store_reply(session, deps, thread, refused)
    if out["status"] == "denied":
        key = "hr.not_allowed.certificate" if tool == "certificate_text" else "hr.not_allowed"
    else:
        key = "hr.no_record"
    return reply_text(session, deps, thread, t(key, deps.lang))


def _run(
    session: Session, deps: AgentDeps, thread: Thread, tool: str, args: dict[str, Any]
) -> ChatReply:
    """Run the tool through the guard (rbac first) and word the reply from its result."""
    binding = _BINDINGS[f"{MANIFEST.id}.{tool}"]
    try:
        inp = binding.input_type.model_validate(args)
    except ValidationError:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    call_id = new_id()
    leave = inp if isinstance(inp, tools.RequestLeaveInput) else None
    preview = _preview(deps, leave, call_id) if leave is not None else None
    summary = ""
    if leave is not None and preview is not None:
        summary = replies.leave_summary(deps.person.name, leave, preview, deps.lang)
    out = call_tool(deps, binding, inp, call_id, summary)
    if leave is not None and out.get("status") == "approval_required":
        approval_id = str(out["approval_id"])
        waiting = replies.leave_waiting(summary, leave, preview, approval_id, deps.lang)
        return store_reply(session, deps, thread, waiting)
    if "status" in out and "message" in out:  # a ToolRefusal
        return _refusal(session, deps, thread, tool, out, inp.model_dump(mode="json"))
    blocks = replies.tool_reply(tool, out, args, deps.lang)
    return store_reply(session, deps, thread, blocks)


def _preview(
    deps: AgentDeps, leave: tools.RequestLeaveInput, call_id: str
) -> tools.LeavePreview | None:
    """The leave's working days and balance after for its card; None when the request cannot
    be previewed (the guard then refuses it with the reason)."""
    try:
        return tools.preview_leave(deps, leave, call_id)
    except (LookupError, PermissionDenied):
        return None


def _missing(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply | None:
    """The reply to a sure decision that lacks one input: a leave without dates asks the day
    with buttons; a certificate by someone who may not issue one is not allowed. None
    otherwise ("Did you mean" follows)."""
    if decision.confidence < THRESHOLD:
        return None
    if decision.raw_action == "file_leave" and decision.missing == "leave_start":
        days = _leave_days(deps)
        return _ask(session, deps, thread, *replies.ask_leave_days(decision, days, deps.lang))
    if decision.raw_action == "certificate" and decision.missing == "person":
        try:  # the denial is logged as rbac.deny, like the guard's
            get_rbac().require(deps.actor, _CERTIFICATE_TOOL, "execute", session=session)
        except PermissionDenied:
            return reply_text(session, deps, thread, t("hr.not_allowed.certificate", deps.lang))
    return None


def _leave_days(deps: AgentDeps) -> list[dt.date]:
    """The days the leave buttons offer: the person's next working days from tomorrow; without
    a contract (or the right to read it) the next days, which the guard then refuses with the
    reason."""
    try:
        return tools.leave_days_ahead(deps, replies.ASKED_DAYS, new_id())
    except (LookupError, PermissionDenied):
        return [deps.today + dt.timedelta(days=i) for i in range(1, replies.ASKED_DAYS + 1)]


def _act(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """Log the decision, then ask what is missing or "Did you mean", run its tool through the
    guard, or word a conversation reply."""
    after = _logged(decision.model_dump(mode="json"))
    events.emit(session, "decision.made", ("thread", thread.id), None, after, deps.actor)
    if decision.action == "clarify" and (asked := _missing(session, deps, thread, decision)):
        return asked
    if decision.action == "clarify":
        return _did_you_mean(session, deps, thread, decision)
    spec = actions.ACTIONS.get(decision.action)
    if spec is None:  # a tapped decision of another agent
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    if spec.tool is not None:
        return _run(session, deps, thread, spec.tool, decision.args)
    kind = str(decision.args.get("kind", "other"))
    return store_reply(session, deps, thread, replies.conversation_reply(kind, deps.lang))


def _unavailable(
    session: Session, deps: AgentDeps, thread: Thread, error: str | None = None
) -> ChatReply:
    """reply.unavailable; a Jev error is logged as decision.failed."""
    if error is not None:
        failed = {"error": error}
        events.emit(session, "decision.failed", ("thread", thread.id), None, failed, deps.actor)
    return reply_text(session, deps, thread, t("reply.unavailable", deps.lang))


async def _jev_turn(
    session: Session, deps: AgentDeps, thread: Thread, text: str, ctx: EgressContext
) -> ChatReply:
    """DB work runs in worker threads; the Jev request runs with no write lock held."""
    decision, query = await asyncio.to_thread(_query, session, deps, thread, text)
    if decision is None and query is not None:
        await asyncio.to_thread(session.commit)
        try:
            with egress_context(replace(ctx, provider="typesafe", purpose=f"{MANIFEST.id}.decide")):
                decision = await decider.decide(query)
        except JevUnreachable:
            raise  # an outage: the chat defers the turn
        except JevError as exc:
            return await asyncio.to_thread(_unavailable, session, deps, thread, str(exc))
    assert decision is not None
    return await asyncio.to_thread(_act, session, deps, thread, decision)


async def handle_turn(turn: Turn) -> ChatReply:
    """A tapped button or Jev's decision worded by code; reply.unavailable without Jev."""
    session, deps, thread = turn.session, turn.deps, turn.thread
    if get_settings().MIA_DECIDER != "jev":
        return await asyncio.to_thread(_unavailable, session, deps, thread)
    return await _jev_turn(session, deps, thread, turn.text, turn.ctx)


SPEC = AgentSpec(
    manifest=MANIFEST,
    label_key=f"agent.{MANIFEST.id}.label",
    router_description=(
        "Employment: my hours worked this cutoff, cash advances, holiday pay, payroll and"
        " payslips, 13th month pay, leave balances, filing sick or vacation leave for a date, SSS,"
        " PhilHealth and Pag-IBIG contributions, hiring; not who works which shift and not adding"
        " people to a branch."
    ),
    handle_turn=handle_turn,
    run_due=due.run_due,
    stream_agent=None,
)
