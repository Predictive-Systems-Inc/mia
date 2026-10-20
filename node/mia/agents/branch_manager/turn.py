"""The branch manager's answer to one chat turn: Jev picks the action (MIA_DECIDER=jev), code
runs the tool through the guard and words the reply. The emergency script runs before this, in
chat.service, for every agent. A button's decision is kept in the decision.clarify_asked event
of its question and runs only when tapped on the day it was asked, and only when its action is
one of ACTIONS. Money (an experiment, a dated price) goes through the approvals guard: the reply
is the card the owner decides; a clerk never gets one (the guard denies the request)."""

import asyncio
import contextlib
import datetime as dt
import html
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, AgentSpec, ToolBinding, Turn, call_tool
from mia.agents.branch_manager import MANIFEST, actions, decider, due, experiments, replies, tools
from mia.agents.branch_manager.models import Experiment, Strategy
from mia.agents.decider import Decision
from mia.agents.sales_supervisor.tools import _currency
from mia.agents.shift_supervisor.classifier import classify
from mia.chat.blocks import Block, ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import reply_text, store_reply
from mia.core import events, orgconfig
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError, JevUnreachable
from mia.core.models import Branch, Event, Message, Person, Thread
from mia.core.money import format_money
from mia.core.rbac import PermissionDenied, Resource, get_rbac
from mia.i18n import t
from mia.settings import get_settings
from mia.templates.retail import items
from mia.templates.retail.models import RetailItem

_BINDINGS = {b.tool_id: b for b in tools.BINDINGS}  # importing tools registers its handlers
_DECIDE_TOOL = Resource(kind="tool", name=f"{MANIFEST.id}.decide_experiment")
OWN_SUGGESTION = "bm.strategy.seasonal"  # the agent's own suggestion (Q74): last year's month
MAX_OPTIONS = 5  # proposal buttons; a QuickRepliesBlock holds six


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
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    blocks: list[Block],
    options: replies.Options,
) -> ChatReply:
    """Store a question with buttons; what each button runs is kept in its event."""
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
    blocks: list[Block] = [
        TextBlock(text=t("clarify.question", deps.lang)),
        QuickRepliesBlock(options=[*options, other]),
    ]
    options[other] = Decision(action="clarify", confidence=1.0).model_dump(mode="json")
    return _ask(session, deps, thread, blocks, options)


def _names(session: Session) -> dict[str, str]:
    """Item, person and branch ids to names, for the replies (ids are ULIDs, never shared)."""
    out = {i.id: i.name for i in session.exec(select(RetailItem))}
    out |= {p.id: p.name for p in session.exec(select(Person))}
    return out | {b.id: b.name for b in session.exec(select(Branch))}


def _money(deps: AgentDeps, amount: int, currency: str | None = None) -> str:
    return format_money(amount, currency or _currency(deps.session, deps.branch.id), deps.lang)


# ---- the money cards ----------------------------------------------------------------------


def _complete(deps: AgentDeps, binding: ToolBinding, inp: BaseModel, call_id: str) -> None:
    """Run the binding's precheck once before the guard, so the input it completes (the
    engine's price, the strategy's kind, the rationale) is what the approval's summary says.
    Only for a person the tool permits (checked without a log line); a refusal is left for
    call_tool, which runs the precheck again and logs it."""
    spec = deps.manifest.tool(binding.tool_id)
    tool = Resource(kind="tool", name=spec.id)
    if binding.precheck is None or not get_rbac().check(deps.actor, tool, spec.permission_action):
        return
    with contextlib.suppress(LookupError, PermissionDenied):
        binding.precheck(deps, inp, call_id)


