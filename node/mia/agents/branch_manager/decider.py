"""Ask Jev which branch manager action a message wants and with which inputs (see
mia.agents.decider). Every value comes from the query's candidates (a price is one code parsed,
never one Jev computed). decide() runs no tool."""

from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.branch_manager.actions import (
    ACTIONS,
    CONVERSATION,
    KINDS,
    PERSON_LANGUAGES,
    PERSON_ROLES,
    Query,
    build_request,
)
from mia.agents.decider import NOT_STATED, Decision, Reader
from mia.core.people import HUMAN_ROLES

# Rule 7: a role word or a common shop noun is never a short code ("bf na ang i-type sang clerk
# para sa Box of 4" names bf, never clerk). A picked candidate in this list asks for the code.
# ponytail: a fixed list beside actions.NOT_CODES; fold the two together if they keep growing.
ROLE_WORDS = frozenset({
    *HUMAN_ROLES, "cashier", "crew", "kiosk", "stall", "branch", "mall", "shop", "store",
    "boss", "amo", "bantay", "tindera", "tindero", "helper", "baker", "rider", "driver",
    "buyer", "client", "guest", "user", "mia", "menu", "price", "presyo", "team", "worker",
    "lahat", "tanan", "sila", "kami", "tayo", "kita", "namon", "aton", "subong", "ngayon",
    "karon", "yana", "ngunyan", "umpisa", "simula", "itype",
})  # fmt: skip


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


def _add_person(r: Reader) -> tuple[dict[str, Any], str | None]:
    """The name from the code's candidates and a role ask when missing; the branch defaults to
    the sender's (the tool's), the language to fil; a phone only when code found one."""
    q: Query = r.q
    name = _pick(r, "new_name", q.names)
    role = r.pick("role", set(PERSON_ROLES))
    branch = _pick(r, "branch", q.branches)
    args = {
        "name": q.names[name] if name else None,
        "role": role,
        "branch_id": branch,
        "language": r.pick("language", set(PERSON_LANGUAGES)) or "fil",
        "phone": q.phone or None,
    }
    return args, "name" if not name else None if role else "role"


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
        if code and q.codes[code].casefold() in ROLE_WORDS:
            code = None  # a role or common word: ask for the code
        args = {"item_id": item, "code": q.codes[code] if code else None}
        return args, "item" if not item else None if code else "code"
    if action == "coaching_who":  # an item only when one is named ("sino magaling sa ube")
        args = {"person_id": _pick(r, "person", q.people)}
        if item := _pick(r, "item", q.items):
            args["item_id"] = item
        return args, None
    if action == "add_person":
        return _add_person(r)
    if action == "set_phone":
        person = _pick(r, "person", q.people)
        args = {"person_id": person, "phone": q.phone or None}
        return args, "person" if not person else None if q.phone else "phone"
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
