"""Reply blocks for the sales supervisor: each tool result worded from i18n keys (money through
format_money, counts through format_int), the conversation replies, and the question this agent
asks (which item). Code words the numbers; no model writes a reply."""

import copy
import datetime as dt
from typing import Any

from mia.agents.decider import Decision
from mia.agents.parsing import DAY_NAMES, EN_WEEKDAYS
from mia.agents.sales_supervisor import calc
from mia.agents.sales_supervisor.actions import WEEKDAYS
from mia.agents.sales_supervisor.report import Result
from mia.agents.sales_supervisor.tools import (
    BranchToday,
    CorrectCountOutput,
    ItemCodesOutput,
    PeriodReportOutput,
    ReceiptOut,
    ReceiptsOutput,
    RecordCountsOutput,
    RecordReceiptOutput,
    SetTargetOutput,
    TodayOutput,
)
from mia.agents.shift_supervisor.rules import fmt_date
from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.core.models import TENDERS
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

TOP = 10  # a breakdown's lines shown before "and N more"

# (label, the stored decision a tap runs)
Options = dict[str, dict[str, Any]]


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action (unknown kinds get the capabilities); a
    greeting is followed by what the agent does."""
    blocks: list[Block] = [
        TextBlock(text=t(CONVERSATION_KEYS.get(kind, "sales.capabilities"), lang))
    ]
    if kind == "greeting":
        blocks.append(TextBlock(text=t("sales.capabilities", lang)))
    return blocks


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


def _branch_today(day: BranchToday, lang: str) -> Block:
    """One branch's line of the today reply; it names the branch."""
    if not day.items:
        return TextBlock(text=t("sales.today.empty", lang, branch=day.branch))
    lines = _lines([(i.quantity, i.item) for i in day.items], lang)
    total = format_money(day.total, day.currency, lang)
    target = _target(day.total, day.target_share, day.currency, lang)
    text = t("sales.today", lang, branch=day.branch, lines=lines, total=total, target=target)
    return TextBlock(text=text)


def _when(day: dt.date, at: dt.datetime, lang: str) -> str:
    """The business date and the local time of `at`: "Fri 23 Oct, 12:05", "23.10. klo 12.05"."""
    if lang == "fi":
        return f"{fmt_date(day.isoformat(), lang)} klo {at:%H.%M}"
    return f"{fmt_date(day.isoformat(), lang)}, {at:%H:%M}"


def _text(key: str, lang: str, **values: Any) -> list[Block]:
    return [TextBlock(text=t(key, lang, **values))]


def tool_reply(tool: str, out: dict[str, Any], args: dict[str, Any], lang: str) -> list[Block]:
    """The reply to one successful tool result (tool is the name without the agent prefix;
    args is the tool input, for the period's dates)."""
    if tool == "record_receipt":
        return receipt_recorded(RecordReceiptOutput.model_validate(out), lang)
    if tool == "receipts":
        return receipts_read(ReceiptsOutput.model_validate(out), str(args.get("which")), lang)
    if tool == "record_counts":
        rec = RecordCountsOutput.model_validate(out)  # the owner's ask: no running total
        lines = _lines([(c.quantity, c.item) for c in rec.recorded], lang)
        # ponytail: a count has one tender (two in a message ask first); the first row's speaks
        tender = rec.recorded[0].tender if rec.recorded else "cash"
        if tender != "cash":
            lines += f" ({t(f'bk.tender.{tender}', lang) if tender in TENDERS else tender})"
        when = _when(rec.business_date, rec.reported_at, lang)
        return _text("sales.recorded", lang, lines=lines, when=when)
    if tool == "correct_count":
        cor = CorrectCountOutput.model_validate(out)
        quantity, previous = (
            format_int(n, lang) for n in (cor.corrected.quantity, cor.previous_quantity)
        )
        return _text(
            "sales.corrected", lang, quantity=quantity, item=cor.corrected.item, previous=previous
        )
    if tool == "today":
        return [_branch_today(day, lang) for day in TodayOutput.model_validate(out).branches]
    if tool == "period_report":
        rep = PeriodReportOutput.model_validate(out)
        start, end = str(args["start"]), str(args["end"])
        if rep.best_day is None:
            return _text("sales.period.empty", lang, start=start, end=end)
        if args.get("branch_id") == "all" and args.get("item_id"):
            ranked = sorted(rep.rows, key=lambda r: -r.quantity)
            lines = ", ".join(f"{r.branch} {format_int(r.quantity, lang)}" for r in ranked)
            return _text("sales.period.by_branch", lang, item=ranked[0].item, lines=lines)
        total = format_money(rep.total, rep.currency, lang)
        best = rep.best_day.isoformat()
        head = t("sales.period", lang, start=start, end=end, total=total, best_day=best)
        shown = [
            t(
                "sales.period.line",
                lang,
                name=b.name,
                quantity=format_int(b.quantity, lang),
                amount=format_money(b.amount, rep.currency, lang),
            )
            for b in rep.breakdown[:TOP]
        ]
        more = len(rep.breakdown) - TOP
        if more > 0:
            shown.append(t("sales.period.more", lang, n=format_int(more, lang)))
        return [TextBlock(text="\n".join([head, *shown]))]
    if tool == "item_codes":
        menu = ItemCodesOutput.model_validate(out)
        rows = [
            t(
                "sales.codes.line",
                lang,
                item=i.item,
                codes=", ".join(i.codes),
                price=format_money(i.price, menu.currency, lang),
            )
            for i in menu.items
        ]
        heading = t("sales.codes", lang, branch=menu.branch)
        return [TextBlock(text="\n".join([heading, *rows]))]
    if tool == "set_target":
        st = SetTargetOutput.model_validate(out)
        when = st.starts_on.isoformat() if st.period == "day" else st.starts_on.strftime("%Y-%m")
        amount = format_money(st.amount, st.currency, lang)
        return _text("sales.target_set", lang, amount=amount, when=when)
    return _text("sales.note_thanks", lang)  # record_note


