"""Reply blocks for the customer service, worded from i18n keys. Code words every reply; no model
writes one. Money is in minor units through format_money, times on the branch clock."""

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.core.money import format_money
from mia.i18n import t

# ponytail: reply.not_built stands in for the agent's own capabilities key until it has tools
CAPABILITIES = "reply.not_built"
CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
}
# The precheck's refusal reasons a customer is told; any other refusal is cs.unavailable.
REFUSALS = ("too_large", "closed", "item", "area", "past", "order")
STATUSES = ("waiting", "confirmed", "ready", "picked_up")


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action: a greeting, thanks or goodbye, else (an
    injection included) what the agent can do."""
    return [TextBlock(text=t(CONVERSATION_KEYS.get(kind, CAPABILITIES), lang))]


def _text(key: str, lang: str, **params: object) -> list[Block]:
    return [TextBlock(text=t(key, lang, **params))]


def hhmm(when: dt.datetime | str, tz: str) -> str:
    """The time on the branch clock as HH:MM (an ISO string is parsed first)."""
    at = dt.datetime.fromisoformat(when) if isinstance(when, str) else when
    return f"{at.astimezone(ZoneInfo(tz)):%H:%M}"


def prices_line(items: list[dict[str, Any]], lang: str) -> str:
    """The priced items as "Classic ₱40.00, Puto bumbong ₱35.00"."""
    return ", ".join(f"{i['name']} {format_money(i['price'], i['currency'], lang)}" for i in items)


def ask_time(lang: str, times: list[str]) -> list[Block]:
    """Ask for the pickup time, with the open times as quick replies when there are any."""
    blocks: list[Block] = [TextBlock(text=t("cs.ask_time", lang))]
    return blocks + ([QuickRepliesBlock(options=times)] if times else [])


def refused(out: dict[str, Any], lang: str) -> list[Block]:
    """A precheck refusal in words (the reason may come quoted, as str(KeyError) does)."""
    reason = str(out.get("message", "")).strip("'")
    return _text(f"cs.refused.{reason}" if reason in REFUSALS else "cs.unavailable", lang)


def customer_reply(action: str, out: dict[str, Any], lang: str, tz: str) -> list[Block]:
    """The reply to one customer action from its tool output. A refusal the customer cannot
    act on (denied, an unknown reason) is cs.unavailable; an unknown action is the menu."""
    status = out.get("status")
    if status == "denied":
        return _text("cs.unavailable", lang)
    if status == "invalid" and action == "cancel_order":
        reason = str(out.get("message", "")).strip("'")
        return _text("cs.cancel_ready" if reason == "ready" else "cs.no_order", lang)
    if status == "invalid":
        return refused(out, lang)
    if action == "hours":
        opens = hhmm(out["next_open"], tz)
        if out["is_open"]:
            return _text("cs.open_until", lang, closes=hhmm(out["closes_at"], tz), opens=opens)
        return _text("cs.closed_now", lang, opens=opens)
    if action == "prices":
        return _text("cs.prices", lang, items=prices_line(out["items"], lang))
    if action == "delivery_area":
        if out["area"] is None:
            return _text("cs.no_delivery", lang, branch=out["pickup_branch"])
        fee = format_money(out["fee"], out["currency"], lang)
        return _text("cs.delivers", lang, area=out["area"], fee=fee)
    if action == "place_order":  # approval_required: the order waits for staff
        return _text("cs.order_waiting", lang, time=out["time"])
    if action == "order_status":
        known = status in STATUSES
        return _text(f"cs.status_{status}" if known else "cs.no_order", lang)
    if action == "cancel_order":
        return _text("cs.cancelled", lang)
    if action == "complaint":
        return _text("cs.complaint_thanks", lang)
    return _text("cs.menu", lang)
