"""The branch manager's answer to one chat turn: Jev picks the action (MIA_DECIDER=jev), code
runs the tool through the guard and words the reply. The emergency script runs before this, in
chat.service, for every agent. A button's decision is kept in the decision.clarify_asked event
of its question and runs only when tapped on the day it was asked (a keep or revert button until
the experiment reverts: the tool's too_late is its deadline), and only when its action is one of
ACTIONS. A typed keep with a negation word is asked with the keep and revert buttons, never run. Money (an experiment, a dated price) goes through the approvals guard: the reply
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
from mia.core import auth, events, orgconfig
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
PEOPLE_TOOLS = ("add_person", "set_phone", "assign_kiosk")
# A people action missing an input asks for it; set_phone's person is asked as a name.
PERSON_ASKS = {"name": "bm.person.ask_name", "role": "bm.person.ask_role",
               "phone": "bm.person.ask_phone", "person": "bm.person.ask_who",
               "kiosk": "bm.assign.ask_kiosk"}  # fmt: skip
PERSON_REFUSALS = {
    "person_exists": "bm.person.exists",
    "phone_invalid": "bm.person.ask_phone",
    "phone_taken": "bm.person.phone_taken",
    "phone_set": "bm.person.phone_set",
    "phone_role": "bm.person.phone_role",
    "not_supervisor": "bm.assign.not_supervisor",
    "home_branch": "bm.assign.home_branch",
    "already_assigned": "bm.assign.already_assigned",
    "not_assigned": "bm.assign.not_assigned",
}
PHONE_EXAMPLE = "0917 123 4567"


def _last_question(session: Session, thread: Thread) -> Message | None:
    """The thread's last Mia message, questions included (chat.service._last_mia)."""
    from mia.chat.service import _last_mia  # chat.service imports the registry, so this module

    return _last_mia(session, thread, questions=True)