def report_text(result: Result, lang: str) -> list[Block]:
    """A report as one text block: the head (measure, dates, grouping, total), the top TOP
    lines then "and N more", each line and the total with the percent change when the form
    compared and the compared value is not zero (calc.compare). Every figure is the Result's."""

    def value(n: int) -> str:
        if result.head_measure == "amount":
            return format_money(n, result.currency, lang)
        return format_int(n, lang)

    def name(raw: str) -> str:
        if result.group_by == "weekday":
            return DAY_NAMES.get(lang, EN_WEEKDAYS)[WEEKDAYS.index(raw)].capitalize()
        return _tender(raw, lang) if result.group_by == "tender" else raw

    def line(key: str, before: int | None, **values: str) -> str | None:
        percent = calc.compare(int(values.pop("now")), before)
        if before is None or percent is None:
            return None
        return t(key, lang, percent=format_int(percent, lang), before=value(before), **values)

    by = ""
    if result.group_by != "none":
        by = t("sales.report.by", lang, group=t(f"sales.report.group.{result.group_by}", lang))
    head = t(
        "sales.report.head",
        lang,
        measure=t(f"sales.report.measure.{result.head_measure}", lang),
        start=result.start.isoformat(),
        end=result.end.isoformat(),
        by=by,
        total=value(result.total),
    )
    shown = []
    for x in result.lines[:TOP]:
        n = x.quantity if result.head_measure == "pieces" else x.amount
        worded = {"name": name(x.name), "value": value(n)}
        shown.append(
            line("sales.report.row_vs", x.before, now=str(n), **worded)
            or t("sales.report.row", lang, **worded)
        )
    more = len(result.lines) - TOP
    if more > 0:
        shown.append(t("sales.period.more", lang, n=format_int(more, lang)))
    if result.total_before is not None:
        total_vs = line(
            "sales.report.total_vs",
            result.total_before,
            now=str(result.total),
            total=value(result.total),
        )
        if total_vs:
            shown.append(total_vs)
    return [TextBlock(text="\n".join([head, *shown]))]


def _asked(decision: Decision, args: dict[str, Any]) -> dict[str, Any]:
    """The decision a button runs: the action that was meant, with the completed args."""
    action = decision.raw_action or decision.action
    return Decision(action=action, args=args, confidence=1.0, raw_action=action).model_dump(
        mode="json"
    )


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


def receipt_recorded(out: RecordReceiptOutput, lang: str) -> list[Block]:
    """The recorded receipt: its number, lines, total and tender."""
    return _text(
        "sales.receipt.recorded",
        lang,
        no=out.receipt_no or "",
        lines=_lines([(x.quantity, x.item) for x in out.lines], lang),
        total=format_money(out.total, out.currency, lang),
        tender=t(f"bk.tender.{out.tender}", lang),
    )


def ask_tender(decision: Decision, lang: str) -> tuple[list[Block], Options]:
    """How a receipt was paid: one button per tender (TENDERS order), each the decision with
    that tender."""
    options = {
        t(f"bk.tender.{x}", lang): _asked(decision, {**decision.args, "tender": x}) for x in TENDERS
    }
    blocks: list[Block] = [
        TextBlock(text=t("sales.receipt.ask_tender", lang)),
        QuickRepliesBlock(options=list(options)),
    ]
    return blocks, options


