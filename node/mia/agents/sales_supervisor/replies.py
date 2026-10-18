"""Reply blocks for the sales supervisor: each tool result worded from i18n keys (money through
format_money, counts through format_int), the conversation replies, and the two questions this
agent asks (which day, which item). Code words the numbers; no model writes a reply."""

import copy
import datetime as dt
from typing import Any

from mia.agents.decider import Decision
from mia.agents.sales_supervisor import calc
from mia.agents.sales_supervisor.tools import (
    CorrectCountOutput,
    PeriodReportOutput,
    RecordCountsOutput,
    SetTargetOutput,
    TodayOutput,
)
from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.core.money import format_int, format_money
from mia.i18n import t

CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
    "capabilities": "sales.capabilities",
    "injection": "sales.capabilities",  # an instruction in a message is data: offer help only
    "other": "sales.capabilities",
}

# (label, the stored decision a tap runs)
Options = dict[str, dict[str, Any]]


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action (unknown kinds get the capabilities)."""
    return [TextBlock(text=t(CONVERSATION_KEYS.get(kind, "sales.capabilities"), lang))]


def _target(total: int, share: int | None, currency: str, lang: str) -> str:
    """ " of <share> (<percent of the share reached>%)", or "" without a target."""
    diff = calc.compare(total, share)
    if share is None or diff is None:
        return ""
    money = format_money(share, currency, lang)
    return t("sales.target_part", lang, share=money, percent=format_int(diff + 100, lang))


def _lines(rows: list[tuple[int, str]], lang: str) -> str:
    return ", ".join(
        t("sales.recorded.line", lang, quantity=format_int(q, lang), item=item) for q, item in rows
    )


def _text(key: str, lang: str, **values: Any) -> list[Block]:
    return [TextBlock(text=t(key, lang, **values))]


def tool_reply(tool: str, out: dict[str, Any], args: dict[str, Any], lang: str) -> list[Block]:
    """The reply to one successful tool result (tool is the name without the agent prefix;
    args is the tool input, for the period's dates)."""
    if tool == "record_counts":
        rec = RecordCountsOutput.model_validate(out)
        lines = _lines([(c.quantity, c.item) for c in rec.recorded], lang)
        total = format_money(rec.day_total, rec.currency, lang)
        target = _target(rec.day_total, rec.target_share, rec.currency, lang)
        return _text("sales.recorded", lang, lines=lines, total=total, target=target)
    if tool == "correct_count":
        cor = CorrectCountOutput.model_validate(out)
        quantity, previous = (
            format_int(n, lang) for n in (cor.corrected.quantity, cor.previous_quantity)
        )
        return _text(
            "sales.corrected", lang, quantity=quantity, item=cor.corrected.item, previous=previous
        )
    if tool == "today":
        day = TodayOutput.model_validate(out)
        if not day.items:
            return _text("sales.today.empty", lang, branch=day.branch)
        lines = _lines([(i.quantity, i.item) for i in day.items], lang)
        total = format_money(day.total, day.currency, lang)
        target = _target(day.total, day.target_share, day.currency, lang)
        return _text(
            "sales.today", lang, branch=day.branch, lines=lines, total=total, target=target
        )
    if tool == "period_report":
        rep = PeriodReportOutput.model_validate(out)
        start, end = str(args["start"]), str(args["end"])
        if rep.best_day is None:
            return _text("sales.period.empty", lang, start=start, end=end)
        total = format_money(rep.total, rep.currency, lang)
        best = rep.best_day.isoformat()
        return _text("sales.period", lang, start=start, end=end, total=total, best_day=best)
    if tool == "set_target":
        st = SetTargetOutput.model_validate(out)
        when = st.starts_on.isoformat() if st.period == "day" else st.starts_on.strftime("%Y-%m")
        amount = format_money(st.amount, st.currency, lang)
        return _text("sales.target_set", lang, amount=amount, when=when)
    return _text("sales.note_thanks", lang)  # record_note


def _asked(decision: Decision, args: dict[str, Any]) -> dict[str, Any]:
    """The decision a button runs: the action that was meant, with the completed args."""
    action = decision.raw_action or decision.action
    return Decision(action=action, args=args, confidence=1.0, raw_action=action).model_dump(
        mode="json"
    )


def ask_day(decision: Decision, today: dt.date, lang: str) -> tuple[list[Block], Options]:
    """Which day a count is for: Today and Yesterday, each the same decision with its
    business_date filled."""
    options: Options = {}
    for key, day in (("today", today), ("yesterday", today - dt.timedelta(days=1))):
        args = {**decision.args, "business_date": day.isoformat()}
        options[t(f"sales.which_day.{key}", lang)] = _asked(decision, args)
    blocks: list[Block] = [
        TextBlock(text=t("sales.which_day", lang)),
        QuickRepliesBlock(options=list(options)),
    ]
    return blocks, options


def unknown_item(args: dict[str, Any]) -> int | None:
    """The index of the first count with no item (report_sales items, or correct_sales' one
    count as index 0), if any."""
    counts = args.get("items") if "items" in args else [args] if "quantity" in args else []
    return next((i for i, c in enumerate(counts or []) if c.get("item_id") is None), None)


def ask_item(
    decision: Decision, index: int, names: dict[str, str], lang: str
) -> tuple[list[Block], Options]:
    """Which item count `index` is: one button per candidate (names maps item id to name),
    each the same decision with that item filled in."""
    options: Options = {}
    nested = "items" in decision.args
    count = decision.args["items"][index] if nested else decision.args
    for item_id in count.get("candidates") or []:
        if item_id not in names:
            continue
        args = copy.deepcopy(decision.args)
        target = args["items"][index] if nested else args
        target["item_id"] = item_id
        target.pop("candidates", None)
        target.pop("words", None)
        options[names[item_id]] = _asked(decision, args)
    blocks: list[Block] = [
        TextBlock(text=t("sales.which_item", lang, words=count.get("words", ""))),
        QuickRepliesBlock(options=list(options)),
    ]
    return blocks, options
