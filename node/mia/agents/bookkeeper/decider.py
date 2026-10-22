"""Ask Jev which bookkeeper action a message wants and with which inputs (see
mia.agents.decider). Every value comes from the query's candidates: an amount is one code
parsed and Jev picked by id, a provider, category, period or bank a fixed-list value. decide()
runs no tool."""

import datetime as dt
from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.bookkeeper import words
from mia.agents.bookkeeper.actions import (
    ACTIONS,
    CATEGORIES,
    CONVERSATION,
    PETTY,
    SOURCES,
    Query,
    build_request,
    providers,
)
from mia.agents.decider import Alternative, Decision, Reader


def _amount(r: Reader) -> int | None:
    q: Query = r.q
    picked = r.pick("amount", set(q.amounts)) if q.amounts else None
    return q.amounts[picked] if picked else None


def _period(r: Reader, default: str | None) -> tuple[dt.date, dt.date] | None:
    """The picked period or date as (first, last day); the default period when none is."""
    q: Query = r.q
    picked = r.pick("period", {*q.periods, *q.dates})
    if picked in q.dates:
        day = dt.date.fromisoformat(q.dates[picked])
        return day, day
    key = picked or default
    return words.period_of(key, q.today) if key else None


def _provider(r: Reader, allowed: tuple[str, ...]) -> str | None:
    """Jev's pick among the offered providers when it is one of `allowed`; a message that names
    one allowed provider by its tender word gives it when Jev says not stated."""
    offered = providers(r.q)
    picked = r.pick("provider", set(offered)) or (offered[0] if len(offered) == 1 else None)
    return picked if picked in allowed else None


def _match(r: Reader, allowed: tuple[str, ...], default: str) -> tuple[dict[str, Any], str | None]:
    amount, provider = _amount(r), _provider(r, allowed)
    span = _period(r, default)
    assert span is not None
    args = {"provider": provider, "amount": amount, "start": span[0], "end": span[1]}
    return args, "amount" if amount is None else None if provider else "provider"


def _cash_count(r: Reader) -> tuple[dict[str, Any], str | None]:
    """A picked day (today aside: the tool takes the branch's business date) or None."""
    q: Query = r.q
    amount, span = _amount(r), _period(r, None)
    day = span[0] if span and span[0] != q.today else None
    args = {"counted": amount, "business_date": day, "source_message_id": q.message_id}
    return args, None if amount is not None else "amount"


def _args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required input that is missing, if any."""
    q: Query = r.q
    if action == "cash_count":
        return _cash_count(r)
    if action == "settlement":
        return _match(r, words.SETTLERS, "yesterday")
    if action == "payout":
        return _match(r, words.PLATFORMS, "last_week")
    if action == "expense":
        amount, category = _amount(r), r.pick("category", set(CATEGORIES))
        args = {
            "category": category,
            "amount": amount,
            "vat_amount": q.vat_amount,
            "receipt_no": q.receipt_no,
            "source": r.pick("source", set(SOURCES)) or "cash",
        }
        return args, "amount" if amount is None else None if category else "category"
    if action == "petty_cash":
        amount = _amount(r)
        kind = r.pick("petty", set(PETTY)) or ("spend" if words.says_spend(q.message) else None)
        # rule 7: a refill word against a spend pick, or a spend word against a refill pick,
        # asks the kind ("pinunan ko ang petty cash, 3,500" is never a spend)
        if (kind == "spend" and words.says_refill(q.message)) or (
            kind == "refill" and words.says_spend(q.message)
        ):
            kind = None
        args = {
            "kind": kind,
            "amount": amount,
            "category": r.pick("category", set(CATEGORIES)) or "supplies",
        }
        return args, "amount" if amount is None else None if kind else "kind"
    if action == "deposit":
        amount, bank = _amount(r), r.pick("bank", set(q.banks or words.BANKS))
        args = {"bank": bank, "amount": amount, "reference": None}
        return args, "amount" if amount is None else None if bank else "bank"
    if action in ("journal", "profit"):
        span = _period(r, "last_month")
        assert span is not None
        return {"month": span[0].replace(day=1)}, None
    if action == "tax_quarter":
        span = _period(r, "this_quarter")
        assert span is not None
        return {"quarter_start": words.period_of("this_quarter", span[0])[0]}, None
    if action == "reply_only":
        return {"kind": r.pick("conversation", set(CONVERSATION)) or "other"}, None
    return {}, None  # balances, not_built, clarify


COUNT_OR_EXPENSE = ("cash_count", "expense")


def _count_or_expense(answers: dict[str, Any], q: Query, d: Decision) -> Decision:
    """An expense pick in a message with a count word of its language and an amount: clarify
    with the cash count and the expense as the alternatives, each with Jev's picked amount (an
    alternative missing an input is not offered as a button)."""
    probabilities = answers["action"].get("probabilities") or {}
    alternatives = []
    for action in COUNT_OR_EXPENSE:
        args, missing = _args(action, Reader(answers, q))
        p = float(probabilities.get(action, 0.0))
        alternatives.append(Alternative(action=action, args=args, probability=p, missing=missing))
    update = {"action": "clarify", "missing": None, "alternatives": alternatives, "guarded": True}
    return d.model_copy(update=update)


def parse(answers: dict[str, Any], q: Query) -> Decision:
    """shared.parse; an action outside ACTIONS becomes clarify, keeping Jev's pick as
    raw_action. An expense pick with a count word of the message's language (words.says_count:
    "pagsira" is the closing in ceb and hil) and an amount asks cash count or expense, never
    writes."""
    top = answers.get("action")
    raw = str(top.get("choice")) if isinstance(top, dict) else ""
    if not isinstance(top, dict) or raw in ACTIONS:
        d = shared.parse(answers, q, actions=ACTIONS, args=_args)
        if d.raw_action == "expense" and q.amounts and words.says_count(q.message, q.lang):
            return _count_or_expense(answers, q, d)
        return d
    d = shared.parse(
        {**answers, "action": {**top, "choice": "clarify"}}, q, actions=ACTIONS, args=_args
    )
    return d.model_copy(update={"raw_action": raw, "guarded": True})


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for a malformed answer) when no usable answer came."""
    return await shared.decide(q, build_request=build_request, parse=partial(parse, q=q))
