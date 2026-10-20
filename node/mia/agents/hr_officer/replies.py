"""Reply blocks for the hr officer: each tool result worded from i18n keys (minutes as "7h 30m",
one line per pay kind, dates as ISO, money through format_money), the payslip, and the
conversation replies. Code words every reply; no model writes one."""

import datetime as dt
from typing import Any

from pydantic import Field

from mia.agents.decider import Decision
from mia.agents.hr_officer.actions import WHICH
from mia.agents.hr_officer.tools import (
    BalanceOutput,
    CertificateOutput,
    ContributionsOutput,
    HolidayOutput,
    HoursOutput,
    LeavePreview,
    NextPaydayOutput,
    PayslipOutput,
    RequestLeaveInput,
    ThirteenthOutput,
)
from mia.agents.parsing import DAY_NAMES, EN_WEEKDAYS
from mia.chat.blocks import ApprovalCardBlock, Block, CardField, QuickRepliesBlock, TextBlock
from mia.core.models import Payslip
from mia.core.money import format_money
from mia.i18n import t

CAPABILITIES = "hr.capabilities"
CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
}
KINDS = ("sss", "philhealth", "pagibig")
LEAVE_REFUSALS = ("no_contract", "in_the_past", "no_working_days", "overlaps")
# The day buttons a leave without dates offers (a QuickRepliesBlock holds six).
ASKED_DAYS = 6
Options = dict[str, dict[str, Any]]  # button label -> the decision a tap runs


class Buttons(QuickRepliesBlock):
    """Quick replies whose decisions are stored with the message row (block dumps keep them;
    the chat API and the channels show the options only). Sensitive when a decision carries a
    leave kind or a pay question, so the row's event hides the blocks."""

    decisions: Options = Field(default_factory=dict)
    sensitive: bool = False


def with_decisions(blocks: list[Block], options: Options, *, sensitive: bool) -> list[Block]:
    """The blocks with each quick replies block carrying the decisions its taps run."""
    return [
        Buttons(options=b.options, decisions=options, sensitive=sensitive)
        if isinstance(b, QuickRepliesBlock)
        else b
        for b in blocks
    ]


