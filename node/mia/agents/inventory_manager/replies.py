"""Reply blocks for the inventory manager: each tool result worded from i18n keys (times as
"HH:MM" in the branch's zone, money through format_money, counts through format_int), the
conversation replies, and the questions this agent asks (why it was thrown away, shall I draft
an order). Code words every reply; no model writes one."""

import copy
import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from mia.agents.decider import Decision
from mia.agents.inventory_manager.tools import (
    EventOut,
    LowOut,
    LowStockOutput,
    OnHandOutput,
    PlanOutput,
    ReceiveDeliveryOutput,
    RecordEventsOutput,
)
from mia.chat.blocks import ApprovalCardBlock, Block, CardField, QuickRepliesBlock, TextBlock
from mia.core.money import format_int, format_money
from mia.i18n import t

CAPABILITIES = "stock.capabilities"
CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
}
REASONS = ("too_dry", "burnt", "expired", "dropped", "other")
EVENT_KEYS = {
    "sold_out": "stock.sold_out",
    "count": "stock.counted",
    "leftover": "stock.leftover",
    "waste": "stock.waste",
    "low": "stock.low",
    "received": "stock.received",
}

# (label, the stored decision a tap runs)
Options = dict[str, dict[str, Any]]


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action: a greeting, thanks or goodbye, else (an
    injection included) what the agent can do."""
    return [TextBlock(text=t(CONVERSATION_KEYS.get(kind, CAPABILITIES), lang))]


def _hhmm(at: dt.datetime, zone: str) -> str:
    return at.astimezone(ZoneInfo(zone)).strftime("%H:%M")


def event_line(e: EventOut, lang: str, zone: str) -> str:
    """One recorded stock event in words; a waste without a reason reads as other."""
    quantity = "" if e.quantity is None else format_int(e.quantity, lang)
    return t(
        EVENT_KEYS[e.kind],
        lang,
        item=e.name,
        ingredient=e.name,
        quantity=quantity,
        unit=e.unit or "",
        time=_hhmm(e.at, zone),
        reason=t(f"stock.reason.{e.reason or 'other'}", lang),
    )


def _text(key: str, lang: str, **values: Any) -> list[Block]:
    return [TextBlock(text=t(key, lang, **values))]


def _low_line(i: LowOut, lang: str) -> str:
    """One low ingredient: its count against the reorder point, or reported low (never counted)."""
    key = "stock.low_list.line" if i.latest_count is not None else "stock.low_list.reported"
    return t(
        key,
        lang,
        ingredient=i.name,
        count=format_int(i.latest_count or 0, lang),
        unit=i.unit,
        reorder=format_int(i.reorder_point, lang),
    )


def tool_reply(
    tool: str, out: dict[str, Any], args: dict[str, Any], lang: str, zone: str
) -> list[Block]:
    """The reply to one successful tool result (tool is the name without the agent prefix;
    zone is the branch's time zone, for the times said)."""
    if tool in ("record_events", "receive_delivery"):
        model = RecordEventsOutput if tool == "record_events" else ReceiveDeliveryOutput
        recorded = model.model_validate(out).recorded
        return [TextBlock(text=event_line(e, lang, zone)) for e in recorded]
    if tool == "plan_tomorrow":
        plan = PlanOutput.model_validate(out)
        said = [TextBlock(text=t(f"stock.plan.{p.plan}", lang, item=p.item)) for p in plan.lines]
        return [*said, *(_text("stock.plan.heuristic", lang) if plan.note_heuristic else [])]
    if tool == "on_hand":
        left = OnHandOutput.model_validate(out)
        if left.quantity is None:
            return _text("stock.not_counted", lang, item=left.name, branch=left.branch)
        quantity = " ".join(filter(None, [format_int(left.quantity, lang), left.unit]))
        return _text("stock.on_hand", lang, quantity=quantity, item=left.name, branch=left.branch)
    if tool == "low_stock":
        low = LowStockOutput.model_validate(out).ingredients
        if not low:
            return _text("stock.low_list.empty", lang)
        return [TextBlock(text=_low_line(i, lang)) for i in low]
    return _text("clarify.rephrase", lang)


def order_text(
    supplier: str,
    lines: list[tuple[int, str, str]],
    total: int | None,
    currency: str,
    lang: str,
) -> str:
    """An order waiting for approval in words: (quantity, unit, ingredient) lines and the total
    when every price is known."""
    said = ", ".join(
        t("stock.order_line", lang, quantity=format_int(q, lang), unit=u, ingredient=name)
        for q, u, name in lines
    )
    money = (
        ""
        if total is None
        else t("stock.order_total", lang, total=format_money(total, currency, lang))
    )
    return t("stock.order_waiting", lang, supplier=supplier, lines=said, total=money)


def order_waiting(text: str, approval_id: str, lang: str) -> list[Block]:
    """The order waiting reply with its approval card (the owner decides it in the app); the
    status field shows the status the card carries."""
    card = ApprovalCardBlock(
        approval_id=approval_id, title=t("stock.approval_title", lang), summary=text
    )
    card.fields = [CardField(label=t("field.status", lang), value=card.status)]
    return [TextBlock(text=text), card]


def _asked(decision: Decision, args: dict[str, Any]) -> dict[str, Any]:
    """The decision a button runs: the action that was meant, with the completed args."""
    action = decision.raw_action or decision.action
    return Decision(action=action, args=args, confidence=1.0, raw_action=action).model_dump(
        mode="json"
    )


def _wasted(events: list[dict[str, Any]], names: dict[str, str], lang: str) -> str:
    """The waste events as "8 Classic, 2 tray Eggs": what a reason button writes."""
    said = []
    for e in events:
        name = names.get(e.get("item_id") or e.get("ingredient_id") or "", "")
        quantity = "" if e.get("quantity") is None else format_int(e["quantity"], lang)
        line = t(
            "stock.order_line", lang, quantity=quantity, unit=e.get("unit") or "", ingredient=name
        )
        said.append(" ".join(line.split()))  # no double space without a unit or a quantity
    return ", ".join(said)


def ask_reason(decision: Decision, names: dict[str, str], lang: str) -> tuple[list[Block], Options]:
    """Why it was thrown away: the question names each waste event that will be written (its
    quantity, unit and name from `names`, id to name), and one button per reason runs the same
    report with the reason filled in on every waste event."""
    wasted = [e for e in decision.args.get("events") or [] if e.get("kind") == "waste"]
    options: Options = {}
    for reason in REASONS:
        args = copy.deepcopy(decision.args)
        for event in args.get("events") or []:
            if event.get("kind") == "waste":
                event["reason"] = reason
        options[t(f"stock.reason.{reason}", lang)] = _asked(decision, args)
    blocks: list[Block] = [
        TextBlock(text=t("stock.which_reason", lang, items=_wasted(wasted, names, lang))),
        QuickRepliesBlock(options=list(options)),
    ]
    return blocks, options


def ask_offer(ingredient: str, order: dict[str, Any], lang: str) -> tuple[list[Block], Options]:
    """Shall I draft an order for the ingredient: Yes carries the order (draft_order input),
    No declines. The question is its own text block, so offer_texts finds it next turn."""
    options: Options = {}
    for key, yes in (("stock.offer.yes", True), ("stock.offer.no", False)):
        args = {"yes": yes, **(order if yes else {})}
        chosen = Decision(action="answer_offer", args=args, confidence=1.0)
        options[t(key, lang)] = chosen.model_dump(mode="json")
    blocks: list[Block] = [
        TextBlock(text=t("stock.offer_order", lang, ingredient=ingredient)),
        QuickRepliesBlock(options=list(options)),
    ]
    return blocks, options