def _tapped(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Decision | None:
    """The decision behind a tapped button of the thread's last Mia message, asked today; a
    keep or revert button any day (decide_experiment refuses too_late after the revert)."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "decision.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = _last_question(session, thread)
    if asked is None or last is None or (asked.after or {}).get("message_id") != last.id:
        return None
    chosen = ((asked.after or {}).get("options") or {}).get(text.strip())
    if not chosen:
        return None
    decision = Decision.model_validate(chosen)
    if decision.action == "decide_experiment_result":
        return decision
    if asked.timestamp.astimezone(ZoneInfo(deps.branch.timezone)).date() != deps.today:
        return None
    return decision


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


def _names(session: Session, deps: AgentDeps) -> dict[str, str]:
    return due.names(session, deps.organisation_id)


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
            **tools.WORDED,
            days=base.days,
            units=base.units,
            amount=_money(deps, base.amount, item.currency),
        )
        if base is not None
        else t("bm.experiment.not_enough", lang, **tools.WORDED)
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
    names = _names(session, deps)
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


def _awaiting(deps: AgentDeps) -> Experiment | None:
    """The branch's latest done experiment awaiting a decision (its revert not yet in force),
    else its running one."""
    rows = deps.session.exec(
        select(Experiment)
        .where(Experiment.branch_id == deps.branch.id)
        .where(col(Experiment.status).in_(["running", "done"]))
    ).all()
    done = [r for r in rows if r.status == "done" and not tools._reverted(deps.session, r)]
    running = [r for r in rows if r.status == "running"]
    return max(done or running, key=lambda r: (r.ends_on, r.id), default=None)


def _decided(deps: AgentDeps, args: dict[str, Any]) -> dict[str, Any]:
    """A typed keep or revert names no experiment: _awaiting's (the tool checks the
    permission and the state)."""
    if args.get("experiment_id"):
        return args
    row = _awaiting(deps)
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
    names = _names(session, deps)
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
    options = replies.keep_or_revert(row, deps.lang)
    blocks: list[Block] = [TextBlock(text=text), QuickRepliesBlock(options=list(options))]
    return _ask(session, deps, thread, blocks, options)


def _ask_keep_or_revert(session: Session, deps: AgentDeps, thread: Thread) -> ChatReply:
    """A typed keep with a negation word ("dai, pundohon na an bagong presyo"): the keep and
    revert buttons of _awaiting's experiment, so a tap decides; nothing is kept. Without one
    the sender may decide, ask to rephrase."""
    row = _awaiting(deps)
    if row is None or not get_rbac().check(deps.actor, _DECIDE_TOOL, "execute"):
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    options = replies.keep_or_revert(row, deps.lang)
    blocks: list[Block] = [
        TextBlock(text=t("clarify.question", deps.lang)),
        QuickRepliesBlock(options=list(options)),
    ]
    return _ask(session, deps, thread, blocks, options)


def _result(
    session: Session, deps: AgentDeps, thread: Thread, tool: str, out: dict[str, Any]
) -> ChatReply:
    """The reply to one successful tool result (tool is the name without the agent prefix)."""
    lang, names = deps.lang, _names(session, deps)
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
    elif tool == "assign_kiosk":
        a = tools.AssignKioskOut.model_validate(out)
        key = "bm.assign.removed" if a.removed else "bm.assign.done"
        blocks = [TextBlock(text=t(key, lang, name=a.name, branch=a.branch))]
    elif tool in PEOPLE_TOOLS:
        days = auth.CODE_TTL["invite"].days
        blocks = replies.person(tools.PersonOut.model_validate(out), days, lang)
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
        if tool in PEOPLE_TOOLS and out["message"] in PERSON_REFUSALS:
            key = PERSON_REFUSALS[str(out["message"])]
            who = deps.session.get(Person, str(args.get("person_id") or ""))
            name = who.name if who is not None else str(args.get("name") or "")
            where = deps.session.get(Branch, str(args.get("branch_id") or ""))
            branch = where.name if where is not None else ""
            text = t(key, deps.lang, name=name, branch=branch, example=PHONE_EXAMPLE)
            return reply_text(session, deps, thread, text)
        key = replies.refusal_key(str(out["message"]))
        return reply_text(session, deps, thread, t(key, deps.lang, **tools.WORDED))
    return _result(session, deps, thread, tool, out)


def _logged(decision: Decision) -> dict[str, Any]:
    """The decision for its event, a phone number in its args or alternatives redacted."""
    after = decision.model_dump(mode="json")
    for args in [after["args"], *(a["args"] for a in after["alternatives"])]:
        if args.get("phone"):
            args["phone"] = events.REDACTED
    return after


def _act(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """Log the decision, then ask "Did you mean", run its tool through the guard, or word a
    conversation reply. A decision whose action is not one of ACTIONS (a tapped decision of
    another agent) asks to rephrase."""
    after = _logged(decision)
    events.emit(session, "decision.made", ("thread", thread.id), None, after, deps.actor)
    if decision.action == "clarify" and decision.raw_action in PEOPLE_TOOLS and decision.missing:
        key = PERSON_ASKS.get(decision.missing, "clarify.rephrase")
        return reply_text(session, deps, thread, t(key, deps.lang, example=PHONE_EXAMPLE))
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
    if query is not None and query.negated and _keeps(decision):
        return await asyncio.to_thread(_negated_keep, session, deps, thread, decision)
    return await asyncio.to_thread(_act, session, deps, thread, decision)


def _keeps(decision: Decision) -> bool:
    return decision.action == "decide_experiment_result" and decision.args.get("keep") is True


def _negated_keep(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply:
    """Log Jev's decision, then ask with the buttons instead of keeping."""
    after = decision.model_dump(mode="json")
    events.emit(session, "decision.made", ("thread", thread.id), None, after, deps.actor)
    return _ask_keep_or_revert(session, deps, thread)


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
        "Leading the shop: coaching and tips for staff, how to sell more and advice on low sales,"
        " upselling, price and promo experiments, menu prices, changing short codes and combos,"
        " opening hours, who is in charge, people and roles and who approves what, assigning a"
        " supervisor to another kiosk or removing them from one, permits and"
        " renewals, the weekly coaching summary; not sales figures for a day, week or month (benta"
        " kahapon, last week per item), not the list of item codes, not sales counts or targets"
        " and not a shift change."
    ),
    handle_turn=handle_turn,
    run_due=due.run_due,
    stream_agent=None,
)