def _experiment_facts(
    deps: AgentDeps, args: tools.ProposeExperimentInput
) -> tuple[str, dict[str, str]]:
    """The experiment's summary and card fields from the completed input: strategy, item, the
    price move, the dates, the rationale, the guard rails and the baseline (or not enough
    data)."""
    session, lang = deps.session, deps.lang
    item = session.get(RetailItem, args.item_id)
    strategy = session.get(Strategy, args.strategy_id or "")
    if item is None or strategy is None or args.to_price is None:
        return "", {}
    new = args.rationale.get("new_item")
    now = (
        int(new["from_price"])
        if new is not None
        else items.price_on(session, item, deps.branch.id, args.starts_on)
    )
    days = orgconfig.load().branch_manager.experiment_days
    ends_on = args.starts_on + dt.timedelta(days=days - 1)
    name, money = t(strategy.name_key, lang), _money(deps, args.to_price, item.currency)
    summary = t(
        "bm.experiment.summary",
        lang,
        strategy=name,
        item=item.name,
        price=money,
        start=args.starts_on.isoformat(),
        end=ends_on.isoformat(),
    )
    before = args.starts_on - dt.timedelta(days=experiments.BASELINE_DAYS)
    history = tools.daily(session, deps.branch.id, item.id, before, args.starts_on)
    base = experiments.baseline(history, args.starts_on, days)
    baseline = (
        t(
            "bm.baseline",
            lang,
            days=base.days,
            units=base.units,
            amount=_money(deps, base.amount, item.currency),
        )
        if base is not None
        else t("bm.experiment.not_enough", lang)
    )
    old = _money(deps, now, item.currency)
    facts = {
        "strategy": name,
        "item": item.name,
        "price": t("bm.price_move", lang, from_price=old, to_price=money),
        "dates": t("bm.span", lang, start=args.starts_on.isoformat(), end=ends_on.isoformat()),
        "rationale": replies.rationale_text(strategy.name_key, args.rationale, item.currency, lang),
        "guard_rails": t(
            "bm.guard_rails", lang, percent=experiments.MAX_MOVE_PERCENT, days=days, price=old
        ),
        "baseline": baseline,
    }
    return summary, facts


def _price_summary(deps: AgentDeps, args: tools.ChangePriceInput) -> str:
    item = deps.session.get(RetailItem, args.item_id)
    if item is None:
        return ""
    now = items.price_on(deps.session, item, deps.branch.id, args.effective_on)
    return t(
        "bm.price.summary",
        deps.lang,
        item=item.name,
        from_price=_money(deps, now, item.currency),
        price=_money(deps, args.price, item.currency),
        date=args.effective_on.isoformat(),
    )


# ---- proposals ----------------------------------------------------------------------------


def _proposal_args(p: experiments.Proposal, starts_on: dt.date) -> dict[str, Any]:
    return {
        "item_id": p.item_id,
        "to_price": p.to_price,
        "starts_on": starts_on.isoformat(),
        "kind": p.kind,
        "strategy_id": p.strategy_id,
    }


def _offer(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    found: list[experiments.Proposal],
    starts_on: dt.date,
    key: str,
) -> ChatReply:
    """The engine's proposals as buttons (strategy, item, price), each requesting that
    experiment when tapped today; none: the numbers support no experiment."""
    if not found:
        return reply_text(session, deps, thread, t(key, deps.lang))
    names = _names(session)
    options: replies.Options = {}
    for p in found[:MAX_OPTIONS]:
        strategy = session.get(Strategy, p.strategy_id)
        label = t(
            "bm.experiment.option",
            deps.lang,
            strategy=t(strategy.name_key if strategy else "", deps.lang),
            item=names.get(p.item_id, ""),
            price=_money(deps, p.to_price),
        )
        decision = Decision(
            action="propose_experiment", args=_proposal_args(p, starts_on), confidence=1.0
        )
        options.setdefault(label, decision.model_dump(mode="json"))
    blocks: list[Block] = [
        TextBlock(text=t("bm.experiment.pick", deps.lang)),
        QuickRepliesBlock(options=list(options)),
    ]
    return _ask(session, deps, thread, blocks, options)


def _proposals(deps: AgentDeps, starts_on: dt.date) -> list[experiments.Proposal] | None:
    """The engine's proposals from starts_on (tools.proposals, its read checks first); None
    when the person may not read what it reads."""
    try:
        return tools.proposals(deps, starts_on, new_id())
    except PermissionDenied:
        return None


