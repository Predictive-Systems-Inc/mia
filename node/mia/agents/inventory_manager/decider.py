"""Ask Jev which inventory manager action a message wants and with which inputs (see
mia.agents.decider). decide() runs no tool."""

import re
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
# Rule 7: the words that say stock was thrown away or lost, across the languages (machine
# drafts beyond en and fil, Q28 to Q35). With one, any kind but waste asks the kind: a waste is
# never recorded as a count. Whole words only ("pagsira", the closing, is not "sira").
WASTE_WORDS = frozenset({
    "waste", "wasted", "trash", "garbage", "threw", "thrown", "throw", "dropped", "spoiled",
    "expired", "burnt", "burned",
    "tapon", "itapon", "tinapon", "itinapon", "natapon", "basura", "basurahan", "sira",
    "nasira", "sayang", "nasayang", "panis", "napanis", "sunog", "nasunog", "nahulog",
    "labay", "ilabay", "gilabay", "gilabayan", "nausik", "usik", "napanos", "panos",
    "haboy", "ihaboy", "ginhaboy", "ginpanhaboy", "labog", "ilabog", "ginlabog", "ginlabugan",
    "pinanlabog",
})  # fmt: skip


# Rule 7: the words that state what a number of stock is (count, leftover, sold out, low,
# received), en and fil, with the local words of KINDS (machine drafts, Q28 to Q35). A number
# with none of these, no WASTE_WORDS word and no count asked by Mia is a bare item and number:
# the kind is asked with the kind buttons, never guessed ("eggs 10" was a count of 10 trays).
KIND_WORDS = frozenset({
    "left", "leftover", "leftovers", "remaining", "remain", "remains", "only", "still", "count",
    "counted", "sold", "out", "finished", "gone", "low", "unsold", "received", "arrived",
    "delivered", "delivery", "stock", "have", "got",
    "lang", "la", "sana", "pa", "nlng", "nalang", "nlang", "lng", "natitira", "natira", "tira", "naiwan", "sobra", "salin",
    "ubos", "naubos", "wala", "paubos", "konti", "kaunti", "bilang", "nabilang", "dumating",
    "natanggap", "meron", "mayroon", "may", "nabilin", "bilin", "nahabilin", "yara", "aada",
    "yaon", "natada", "naa", "igwa", "hurot", "nahurot", "mayo", "gamay", "diutay", "dikit",
    "kulang", "nabati", "natamban", "metda",
})  # fmt: skip
# A how-many question: one of these words, or "pa" with "ba" or "bang" ("may ube pa ba",
# "may ube pa bang natira").
# With no number it is the on_hand read whatever kind is picked, never a stock event (rule 7).
QUESTION_WORDS = frozenset({"ilan", "ilang", "gaano"})
QUESTION_PHRASES = ("how many", "how much", "magkano pa", "meron pa", "mayroon pa")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _says_waste(text: str) -> bool:
    return any(w in WASTE_WORDS for w in _words(text))


def _says_kind(text: str) -> bool:
    return any(w in KIND_WORDS or w in WASTE_WORDS for w in _words(text))


def _asks_how_many(text: str) -> bool:
    words = _words(text)
    joined = f" {' '.join(words)} "
    return (
        any(w in QUESTION_WORDS for w in words)
        or any(f" {p} " in joined for p in QUESTION_PHRASES)
        or ("pa" in words and bool({"ba", "bang"} & set(words)))
    )


def _report(r: Reader) -> tuple[dict[str, Any], str | None]:
    """record_events input. A bare count is `count`; a negation on a count simply records the
    count (no correction action in v1). A count or leftover with no number is the question
    how many are left: the event of the item, marked ON_HAND (the turn runs on_hand). An unsure reason is not stated (it does not count
    toward the confidence), so a waste asks for it with the reason buttons; a waste with no
    number is missing its quantity. No kind and no number is the on_hand question too, unless a
    WASTE_WORDS word is said; with one, any kind but waste asks the kind (rule 7). A how-many
    question (QUESTION_WORDS) with no number is the on_hand read, whatever the kind pick. A
    number with no kind word (KIND_WORDS, WASTE_WORDS) asks the kind with its events, unless
    Mia's last message said each item is not counted yet (count_asked: then it is a count); a
    question with a number (QUESTION_WORDS or a "?") always asks the kind."""
    q: Query = r.q
    if not q.groups and _asks_how_many(q.message):  # decisive before the kind pick
        ref = r.pick("item", set(q.items), fallback=True)
        if ref is None:
            return {"events": []}, "item"
        return _event(r, "count", ref, None, None) | {ON_HAND: True}, None
    kind = r.pick("kind", set(KINDS))
    reason = r.pick("reason", set(REASONS), fallback=True) if kind == "waste" else None
    waste_said = _says_waste(q.message)
    if waste_said and kind != "waste" and (kind is not None or q.groups):
        return {"events": []}, "kind"  # "4 nga classic ginlabog" is never a count of 4
    events: list[dict[str, Any]] = []
    if q.groups:
        for i, g in enumerate(q.groups):
            ref = _item(r, i)
            if ref is None or g.quantity is None:
                return {"events": []}, f"item_{i}"
            events.append(_event(r, kind or "count", ref, g.quantity, reason))
        asked = {"events": events, "source_message_id": q.message_id}
        if _asks_how_many(q.message) or "?" in q.message:  # a question is never a count
            return asked, "kind"
        refs = {e["item_id"] or e["ingredient_id"] for e in events}
        if refs <= q.count_asked:  # Mia said these are not counted yet: the number is a count
            for e in events:
                e.update(kind="count", reason=None)
        elif not _says_kind(q.message):  # a bare item and number
            return asked, "kind"
    else:
        ref = r.pick("item", set(q.items), fallback=True)
        if ref is None:
            return {"events": []}, "item"
        if kind is None and waste_said:
            return {"events": []}, "kind"
        if kind is None or kind in ASKS:  # no number: "how many are left", a read, never a write
            return _event(r, kind or "count", ref, None, None) | {ON_HAND: True}, None
        if kind == "waste":  # no number: ask how many, never a waste of nothing (rule 7)
            return {"events": [_event(r, kind, ref, None, reason)]}, "quantity"
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
    alternatives = [first, *d.alternatives][:3]
    return d.model_copy(update={"action": "clarify", "alternatives": alternatives, "guarded": True})