def button_decisions(stored: list[dict[str, Any]]) -> Options:
    """The decisions behind the buttons of a stored message's blocks (label -> decision)."""
    found: Options = {}
    for block in stored:
        if block.get("type") == "quick_replies":
            found.update(block.get("decisions") or {})
    return found


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action: a greeting, thanks or goodbye, else (an
    injection included) what the agent can do."""
    return [TextBlock(text=t(CONVERSATION_KEYS.get(kind, CAPABILITIES), lang))]


def duration(minutes: int) -> str:
    """Minutes as "7h 30m", "8h" on the hour, "0h 45m" under one."""
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if m else f"{h}h"


def _span(start: dt.date, end: dt.date, lang: str) -> str:
    return t("hr.span", lang, start=start.isoformat(), end=end.isoformat())


def _text(key: str, lang: str, **values: Any) -> list[Block]:
    return [TextBlock(text=t(key, lang, **values))]


def _contributions(out: ContributionsOutput, which: str, lang: str) -> list[Block]:
    """One contribution when one was asked, else all three; one not on the payslip reads as
    none on record (never as zero money)."""
    none = t("hr.contribution.none", lang)
    amounts = {k: getattr(out, k) for k in KINDS}
    paid = {
        k: none if a is None else format_money(a, out.currency, lang) for k, a in amounts.items()
    }
    cutoff = out.cutoff_end.isoformat()
    if which in KINDS:
        return _text("hr.contribution", lang, cutoff=cutoff, name=WHICH[which], amount=paid[which])
    return _text("hr.contributions", lang, cutoff=cutoff, **paid)


def tool_reply(tool: str, out: dict[str, Any], args: dict[str, Any], lang: str) -> list[Block]:
    """The reply to one successful tool result (tool is the name without the agent prefix)."""
    if tool == "hours":
        h = HoursOutput.model_validate(out)
        kinds = {k: duration(getattr(h, k)) for k in ("regular", "overtime", "night", "rest_day")}
        period = _span(h.start, h.end, lang)
        return _text(
            "hr.hours", lang, period=period, holiday=duration(h.holiday), days=h.days, **kinds
        )
    if tool == "next_payday":
        p = NextPaydayOutput.model_validate(out)
        start, end = p.cutoff_start.isoformat(), p.cutoff_end.isoformat()
        return _text("hr.payday", lang, date=p.pay_date.isoformat(), start=start, end=end)
    if tool == "thirteenth_month":
        m = ThirteenthOutput.model_validate(out)
        amount = format_money(m.estimate, m.currency, lang)
        return _text("hr.thirteenth", lang, amount=amount, month=t(f"hr.month.{m.paid_in}", lang))
    if tool == "last_contributions":
        c = ContributionsOutput.model_validate(out)
        return _contributions(c, str(args.get("which", "all")), lang)
    if tool == "balance":
        b = BalanceOutput.model_validate(out)
        return _text("hr.balance", lang, left=b.left, total=b.total, used=b.used)
    if tool == "holiday":
        d = HolidayOutput.model_validate(out)
        day = str(args.get("day"))
        return _text(f"hr.holiday.{d.kind}", lang, date=day, name=d.name, rate=d.rate_percent)
    if tool == "resend_payslip":
        slip = PayslipOutput.model_validate(out)
        start, end = slip.cutoff_start.isoformat(), slip.cutoff_end.isoformat()
        return _text("hr.payslip_sent", lang, start=start, end=end)  # amounts: the notification
    if tool == "certificate_text":
        return [TextBlock(text=CertificateOutput.model_validate(out).text)]
    return _text("reply.not_built", lang)  # request_leave runs on approve, set_contract in v2


def payslip_blocks(slip: Payslip, lang: str) -> list[Block]:
    """The payslip in lang: the totals line (hr.payslip_resent), one line per pay kind with
    its time and amount, one per deduction. Issued and resent payslips both read this way."""

    def money(amount: int) -> str:
        return format_money(amount, slip.currency, lang)

    deducted = sum(int(d["amount"]) for d in slip.deductions)
    head = t(
        "hr.payslip_resent",
        lang,
        start=slip.cutoff_start.isoformat(),
        end=slip.cutoff_end.isoformat(),
        gross=money(slip.gross),
        deductions=money(deducted),
        net=money(slip.net),
    )
    lines = [
        t(
            "hr.payslip.line",
            lang,
            kind=t(f"hr.pay.{line['kind']}", lang),
            time=duration(int(line["minutes"])),
            amount=money(int(line["amount"])),
        )
        for line in slip.lines
    ]
    lines += [
        t("hr.payslip.deduction", lang, name=WHICH[d["kind"]], amount=money(int(d["amount"])))
        for d in slip.deductions
    ]
    return [TextBlock(text=text) for text in (head, *lines)]


def leave_refused(reason: str, args: dict[str, Any], lang: str) -> list[Block] | None:
    """The reason a leave was refused before any approval, in words; None for another refusal."""
    if reason not in LEAVE_REFUSALS:
        return None
    return _text(f"hr.leave_refused.{reason}", lang, start=args["start"], end=args["end"])


def leave_summary(name: str, leave: RequestLeaveInput, preview: LeavePreview, lang: str) -> str:
    """The leave in words for the approver: who, the dates, the working days, the balance after
    (never the kind: a sick leave stays off the log)."""
    start, end = leave.start.isoformat(), leave.end.isoformat()
    days, left = preview.days, preview.left_after
    return t("hr.leave.summary", lang, name=name, start=start, end=end, days=days, left=left)


def leave_waiting(
    summary: str,
    leave: RequestLeaveInput,
    preview: LeavePreview | None,
    approval_id: str,
    lang: str,
) -> list[Block]:
    """The requester's reply: the leave waits for head staff, with its approval card (the
    dates, the working days, how many are paid and the balance after)."""
    start, end = leave.start.isoformat(), leave.end.isoformat()
    card = ApprovalCardBlock(
        approval_id=approval_id, title=t("hr.leave.approval_title", lang), summary=summary
    )
    card.fields = [
        CardField(label=t("hr.field.dates", lang), value=_span(leave.start, leave.end, lang))
    ]
    if preview is not None:
        card.fields += [
            CardField(label=t("hr.field.working_days", lang), value=str(preview.days)),
            CardField(label=t("hr.field.paid_days", lang), value=str(preview.paid)),
            CardField(label=t("hr.field.leave_left", lang), value=str(preview.left_after)),
        ]
    card.fields.append(CardField(label=t("field.status", lang), value=card.status))
    return [TextBlock(text=t("hr.leave.waiting", lang, start=start, end=end)), card]


def ask_leave_days(
    decision: Decision, days: list[dt.date], lang: str
) -> tuple[list[Block], Options]:
    """Which day the leave is for: one button per offered day (the weekday and the date), each
    filing a one-day leave of the kind asked; longer leave is typed."""
    names = DAY_NAMES.get(lang, EN_WEEKDAYS)
    kind = decision.args.get("kind") or "vacation"
    options: Options = {}
    for d in days:
        day = d.isoformat()
        label = t("hr.leave.day", lang, weekday=names[d.weekday()].capitalize(), date=day)
        args = {"kind": kind, "start": day, "end": day}
        options[label] = Decision(
            action="file_leave", args=args, confidence=1.0, raw_action="file_leave"
        ).model_dump(mode="json")
    blocks: list[Block] = [
        TextBlock(text=t("hr.leave.which_days", lang)),
        QuickRepliesBlock(options=list(options)),
    ]
    return blocks, options