def _own_suggestion(session: Session, deps: AgentDeps, thread: Thread) -> ChatReply:
    """No item named ("ano ang pwede nating i-promo"): the engine's own suggestion (the
    seasonal strategy, Q74) is requested for the next open day; without one, the engine's
    proposals as buttons."""
    starts_on = actions._next_open_day(deps)
    found = _proposals(deps, starts_on)
    if found is None:
        return reply_text(session, deps, thread, t("bm.not_allowed", deps.lang))
    keys = {s.id: s.name_key for s in session.exec(select(Strategy))}
    own = next((p for p in found if keys.get(p.strategy_id) == OWN_SUGGESTION), None)
    if own is None:
        return _offer(session, deps, thread, found, starts_on, "bm.experiment.no_proposals")
    return _run(session, deps, thread, "propose_experiment", _proposal_args(own, starts_on))


# ---- tool results -------------------------------------------------------------------------


def _decided(deps: AgentDeps, args: dict[str, Any]) -> dict[str, Any]:
    """A typed keep or revert names no experiment: the branch's running or latest done one
    (the tool checks the permission and the state)."""
    if args.get("experiment_id"):
        return args
    row = deps.session.exec(
        select(Experiment)
        .where(Experiment.branch_id == deps.branch.id)
        .where(col(Experiment.status).in_(["running", "done"]))
        .order_by(col(Experiment.starts_on).desc())
    ).first()
    return {**args, "experiment_id": row.id if row is not None else ""}


