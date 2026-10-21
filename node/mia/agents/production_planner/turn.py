"""The production planner's answer to one chat turn: Jev picks the action (MIA_DECIDER=jev), code
runs the tool through the guard and words the reply. The emergency script runs before this, in
chat.service, for every agent.

A button's decision is kept in the decision.clarify_asked event of its question (or its
notification, through remember) and runs only while it holds, and only when its action is one of
ACTIONS: the plan card's Confirm until production starts (hours.start) on the plan's date (a
"Did you mean" confirm holds only the day it was asked), a Delivered button to the end of its
business date, any other button on the day it was asked. The recipe card's Save is a stored set_recipe decision with its args; a recipe typed in chat only
shows the card. A confirm with a negation word ("hindi pa ok") shows the plan with its Confirm
button, never confirms. No tool asks for an approval."""

import asyncio
import datetime as dt
import html
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, AgentSpec, Turn, call_tool
from mia.agents.decider import Decision
from mia.agents.production_planner import MANIFEST, actions, decider, replies, tools
from mia.agents.production_planner import capacity as oven
from mia.agents.shift_supervisor.classifier import classify
from mia.chat.blocks import Block, ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import reply_text, store_reply
from mia.core import db, events, orgconfig
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError, JevUnreachable
from mia.core.models import Actor, Branch, Event, Message, Thread
from mia.core.rbac import Resource, get_rbac
from mia.i18n import t
from mia.settings import get_settings
from mia.templates.retail.models import RetailIngredient, RetailItem

_BINDINGS = {b.tool_id: b for b in tools.BINDINGS}  # importing tools registers its handlers
SET_RECIPE = Resource(kind="tool", name=f"{MANIFEST.id}.set_recipe")
# a missing input asked for in words; recipe and negated depend on the action (_clarify)
ASKED = {
    "item": "pp.ask.item",
    "kiosk": "pp.ask.kiosk",
    "number": "pp.ask.number",
    "plan": "pp.ask.plan",
    "batch": "pp.batch.unclear",
    "negated": "pp.change.kept",
    "direction": "pp.ask.direction",
    "unit": "pp.ask.unit",
}
# a tool refusal's reason -> its reply key (the turn fills item, kiosk and minutes)
REFUSALS = {
    "no_recipe": "pp.sheet.no_recipe",
    "capacity": "pp.change.no_room",
    "past": "pp.change.past",
    "no_plan": "pp.plan.none",
    "not_planned": "pp.change.not_planned",
    "batch_total": "pp.batch.too_many",
    "bundle": "pp.recipe.bundle",
    "not_driver": "pp.delivered.not_driver",
    "no_dispatch": "pp.dispatch.none",
    "no_commissary": "pp.no_commissary",
}


def remember(session: Session, message: Message, options: replies.Options, actor: Actor) -> None:
    """Keep the decisions a message's buttons run (decision.clarify_asked on its thread), so a
    tap runs one without Jev. The due work calls this right after notify()."""
    after = {"options": options, "message_id": message.id}
    events.emit(
        session, "decision.clarify_asked", ("thread", message.thread_id), None, after, actor
    )


def _last_question(session: Session, thread: Thread) -> Message | None:
    """The thread's last Mia message, questions included (chat.service._last_mia)."""
    from mia.chat.service import _last_mia  # chat.service imports the registry, so this module

    return _last_mia(session, thread, questions=True)


def _holds(session: Session, deps: AgentDeps, asked: Event, decision: Decision) -> bool:
    """Whether a stored decision may still run now (see the module docstring)."""
    now = db.utcnow()
    if decision.action == "confirm_plan" and decision.args.get("card"):  # plan_card's only
        home = actions.commissary(session, deps.organisation_id)
        if home is not None:
            start = orgconfig.load().production_planner.hours.start
            day = dt.date.fromisoformat(str(decision.args["production_date"]))
            return now < dt.datetime.combine(day, start, ZoneInfo(home.timezone))
    if decision.action == "delivered" and decision.args.get("business_date"):
        day = dt.date.fromisoformat(str(decision.args["business_date"]))
        return now.astimezone(ZoneInfo(deps.branch.timezone)).date() <= day
    return asked.timestamp.astimezone(ZoneInfo(deps.branch.timezone)).date() == deps.today