def ask_total(
    decision: Decision, out: RecordReceiptOutput | RecordCountsOutput, lang: str
) -> tuple[list[Block], Options]:
    """The typed total of a receipt or a count differs from the prices: one button records at
    the computed total (the decision without the typed total), plus Something else."""
    computed = format_money(out.total, out.currency, lang)
    typed = format_money(out.typed_total or 0, out.currency, lang)
    use = t("sales.receipt.use_computed", lang, total=computed)
    other = t("clarify.something_else", lang)
    key = "typed_total" if isinstance(out, RecordReceiptOutput) else "total"
    options: Options = {
        use: _asked(decision, {**decision.args, key: None}),
        other: Decision(action="clarify", confidence=1.0).model_dump(mode="json"),
    }
    blocks: list[Block] = [
        TextBlock(text=t("sales.receipt.total_differs", lang, computed=computed, typed=typed)),
        QuickRepliesBlock(options=list(options)),
    ]
    return blocks, options


def ask_confirm(
    decision: Decision, out: RecordReceiptOutput, lang: str
) -> tuple[list[Block], Options]:
    """A count rung as one receipt on a receipts kiosk: the computed receipt asked on a button
    that records it (the decision without confirm), plus Something else (as ask_total)."""
    total = format_money(out.total, out.currency, lang)
    lines = _lines([(x.quantity, x.item) for x in out.lines], lang)
    tender = t(f"bk.tender.{out.tender}", lang)
    use = t("sales.receipt.ring_up", lang)
    other = t("clarify.something_else", lang)
    options: Options = {
        use: _asked(decision, {**decision.args, "confirm": False}),
        other: Decision(action="clarify", confidence=1.0).model_dump(mode="json"),
    }
    blocks: list[Block] = [
        TextBlock(
            text=t("sales.receipt.confirm_one", lang, lines=lines, total=total, tender=tender)
        ),
        QuickRepliesBlock(options=list(options)),
    ]
    return blocks, options


def void_asked(out: ReceiptOut, lang: str) -> list[Block]:
    """The void was sent to head staff: the receipt's number, lines and total, so a wrong
    number is seen."""
    return _text(
        "sales.void.asked",
        lang,
        no=out.receipt_no,
        lines=_lines([(x.quantity, x.item) for x in out.lines], lang),
        total=format_money(out.total, out.currency, lang),
    )


def refund_asked(
    no: str, amount: int, lines: list[tuple[int, str]], currency: str, lang: str
) -> list[Block]:
    """The refund was sent to the owner: the computed amount, the sale's number and the lines
    asked for, so a refund wider than meant is seen."""
    money = format_money(amount, currency, lang)
    return _text("sales.refund.asked", lang, amount=money, no=no, lines=_lines(lines, lang))


def _tender(tender: str, lang: str) -> str:
    return t(f"bk.tender.{tender}", lang) if tender in TENDERS else tender  # "split" as is


def receipts_read(out: ReceiptsOutput, which: str, lang: str) -> list[Block]:
    """Today's receipts (how many sales were paid, the net total and each tender in TENDERS order), or
    the last one with its time, lines, total and tender (voided or refund said); none yet, or
    none paid for today, says so."""
    paid = [r for r in out.receipts if r.status == "paid"]
    if not out.receipts or (which != "last" and not paid):
        return _text("sales.receipts.today_empty", lang, branch=out.branch)
    if which == "last":
        r = out.receipts[-1]
        if r.status == "voided":
            key = "sales.receipts.last_voided"
        elif r.kind == "refund":
            key = "sales.receipts.last_refund"
        else:
            key = "sales.receipts.last"
        return _text(
            key,
            lang,
            no=r.receipt_no,
            time=r.time,
            lines=_lines([(abs(x.quantity), x.item) for x in r.lines], lang),
            total=format_money(abs(r.total), r.currency, lang),
            tender=_tender(r.tender, lang),
        )
    tenders = ", ".join(
        t(
            "sales.receipts.tender",
            lang,
            tender=_tender(x, lang),
            amount=format_money(out.by_tender[x], out.currency, lang),
        )
        for x in TENDERS
        if out.by_tender.get(x)
    )
    return _text(
        "sales.receipts.today",
        lang,
        branch=out.branch,
        count=format_int(sum(r.kind != "refund" for r in paid), lang),  # sales; the total is net
        total=format_money(out.total, out.currency, lang),
        tenders=tenders,
    )