def _tool_args(deps: AgentDeps, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """The decision's args as the tool's input."""
    if tool == "set_short_code":
        code = args.get("code")
        return {"item_id": args.get("item_id"), "codes": [code] if code else []}
    if tool == "decide_experiment":
        return _decided(deps, args)
    return args


def _scored(session: Session, deps: AgentDeps, thread: Thread, out: dict[str, Any]) -> ChatReply:
    """A running experiment so far; a done one's result naming its strategy, with keep and
    revert buttons for whoever may decide it before its price goes back."""
    score = tools.ScoreOutput.model_validate(out)
    row = session.get(Experiment, score.experiment_id)
    if row is None:
        return reply_text(session, deps, thread, t("bm.no_record", deps.lang))
    names = _names(session)
    strategy = session.get(Strategy, row.strategy_id)
    name = t(strategy.name_key, deps.lang) if strategy is not None else ""
    item = names.get(row.item_id, "")
    done = row.status in ("done", "kept")
    text = replies.score_text(
        score.units_pct, score.amount_pct, score.days, done, name, item, deps.lang
    )
    may_decide = get_rbac().check(deps.actor, _DECIDE_TOOL, "execute")
    if row.status != "done" or not may_decide or tools._reverted(session, row):
        return reply_text(session, deps, thread, text)
    options: replies.Options = {}
    for keep, key, price in ((True, "keep", row.to_price), (False, "revert", row.from_price)):
        label = t(f"bm.experiment.{key}", deps.lang, price=_money(deps, price, row.currency))
        args = {"experiment_id": row.id, "keep": keep}
        decision = Decision(action="decide_experiment_result", args=args, confidence=1.0)
        options[label] = decision.model_dump(mode="json")
    blocks: list[Block] = [TextBlock(text=text), QuickRepliesBlock(options=list(options))]
    return _ask(session, deps, thread, blocks, options)


def _result(
    session: Session, deps: AgentDeps, thread: Thread, tool: str, out: dict[str, Any]
) -> ChatReply:
    """The reply to one successful tool result (tool is the name without the agent prefix)."""
    lang, names = deps.lang, _names(session)
    currency = _currency(session, deps.branch.id)
    blocks: list[Block]
    if tool == "coaching":
        text = replies.coaching_text(
            tools.CoachingOutput.model_validate(out), lang, names, currency
        )
        blocks = [TextBlock(text=text)]
    elif tool == "how_to_sell":
        blocks = replies.how_to_sell(tools.HowToSellOutput.model_validate(out), lang)
    elif tool == "score_experiment":
        return _scored(session, deps, thread, out)
    elif tool == "decide_experiment":
        e = tools.ExperimentOut.model_validate(out)
        key, price = (
            ("bm.experiment.kept", e.to_price)
            if e.status == "kept"
            else ("bm.experiment.not_kept", e.from_price)
        )
        item = names.get(e.new_item_id or e.item_id, "")
        money = _money(deps, price, e.currency)
        blocks = [TextBlock(text=t(key, lang, item=item, price=money, end=e.ends_on.isoformat()))]
    elif tool == "set_short_code":
        blocks = replies.short_code(tools.ItemOut.model_validate(out), lang)
    elif tool == "weekly_summary":
        blocks = replies.weekly(tools.WeeklyOutput.model_validate(out), names, currency, lang)
    elif tool == "monthly_letter":
        blocks = replies.monthly(tools.MonthlyOutput.model_validate(out), names, lang)
    else:  # propose_experiment and change_price run on approve
        blocks = [TextBlock(text=t("reply.not_built", lang))]
    return store_reply(session, deps, thread, blocks)


def _run(
    session: Session, deps: AgentDeps, thread: Thread, tool: str, args: dict[str, Any]
) -> ChatReply:
    """Run the tool through the guard (rbac first) and word the reply from its result: a money
    request is the card the owner decides; a request matching no strategy offers the engine's
    proposals."""
    if tool == "propose_experiment" and not args.get("item_id"):
        return _own_suggestion(session, deps, thread)
    binding = _BINDINGS[f"{MANIFEST.id}.{tool}"]
    try:
        inp = binding.input_type.model_validate(_tool_args(deps, tool, args))
    except ValidationError:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    call_id = new_id()
    summary, facts = "", dict[str, str]()
    if isinstance(inp, tools.ProposeExperimentInput):
        _complete(deps, binding, inp, call_id)
        summary, facts = _experiment_facts(deps, inp)
    elif isinstance(inp, tools.ChangePriceInput):
        summary = _price_summary(deps, inp)
    out = call_tool(deps, binding, inp, call_id, summary)
    if out.get("status") == "approval_required":
        approval_id = str(out["approval_id"])
        if isinstance(inp, tools.ProposeExperimentInput):
            waiting = replies.experiment_waiting(approval_id, summary, facts, deps.lang)
        else:
            waiting = replies.price_waiting(approval_id, summary, deps.lang)
        return store_reply(session, deps, thread, waiting)
    if "status" in out and "message" in out:  # a ToolRefusal
        if out["status"] == "denied":
            return reply_text(session, deps, thread, t("bm.not_allowed", deps.lang))
        if isinstance(inp, tools.ProposeExperimentInput) and out["message"] == "no_strategy":
            starts_on = inp.starts_on
            found = _proposals(deps, starts_on) or []
            return _offer(session, deps, thread, found, starts_on, "bm.refused.no_strategy")
        key = replies.refusal_key(str(out["message"]))
        return reply_text(session, deps, thread, t(key, deps.lang))
    return _result(session, deps, thread, tool, out)


def _act(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """Log the decision, then ask "Did you mean", run its tool through the guard, or word a
    conversation reply. A decision whose action is not one of ACTIONS (a tapped decision of
    another agent) asks to rephrase."""
    after = decision.model_dump(mode="json")
    events.emit(session, "decision.made", ("thread", thread.id), None, after, deps.actor)
    if decision.action == "clarify":
        return _did_you_mean(session, deps, thread, decision)
    spec = actions.ACTIONS.get(decision.action)
    if spec is None:
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
        "Leading the shop: coaching and tips for staff, price and promo experiments, menu prices,"
        " short codes and combos, opening hours, people and roles and who approves what, permits"
        " and renewals, the weekly summary and the monthly numbers; not sales counts or targets"
        " and not a shift change."
    ),
    handle_turn=handle_turn,
    run_due=due.run_due,
    stream_agent=None,
)
