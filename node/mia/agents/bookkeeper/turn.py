"""The bookkeeper's answer to one chat turn: Jev picks the action (MIA_DECIDER=jev), code runs
the tool through the guard and words the reply. The emergency script runs before this, in
chat.service, for every agent.

A button's decision is kept in the decision.clarify_asked event of its question and runs only
when tapped on the day it was asked, and only when its action is one of ACTIONS. Petty cash
whose kind the message does not say is asked with Spend and Refill buttons. A correction
(Query.corrected) of a write replaces the day's cash count (the latest count of a date wins)
only when there is one to replace; anything else is asked, never written twice. A large expense
goes through the approvals guard: the reply is the card the owner (or an admin) decides; the
owner's own is decided by the owner with a step-up (D37)."""

import asyncio
import html
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, AgentSpec, Turn, call_tool
from mia.agents.bookkeeper import MANIFEST, actions, calc, decider, replies, tools
from mia.agents.bookkeeper.models import CashCount
from mia.agents.decider import Decision
from mia.agents.sales_supervisor.tools import _currency
from mia.agents.shift_supervisor.classifier import classify
from mia.chat.blocks import Block, ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import reply_text, store_reply
from mia.core import db, events, orgconfig
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError, JevUnreachable
from mia.core.models import Branch, Event, Message, Thread
from mia.core.rbac import get_rbac
from mia.i18n import t
from mia.settings import get_settings
from mia.templates.retail import hours as retail_hours

_BINDINGS = {b.tool_id: b for b in tools.BINDINGS}  # importing tools registers its handlers
WRITES = frozenset(["cash_count", "settlement", "payout", "expense", "petty_cash", "deposit"])
ASKED = frozenset(["amount", "provider", "category", "bank"])  # bk.ask.<slot> questions


def _last_question(session: Session, thread: Thread) -> Message | None:
    """The thread's last Mia message, questions included (chat.service._last_mia)."""
    from mia.chat.service import _last_mia  # chat.service imports the registry, so this module

    return _last_mia(session, thread, questions=True)


