"""Ask Jev which inventory manager action a message wants and with which inputs (see
mia.agents.decider). decide() runs no tool."""

from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.decider import Alternative, Decision, Reader
from mia.agents.inventory_manager.actions import (
    ACTIONS,
    CONVERSATION,
    KINDS,
    NONE,
    NOW,
    REASONS,
    Query,
    build_request,
)
from mia.agents.parsing import has_buy_word


def _item(r: Reader, i: int) -> str | None:
    """The item or ingredient picked for group i; None for none or an unsure pick (the caller
    reports item_<i> missing)."""
    pick = r.pick(f"item_{i}", {*r.q.items, NONE}, fallback=True)
    return None if pick == NONE else pick


def _at(r: Reader) -> str | None:
    """The picked time as "HH:MM", or None for now."""
    pick = r.pick("time", {*r.q.times, NOW})
    return None if pick in (None, NOW) else r.q.times[pick]


def _lines(r: Reader) -> tuple[list[dict[str, Any]], str | None]:
    """Order or delivery lines from the groups picked as ingredients (an item pick is not a
    stock line); the missing input is item_<i> for a group with no sure pick."""
    q: Query = r.q
    lines: list[dict[str, Any]] = []
    for i, g in enumerate(q.groups):
        pick = _item(r, i)
        if pick is None or g.quantity is None:
            return [], f"item_{i}"
        if q.kinds[pick] == "ingredient":
            lines.append({"ingredient_id": pick, "quantity": g.quantity, "unit": q.units[pick]})
    return lines, None if lines else "lines"


def _event(
    r: Reader, kind: str, ref: str, quantity: int | None, reason: str | None
) -> dict[str, Any]:
    """One record_events event about the item or ingredient `ref` (the unit is the
    ingredient's; the reason only on waste; the picked time or none for now)."""
    q: Query = r.q
    is_ing = q.kinds[ref] == "ingredient"
    return {
        "kind": kind,
        "item_id": None if is_ing else ref,
        "ingredient_id": ref if is_ing else None,
        "quantity": quantity,
        "unit": q.units[ref] if is_ing else None,
        "reason": reason if kind == "waste" else None,
        "at": _at(r),
    }


ON_HAND = "on_hand"
ASKS = ("count", "leftover")  # these kinds with no number ask how many are left


def _report(r: Reader) -> tuple[dict[str, Any], str | None]:
    """record_events input. A bare count is `count`; a negation on a count simply records the
    count (no correction action in v1). A count or leftover with no number is the question
    how many are left: the event of the item, marked ON_HAND (the turn runs on_hand). An unsure reason is not stated (it does not count
    toward the confidence), so a waste asks for it with the reason buttons."""
    q: Query = r.q
    kind = r.pick("kind", set(KINDS))
    reason = r.pick("reason", set(REASONS), fallback=True) if kind == "waste" else None
    events: list[dict[str, Any]] = []
    if q.groups:
        for i, g in enumerate(q.groups):
            ref = _item(r, i)
            if ref is None or g.quantity is None:
                return {"events": []}, f"item_{i}"
            events.append(_event(r, kind or "count", ref, g.quantity, reason))
    else:
        ref = r.pick("item", set(q.items), fallback=True)
        if ref is None:
            return {"events": []}, "item"
        if kind is None:
            return {"events": []}, "kind"
        if kind in ASKS:  # no number: "how many are left", never a count of nothing
            return _event(r, kind, ref, None, None) | {ON_HAND: True}, None
        events.append(_event(r, kind, ref, None, reason))
    args = {"events": events, "source_message_id": q.message_id}
    return args, "reason" if kind == "waste" and reason is None else None


def _args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required input that is missing, if any."""
    q: Query = r.q
    if action == "report_stock":
        return _report(r)
    if action == "place_order":
        lines, missing = _lines(r)
        stated = r.pick("supplier", set(q.suppliers))
        fitting = {
            q.supplier_of[ln["ingredient_id"]]
            for ln in lines
            if ln["ingredient_id"] in q.supplier_of
        }
        supplier = stated or (next(iter(fitting)) if len(fitting) == 1 else None)
        return {"supplier": supplier, "lines": lines}, missing or (None if supplier else "supplier")
    if action == "receive":
        lines, missing = _lines(r)
        return {"lines": lines}, missing
    if action == "answer_offer":
        if not q.offer_asked:
            return {}, "offer"
        answer = r.pick("answer", {"yes", "no"})
        return {"yes": answer == "yes"}, None if answer else "answer"
    if action == "reply_only":
        return {"kind": r.pick("conversation", set(CONVERSATION)) or "other"}, None
    return {}, None  # bake_plan, whats_low, clarify


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for an answer outside the options) when no usable answer came."""
    return await shared.decide(q, build_request=build_request, parse=partial(parse, q=q))


def parse(answers: dict[str, Any], q: Query) -> Decision:
    """shared.parse, then an order with no buy word in the message (parsing.has_buy_word)
    becomes clarify with place_order as the first alternative: a count is never ordered
    silently."""
    d = shared.parse(answers, q, actions=ACTIONS, args=_args)
    if d.action != "place_order" or has_buy_word(q.message):
        return d
    first = Alternative(action=d.action, args=d.args, probability=d.confidence)
    return d.model_copy(update={"action": "clarify", "alternatives": [first, *d.alternatives][:3]})