def _tapped(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Decision | None:
    """The decision behind a tapped button of the thread's last Mia message while it holds
    (_act then checks its action is one of ACTIONS)."""
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
    return decision if _holds(session, deps, asked, decision) else None


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
    said = session.exec(
        select(Message.id)
        .where(Message.thread_id == thread.id)
        .where(Message.role == "user")
        .order_by(col(Message.id).desc())
    ).first()
    return None, actions.build_query(deps, text, last.text if last else "", message_id=said)


def _ask(
    session: Session, deps: AgentDeps, thread: Thread, blocks: list[Block], options: replies.Options
) -> ChatReply:
    """Store a reply with buttons; what each button runs is kept in its event."""
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
    blocks: list[Block] = [
        TextBlock(text=t("clarify.question", deps.lang)),
        QuickRepliesBlock(options=list(options)),
    ]
    return _ask(session, deps, thread, blocks, options)


def _clarify(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """A missing input of a tool action is asked for in words (a recipe not read is the
    recipe hint, pieces without a recipe say so); else "Did you mean"."""
    missing, raw = decision.missing, decision.raw_action
    if missing == "recipe":
        key = "pp.recipe.unclear" if raw == "set_recipe" else "pp.ask.recipe"
        return reply_text(session, deps, thread, t(key, deps.lang))
    if raw in actions.ACTIONS and missing in ASKED:
        return reply_text(session, deps, thread, t(ASKED[missing], deps.lang))
    return _did_you_mean(session, deps, thread, decision)


def names(session: Session, organisation_id: str) -> dict[str, str]:
    """Item, ingredient and branch (of the organisation) ids -> names."""
    found = {i.id: i.name for i in session.exec(select(RetailItem))}
    found |= {i.id: i.name for i in session.exec(select(RetailIngredient))}
    branches = select(Branch).where(Branch.organisation_id == organisation_id)
    return found | {b.id: b.name for b in session.exec(branches)}


def _refused(
    session: Session, deps: AgentDeps, thread: Thread, inp: BaseModel, out: dict[str, Any]
) -> ChatReply:
    """The reply to a tool refusal: denied, else its reason's key with the item, kiosk and the
    free oven minutes of the change's date."""
    if out["status"] == "denied":
        return reply_text(session, deps, thread, t("pp.not_allowed", deps.lang))
    reason = str(out["message"])
    key = REFUSALS.get(reason, "pp.refused")
    known = names(session, deps.organisation_id)
    params: dict[str, Any] = {
        "item": known.get(str(getattr(inp, "item_id", "") or ""), ""),
        "kiosk": known.get(str(getattr(inp, "kiosk_id", "") or ""), ""),
        "minutes": 0,
    }
    home = actions.commissary(session, deps.organisation_id)
    if reason == "capacity" and home is not None:
        s = orgconfig.load().production_planner
        day = getattr(inp, "production_date", None) or tools.production_day(home, s, db.utcnow())
        params["minutes"] = oven.free(session, home.id, day).minutes_free
    return reply_text(session, deps, thread, t(key, deps.lang, **params))


def _call(deps: AgentDeps, tool: str, inp: BaseModel) -> dict[str, Any]:
    return call_tool(deps, _BINDINGS[f"{MANIFEST.id}.{tool}"], inp, new_id())


def _delivered(
    session: Session, deps: AgentDeps, thread: Thread, done: tools.DispatchOut, known: replies.Names
) -> ChatReply:
    """Delivered, with a Delivered button per kiosk of that date still packed (listed through
    the dispatch_list tool, rbac first), so the card's other buttons live on in this reply."""
    text = t("pp.delivered.done", deps.lang, kiosk=known.get(done.branch_id, ""))
    listed = _call(deps, "dispatch_list", tools.DispatchInput(business_date=done.business_date))
    rows = tools.DispatchListOut.model_validate(listed).dispatches if "dispatches" in listed else []
    options = replies.delivered_options(rows, known, deps.lang)
    if not options:
        return reply_text(session, deps, thread, text)
    blocks: list[Block] = [TextBlock(text=text), QuickRepliesBlock(options=list(options))]
    return _ask(session, deps, thread, blocks, options)


def _result(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    tool: str,
    inp: BaseModel,
    out: dict[str, Any],
) -> ChatReply:
    """The reply of one successful tool result (tool is the name without the agent prefix)."""
    lang, known = deps.lang, names(session, deps.organisation_id)
    if tool == "plan":
        text = replies.plan_text(tools.PlanOut.model_validate(out), known, lang)
    elif tool == "change_plan":
        assert isinstance(inp, tools.ChangePlanInput)
        plan = tools.PlanOut.model_validate(out)
        text = replies.changed_text(plan, inp.item_id, known, lang)
    elif tool == "confirm_plan":
        day = tools.PlanOut.model_validate(out).production_date.isoformat()
        text = t("pp.plan.confirmed", lang, date=day)
    elif tool == "batch_sheet":
        text = replies.sheet_text(tools.SheetOut.model_validate(out), known, lang)
    elif tool == "set_recipe":
        assert isinstance(inp, tools.RecipeInput)
        text = replies.recipe_text(inp, known, lang)
    elif tool == "record_batch":
        text = replies.batch_text(tools.BatchOut.model_validate(out), known, lang)
    elif tool == "dispatch_list":
        rows = tools.DispatchListOut.model_validate(out).dispatches
        texts = [replies.dispatch_text(d, known, lang) for d in rows]
        text = "\n".join(texts) or t("pp.dispatch.none", lang)
    elif tool == "confirm_delivery":
        return _delivered(session, deps, thread, tools.DispatchOut.model_validate(out), known)
    else:  # capacity
        assert isinstance(inp, tools.CapacityInput)
        text = replies.capacity_text(tools.CapacityOut.model_validate(out), known, lang, inp)
    return reply_text(session, deps, thread, text)


def _run(
    session: Session, deps: AgentDeps, thread: Thread, action: str, args: dict[str, Any]
) -> ChatReply:
    """Run the action's tool through the guard (rbac first) and word the reply from its
    result or refusal."""
    spec = actions.ACTIONS[action]
    assert spec.tool is not None
    binding = _BINDINGS[f"{MANIFEST.id}.{spec.tool}"]
    try:
        inp = binding.input_type.model_validate(args)
    except ValidationError:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    out = _call(deps, spec.tool, inp)
    if "status" in out and "message" in out:  # a ToolRefusal
        return _refused(session, deps, thread, inp, out)
    return _result(session, deps, thread, spec.tool, inp, out)


def _plan_card(
    session: Session, deps: AgentDeps, thread: Thread, args: dict[str, Any]
) -> ChatReply:
    """The plan through the plan tool, with its Confirm button while it is a draft."""
    inp = tools.PlanInput.model_validate(args)
    out = _call(deps, "plan", inp)
    if "status" in out and "message" in out:
        return _refused(session, deps, thread, inp, out)
    plan = tools.PlanOut.model_validate(out)
    blocks, options = replies.plan_card(plan, names(session, deps.organisation_id), deps.lang)
    if not options:
        return store_reply(session, deps, thread, blocks)
    return _ask(session, deps, thread, blocks, options)


def _recipe_card(
    session: Session, deps: AgentDeps, thread: Thread, args: dict[str, Any]
) -> ChatReply:
    """A typed recipe: the card to check, its Save button the set_recipe decision with these
    args; nothing is stored before the tap. Without the right to set a recipe, refused."""
    if not get_rbac().check(deps.actor, SET_RECIPE, "execute", session=session):
        return reply_text(session, deps, thread, t("pp.not_allowed", deps.lang))
    try:
        inp = tools.RecipeInput.model_validate(args)
    except ValidationError:
        return reply_text(session, deps, thread, t("pp.recipe.unclear", deps.lang))
    units = {i.id: i.unit for i in session.exec(select(RetailIngredient))}
    known = names(session, deps.organisation_id)
    blocks = replies.recipe_card(inp, known, deps.lang, units)
    return _ask(session, deps, thread, blocks, replies.recipe_save(inp, deps.lang))


def _act(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision, negated: bool = False
) -> ChatReply:
    """Log the decision, then ask, show a card, run its tool through the guard, or word a
    conversation reply. A decision whose action is not one of ACTIONS (a tapped decision of
    another agent) asks to rephrase."""
    after = decision.model_dump(mode="json")
    events.emit(session, "decision.made", ("thread", thread.id), None, after, deps.actor)
    if decision.action == "clarify":
        return _clarify(session, deps, thread, decision)
    spec = actions.ACTIONS.get(decision.action)
    if spec is None:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    args = dict(decision.args)
    args.pop("card", None)  # plan_card's mark of its Confirm button (_holds)
    if decision.action == "confirm_plan" and negated:
        return _plan_card(session, deps, thread, args)
    if decision.action == "set_recipe" and not args.pop("save", False):
        return _recipe_card(session, deps, thread, args)
    if spec.tool is not None:
        return _run(session, deps, thread, decision.action, args)
    kind = str(args.get("kind", "other"))
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
    negated = query is not None and query.negated
    return await asyncio.to_thread(_act, session, deps, thread, decision, negated)


async def handle_turn(turn: Turn) -> ChatReply:
    """A tapped button or Jev's decision worded by code; reply.unavailable without Jev."""
    session, deps, thread = turn.session, turn.deps, turn.thread
    if get_settings().MIA_DECIDER != "jev":
        return await asyncio.to_thread(_unavailable, session, deps, thread)
    return await _jev_turn(session, deps, thread, turn.text, turn.ctx)


def run_due(session: Session, now: dt.datetime) -> int:
    """The planner's due work (due.run_due), imported here so this module never imports due."""
    from mia.agents.production_planner import due

    return due.run_due(session, now)


# 21 Oct 2026: the driver's phrases (tapos na ang hatid, naihatid, delivery done) were added
# after the router gate run 0749; its numbers stand, no rerun.
SPEC = AgentSpec(
    manifest=MANIFEST,
    label_key=f"agent.{MANIFEST.id}.label",
    router_description=(
        "The commissary's production: tomorrow's plan per item and its batches, batch sheets and"
        " recipes, yield and waste of a batch, the dispatch to each kiosk and its delivery (the"
        " driver's tapos na ang hatid, naihatid, delivery done), oven capacity for a date; not"
        " kiosk stock, not sales counts."
    ),
    handle_turn=handle_turn,
    run_due=run_due,
    stream_agent=None,
)
