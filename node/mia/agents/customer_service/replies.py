"""Reply blocks for the customer service, worded from i18n keys. Code words every reply; no model
writes one. Money is in minor units through format_money, times on the branch clock."""

import datetime as dt
from collections.abc import Sequence
from typing import Any
from zoneinfo import ZoneInfo

from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.core.money import format_money
from mia.core.orgconfig import DeliveryArea
from mia.i18n import t

# ponytail: reply.not_built stands in for the agent's own capabilities key until it has tools
CAPABILITIES = "reply.not_built"
CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
}
# The precheck's refusal reasons a customer is told; any other refusal is cs.unavailable.
REFUSALS = ("too_large", "closed", "item", "area", "past", "order", "pending")
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


def delivery_areas(areas: Sequence[DeliveryArea], branch: str, lang: str) -> list[Block]:
    """The configured delivery areas with their fees, or cs.no_delivery when there are none."""
    if not areas:
        return _text("cs.no_delivery", lang, branch=branch)
    listed = ", ".join(f"{a.name} {format_money(a.fee, a.currency, lang)}" for a in areas)
    return _text("cs.delivery_areas", lang, areas=listed, branch=branch)


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


# ---- the staff side -----------------------------------------------------------------------


def short_name(name: str | None) -> str:
    """How staff see a customer: the first name and the last name's initial ("Mila R.")."""
    parts = (name or "").split()
    if not parts:
        return "?"
    return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else parts[0]


def order_line(time: str, who: str, lines: list[tuple[str, int]]) -> str:
    """One order as "15:00 Mila R. (Classic x10)"."""
    items = ", ".join(f"{name} x{quantity}" for name, quantity in lines)
    return f"{time} {who} ({items})"


def orders_line(orders: list[str]) -> str:
    """The order lines of a list or digest, in pickup order."""
    return "; ".join(orders)


STAFF_DONE = {"mark_ready": "cs.staff.marked_ready", "mark_picked_up": "cs.staff.marked_picked_up"}


def staff_reply(
    tool: str, out: dict[str, Any], names: dict[str, str], lang: str, tz: str
) -> list[Block]:
    """The reply to one staff tool from its output; `names` holds each order's short_name by
    order id. A denial is denied.generic; any other refusal (an order not open, not found)
    is cs.staff.cannot_mark."""
    status = out.get("status")
    if status == "denied":
        return _text("denied.generic", lang)
    if status == "invalid":
        return _text("cs.staff.cannot_mark", lang)
    if tool == "orders_today":
        lines = [
            order_line(
                hhmm(o["pickup_at"], tz),
                names.get(o["order_id"], o["customer"]),
                [(ln["name"], ln["quantity"]) for ln in o["lines"]],
            )
            for o in out["orders"]
        ]
        if not lines:
            return _text("cs.no_orders_today", lang)
        return _text("cs.orders_today", lang, orders=orders_line(lines))
    who = names.get(str(out.get("order_id")), "?")
    return _text(STAFF_DONE[tool], lang, who=who)
