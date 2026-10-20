"""Ask Jev which branch manager action a message wants and with which inputs (see
mia.agents.decider). Every value comes from the query's candidates (a price is one code parsed,
never one Jev computed). decide() runs no tool."""

from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.branch_manager.actions import ACTIONS, CONVERSATION, KINDS, Query, build_request
from mia.agents.decider import NOT_STATED, Decision, Reader


def _pick(r: Reader, slot: str, options: dict[str, Any]) -> str | None:
    return r.pick(slot, set(options)) if options else None


def _propose(r: Reader) -> tuple[dict[str, Any], str | None]:
    """No item: {} (the turn offers the engine's suggestion). No price: missing price, unless a
    strategy is picked (to_price None: the tool sizes it through experiments.propose). No
    start: the next open day. strategy_id None is refused by the tool (no_strategy)."""
    q: Query = r.q
    item = _pick(r, "item", q.items)
    if item is None:
        return {}, None
    price = _pick(r, "price", q.prices)
    start = _pick(r, "start", q.dates)
    args = {
        "item_id": item,
        "to_price": q.prices[price] if price else None,
        "starts_on": q.dates[start] if start else q.next_open_day,
        "kind": r.pick("kind", set(KINDS) - {NOT_STATED}) or "price",
        "strategy_id": _pick(r, "strategy", q.strategies),
    }
    return args, None if price or args["strategy_id"] else "price"


def _change_price(r: Reader) -> tuple[dict[str, Any], str | None]:
    q: Query = r.q
    item = _pick(r, "item", q.items)
    price = _pick(r, "price", q.prices)
    day = _pick(r, "date", q.dates)
    args = {
        "item_id": item,
        "price": q.prices[price] if price else None,
        "effective_on": q.dates[day] if day else None,
    }
    return args, "item" if not item else "price" if not price else None if day else "date"


def _args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required input that is missing, if any."""
    q: Query = r.q
    if action == "propose_experiment":
        return _propose(r)
    if action == "change_price":
        return _change_price(r)
    if action == "how_to_sell":
        item = _pick(r, "item", q.items)
        return {"item_id": item}, None if item else "item"
    if action == "set_short_code":
        item, code = _pick(r, "item", q.items), _pick(r, "code", q.codes)
        args = {"item_id": item, "code": q.codes[code] if code else None}
        return args, "item" if not item else None if code else "code"
    if action == "coaching_who":
        return {"person_id": _pick(r, "person", q.people)}, None
    if action == "decide_experiment_result":
        return {"keep": r.yes("keep")}, None
    if action == "reply_only":
        return {"kind": r.pick("conversation", set(CONVERSATION)) or "other"}, None
    return {}, None  # experiment_status, weekly_summary, monthly_letter, clarify


def parse(answers: dict[str, Any], q: Query) -> Decision:
    """shared.parse; an action outside ACTIONS becomes clarify, keeping Jev's pick as
    raw_action."""
    top = answers.get("action")
    raw = str(top.get("choice")) if isinstance(top, dict) else ""
    if not isinstance(top, dict) or raw in ACTIONS:
        return shared.parse(answers, q, actions=ACTIONS, args=_args)
    d = shared.parse(
        {**answers, "action": {**top, "choice": "clarify"}}, q, actions=ACTIONS, args=_args
    )
    return d.model_copy(update={"raw_action": raw})


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for a malformed answer) when no usable answer came."""
    return await shared.decide(q, build_request=build_request, parse=partial(parse, q=q))
