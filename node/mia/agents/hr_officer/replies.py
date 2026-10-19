"""Reply blocks for the hr officer: each tool result worded from i18n keys (minutes as "7h 30m",
one line per pay kind,
dates as ISO, money through format_money), and the conversation replies. Code words every
reply; no model writes one."""

import datetime as dt
from typing import Any

from mia.agents.hr_officer.actions import WHICH
from mia.agents.hr_officer.tools import (
    ContributionsOutput,
    HoursOutput,
    NextPaydayOutput,
    ThirteenthOutput,
)
from mia.chat.blocks import Block, TextBlock
from mia.core.money import format_money
from mia.i18n import t

CAPABILITIES = "hr.capabilities"
CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
}
KINDS = ("sss", "philhealth", "pagibig")


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
    return _text("reply.not_built", lang)  # ponytail: leave, holiday, payslip, certificate: Task 5