def _tapped(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Decision | None:
    """The decision behind a tapped button of the thread's last Mia message, asked today (_act
    then checks its action is one of ACTIONS)."""
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
    chosen = ((asked.after or {}).get("options") or {}).get(text.strip())
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


def _ask(
    session: Session, deps: AgentDeps, thread: Thread, text: str, options: replies.Options
) -> ChatReply:
    """Store a question with a button per option; what each button runs is kept in its
    event."""
    blocks: list[Block] = [TextBlock(text=text), QuickRepliesBlock(options=list(options))]
    reply = store_reply(session, deps, thread, blocks)
    after = {"options": options, "message_id": reply.message_id}
    events.emit(session, "decision.clarify_asked", ("thread", thread.id), None, after, deps.actor)
    return reply


def _did_you_mean(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply:
    """Ask "Did you mean" with a button per offerable alternative; with none, ask to rephrase."""
    options: replies.Options = {}
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
    options[other] = Decision(action="clarify", confidence=1.0).model_dump(mode="json")
    return _ask(session, deps, thread, t("clarify.question", deps.lang), options)


def _ask_petty_kind(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply:
    """Petty cash without its kind: Spend and Refill buttons, each the petty_cash decision with
    the parsed amount and that kind."""
    options: replies.Options = {}
    for kind in actions.PETTY:
        args = {**decision.args, "kind": kind}
        chosen = Decision(action="petty_cash", args=args, confidence=1.0)
        options[t(f"bk.petty.{kind}_option", deps.lang)] = chosen.model_dump(mode="json")
    return _ask(session, deps, thread, t("bk.petty.ask_kind", deps.lang), options)


def _clarify(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """A missing petty kind asks with buttons; a missing amount, provider, category or bank
    asks for it; else "Did you mean"."""
    if decision.raw_action == "petty_cash" and decision.missing == "kind":
        return _ask_petty_kind(session, deps, thread, decision)
    if decision.raw_action in WRITES and decision.missing in ASKED:
        return reply_text(session, deps, thread, t(f"bk.ask.{decision.missing}", deps.lang))
    return _did_you_mean(session, deps, thread, decision)


def _names(session: Session, deps: AgentDeps) -> replies.Names:
    stmt = select(Branch).where(Branch.organisation_id == deps.organisation_id)
    return {b.id: b.name for b in session.exec(stmt)}


def _result(deps: AgentDeps, tool: str, args: dict[str, Any], out: dict[str, Any]) -> str:
    """The reply text of one successful tool result (tool is the name without the agent
    prefix)."""
    lang, settings = deps.lang, orgconfig.load().bookkeeper
    if tool == "record_cash_count":
        text = replies.count_text(tools.CashCountOut.model_validate(out), lang)
    elif tool in ("record_settlement", "record_payout"):
        o = tools.MatchOut.model_validate(out)
        m = calc.Match(expected=o.expected, cut=o.cut, gap=o.gap, flagged=o.flagged)
        text = replies.match_text(m, o.provider, lang, o.currency)
    elif tool in ("record_expense", "record_large_expense"):
        text = replies.expense_text(tools.ExpenseOut.model_validate(out), lang)
    elif tool == "record_petty":
        petty = tools.PettyOut.model_validate(out)
        category = str(args.get("category") or "supplies")
        text = replies.petty_text(petty, settings.petty_floor, category, lang)
    elif tool == "record_deposit":
        text = replies.deposit_text(tools.DepositOut.model_validate(out), lang)
    elif tool == "balances":
        balances = tools.BalancesOut.model_validate(out)
        text = replies.balances_text(balances, settings.undeposited_limit, lang)
    elif tool == "sales_journal":
        text = replies.journal_text(tools.JournalOut.model_validate(out), lang)
    elif tool == "tax_quarter":
        text = replies.tax_text(
            tools.TaxOutput.model_validate(out), _names(deps.session, deps), lang
        )
    else:  # monthly_profit
        profit = tools.ProfitOutput.model_validate(out)
        text = replies.profit_text(profit, _names(deps.session, deps), lang)
    return text


def _run(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    action: str,
    args: dict[str, Any],
    lead: str | None = None,
) -> ChatReply:
    """Run the action's tool through the guard (rbac first) and word the reply from its
    result, after lead when it succeeded: an expense over the limit is the card the owner
    decides."""
    binding = _BINDINGS[actions.tool_for(action, args)]
    try:
        inp = binding.input_type.model_validate(args)
    except ValidationError:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    currency, summary = _currency(session, deps.branch.id), ""
    if isinstance(inp, tools.ExpenseInput) and binding.tool_id == tools.LARGE_EXPENSE:
        summary = replies.expense_summary(inp, currency, deps.lang)
    out = call_tool(deps, binding, inp, new_id(), summary)
    if out.get("status") == "approval_required" and isinstance(inp, tools.ExpenseInput):
        approval_id = str(out["approval_id"])
        blocks = replies.expense_waiting(approval_id, summary, inp, currency, deps.lang)
        return store_reply(session, deps, thread, blocks)
    if "status" in out and "message" in out:  # a ToolRefusal
        if out["status"] == "denied":
            return reply_text(session, deps, thread, t("bk.not_allowed", deps.lang))
        limit = replies.money(orgconfig.load().bookkeeper.expense_limit, currency, deps.lang)
        key = replies.refusal_key(str(out["message"]))
        return reply_text(session, deps, thread, t(key, deps.lang, limit=limit))
    text = _result(deps, binding.tool_id.removeprefix(f"{MANIFEST.id}."), args, out)
    return reply_text(session, deps, thread, "\n".join(filter(None, [lead, text])))


def _log(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> None:
    after = decision.model_dump(mode="json")
    events.emit(session, "decision.made", ("thread", thread.id), None, after, deps.actor)


def _act(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """Log the decision, then ask, run its tool through the guard, or word a conversation
    reply. A decision whose action is not one of ACTIONS (a tapped decision of another agent)
    asks to rephrase."""
    _log(session, deps, thread, decision)
    if decision.action == "clarify":
        return _clarify(session, deps, thread, decision)
    spec = actions.ACTIONS.get(decision.action)
    if spec is None:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    if spec.tool is not None:
        return _run(session, deps, thread, decision.action, decision.args)
    if decision.action == "not_built":
        return reply_text(session, deps, thread, t("bk.not_built.utang", deps.lang))
    kind = str(decision.args.get("kind", "other"))
    return store_reply(session, deps, thread, replies.conversation_reply(kind, deps.lang))


def _todays_count(session: Session, deps: AgentDeps, args: dict[str, Any]) -> CashCount | None:
    """The latest count of the decision's day (the stated day, else the branch's business
    date now) when the sender may read counts, else None."""
    if not get_rbac().check(deps.actor, tools.CASH, "read"):
        return None
    day = args.get("business_date") or retail_hours.business_date_at(
        deps.branch, retail_hours.load(session, deps.branch.id), db.utcnow()
    )
    stmt = (
        select(CashCount)
        .where(CashCount.branch_id == deps.branch.id)
        .where(CashCount.business_date == day)
        .order_by(col(CashCount.created_at).desc(), col(CashCount.id).desc())
    )
    return session.exec(stmt).first()


def _correct(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """A correction of a write: a cash count replaces the day's count it names (a new row; the
    latest count of a date wins) and says so; anything else, or a count with none to replace,
    is asked again, never written as a second entry."""
    _log(session, deps, thread, decision)
    previous = (
        _todays_count(session, deps, decision.args) if decision.action == "cash_count" else None
    )
    if previous is None:
        return reply_text(session, deps, thread, t("bk.correction.ask", deps.lang))
    old = replies.money(previous.counted, previous.currency, deps.lang)
    lead = t("bk.count.replaced", deps.lang, old=old)
    return _run(session, deps, thread, decision.action, decision.args, lead)


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
    if query is not None and query.corrected and decision.action in WRITES:
        return await asyncio.to_thread(_correct, session, deps, thread, decision)
    return await asyncio.to_thread(_act, session, deps, thread, decision)


def _unavailable(
    session: Session, deps: AgentDeps, thread: Thread, error: str | None = None
) -> ChatReply:
    """reply.unavailable; a Jev error is logged as decision.failed."""
    if error is not None:
        failed = {"error": error}
        events.emit(session, "decision.failed", ("thread", thread.id), None, failed, deps.actor)
    return reply_text(session, deps, thread, t("reply.unavailable", deps.lang))


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
        "Money: the closing cash count against sales, a drawer short or over, expenses and"
        " receipts, petty cash, bank deposits, GCash and Maya settlements, Grab and Foodpanda"
        " payouts, VAT, the BIR sales book and monthly profit; not sales counts, not a day's"
        " sales total and not pay."
    ),
    handle_turn=handle_turn,
    run_due=None,
    stream_agent=None,
)
