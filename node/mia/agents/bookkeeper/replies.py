"""Reply blocks for the bookkeeper: each tool result worded from bk.* keys (money through
format_money in minor units, dates as ISO, providers, categories, banks and tenders as bk.*
labels), the large expense card and the conversation replies. Code words every reply; no model
writes one, and every number in a reply is one a tool computed."""

from collections.abc import Mapping
from typing import Any

from mia.agents.bookkeeper import calc, words
from mia.agents.bookkeeper.tools import (
    BalancesOut,
    CashCountOut,
    DepositOut,
    ExpenseInput,
    ExpenseOut,
    JournalOut,
    PettyOut,
    ProfitOutput,
    TaxOutput,
)
from mia.chat.blocks import ApprovalCardBlock, Block, CardField, TextBlock
from mia.core.money import format_money
from mia.i18n import t
from mia.i18n.strings import STRINGS

CAPABILITIES = "bk.capabilities"
CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
}
Names = Mapping[str, str]  # branch ids -> names
Options = dict[str, dict[str, Any]]  # button label -> the decision a tap runs


def money(amount: int, currency: str, lang: str) -> str:
    """Minor units worded in the language (mia.core.money)."""
    return format_money(amount, currency, lang)


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action: a greeting, thanks or goodbye, else (an
    injection included) what the agent can do."""
    return [TextBlock(text=t(CONVERSATION_KEYS.get(kind, CAPABILITIES), lang))]


def refusal_key(message: str) -> str:
    """The bk.refused.<reason> key of a tool refusal's reason, else bk.no_record."""
    key = f"bk.refused.{message}"
    return key if key in STRINGS["en"] else "bk.no_record"


def _side(gap: int, flagged: bool) -> str:
    return "within" if not flagged else "short" if gap < 0 else "over"


def count_text(out: CashCountOut, lang: str) -> str:
    """The count against the day's cash sales: within the threshold, or short or over (the
    owner is told by the tool). On a receipts day (out.clerk set) the clerk's drawer with its
    float and cash receipts, and the drawers still open."""
    side = _side(out.difference, out.flagged)
    gap = money(abs(out.difference), out.currency, lang)
    params = {
        "counted": money(out.counted, out.currency, lang),
        "expected": money(out.expected, out.currency, lang),
        "difference": gap,
        "short": gap,
        "over": gap,
    }
    if out.clerk is None:
        return t(f"bk.count.{side}", lang, **params)
    text = t(
        f"bk.count.drawer.{side}",
        lang,
        clerk=out.clerk,
        float=money(out.opening_float or 0, out.currency, lang),
        cash=money(out.cash or 0, out.currency, lang),
        **params,
    )
    if out.still_open:
        text += " " + t("bk.count.still_open", lang, names=", ".join(out.still_open))
    return text


def match_text(m: calc.Match, provider: str, lang: str, currency: str) -> str:
    """A settlement (GCash, Maya: the fee) or payout (Grab, Foodpanda: the commission) against
    the period's sales by that tender less the cut, within the threshold or short or over."""
    kind = "settlement" if provider in words.SETTLERS else "payout"
    gap = money(abs(m.gap), currency, lang)
    return t(
        f"bk.{kind}.{_side(m.gap, m.flagged)}",
        lang,
        provider=t(f"bk.provider.{provider}", lang),
        amount=money(m.expected + m.gap, currency, lang),
        expected=money(m.expected, currency, lang),
        sales=money(m.expected + m.cut, currency, lang),
        cut=money(m.cut, currency, lang),
        gap=gap,
    )


def expense_text(out: ExpenseOut, lang: str) -> str:
    """The expense, its receipt number when typed, and its category's total for the month."""
    key = "bk.expense.recorded_receipt" if out.receipt_no else "bk.expense.recorded"
    return t(
        key,
        lang,
        amount=money(out.amount, out.currency, lang),
        category=t(f"bk.category.{out.category}", lang),
        receipt=out.receipt_no or "",
        month_total=money(out.month_total, out.currency, lang),
    )


def expense_summary(args: ExpenseInput, currency: str, lang: str) -> str:
    """The large expense approval's summary: amount and category."""
    return t(
        "bk.expense.summary",
        lang,
        amount=money(args.amount, currency, lang),
        category=t(f"bk.category.{args.category}", lang),
    )


def expense_waiting(
    approval_id: str, summary: str, args: ExpenseInput, currency: str, lang: str
) -> list[Block]:
    """The requester's reply: the large expense waits for the owner, with its card (amount,
    category, receipt, business date, source, status)."""
    card = ApprovalCardBlock(
        approval_id=approval_id, title=t("bk.expense.approval_title", lang), summary=summary
    )
    facts = {
        "amount": money(args.amount, currency, lang),
        "category": t(f"bk.category.{args.category}", lang),
        "receipt": args.receipt_no or "",
        "date": args.business_date.isoformat() if args.business_date else "",
        "source": t(f"bk.source.{args.source}", lang),
    }
    card.fields = [
        CardField(label=t(f"bk.field.{k}", lang), value=v) for k, v in facts.items() if v
    ]
    card.fields.append(CardField(label=t("field.status", lang), value=card.status))
    return [TextBlock(text=t("bk.expense.waiting", lang, summary=summary)), card]


def petty_text(out: PettyOut, floor: int, category: str, lang: str) -> str:
    """The spend or refill, the petty balance after it, and the refill reminder under the
    floor."""
    amount = money(out.amount, out.currency, lang)
    head = (
        t("bk.petty.spent", lang, amount=amount, category=t(f"bk.category.{category}", lang))
        if out.kind == "spend"
        else t("bk.petty.refilled", lang, amount=amount)
    )
    lines = [head, t("bk.petty.balance", lang, balance=money(out.balance, out.currency, lang))]
    if out.below_floor:
        lines.append(t("bk.petty.refill", lang, floor=money(floor, out.currency, lang)))
    return "\n".join(lines)


def deposit_text(out: DepositOut, lang: str) -> str:
    """The deposit, its bank and the cash not yet deposited after it."""
    return t(
        "bk.deposit.done",
        lang,
        amount=money(out.amount, out.currency, lang),
        bank=t(f"bk.bank.{out.bank}", lang),
        undeposited=money(out.undeposited, out.currency, lang),
    )


def balances_text(out: BalancesOut, limit: int, lang: str) -> str:
    """The petty balance and the undeposited cash, and the days in a row over the limit."""
    lines = [
        t(
            "bk.balances",
            lang,
            petty=money(out.petty, out.currency, lang),
            undeposited=money(out.undeposited, out.currency, lang),
        )
    ]
    if out.days_over:
        limit_text = money(limit, out.currency, lang)
        lines.append(t("bk.balances.over", lang, limit=limit_text, days=out.days_over))
    return "\n".join(lines)


def journal_text(out: JournalOut, lang: str) -> str:
    """The month's sales book: the total, then one line per business date by tender."""
    month = out.month.isoformat()[:7]
    if not out.days:
        return t("bk.journal.none", lang, month=month)
    lines = [t("bk.journal.head", lang, month=month, total=money(out.total, out.currency, lang))]
    for day in sorted(out.days):
        tenders = ", ".join(
            t(
                "bk.journal.tender",
                lang,
                tender=t(f"bk.tender.{k}", lang),
                amount=money(v, out.currency, lang),
            )
            for k, v in out.days[day].items()
        )
        lines.append(t("bk.journal.day", lang, date=day.isoformat(), tenders=tenders))
    return "\n".join(lines)


def tax_text(out: TaxOutput, names: Names, lang: str) -> str:
    """One line per branch: VAT (output less input, an excess carried over) or percentage
    tax, with the filing deadline."""
    lines = []
    for b in out.branches:

        def m(amount: int, currency: str = b.currency) -> str:
            return money(amount, currency, lang)

        common = {
            "branch": names.get(b.branch_id, ""),
            "start": b.start.isoformat(),
            "end": b.end.isoformat(),
            "gross": m(b.gross),
            "deadline": b.deadline.isoformat(),
        }
        if b.regime != "vat":
            lines.append(t("bk.tax.percentage", lang, rate=b.rate, due=m(b.due), **common))
            continue
        key = "bk.tax.vat" if b.due >= 0 else "bk.tax.vat_excess"
        lines.append(
            t(
                key,
                lang,
                output=m(b.output_tax),
                input=m(b.input_tax),
                due=m(b.due),
                excess=m(-b.due),
                **common,
            )
        )
    return "\n".join(lines)


def profit_text(out: ProfitOutput, names: Names, lang: str) -> str:
    """The month's profit per branch: the lines subtracted, the profit, and cost of goods and
    waste at cost shown (not subtracted)."""
    lines = [t("bk.profit.head", lang, month=out.month.isoformat()[:7])]
    for b in out.branches:

        def m(amount: int, currency: str = b.currency) -> str:
            return money(amount, currency, lang)

        lines.append(
            t(
                "bk.profit.branch",
                lang,
                branch=names.get(b.branch_id, ""),
                sales=m(b.sales),
                fees=m(b.fees),
                expenses=m(b.expenses),
                supplier=m(b.supplier),
                payroll=m(b.payroll),
                profit=m(b.profit),
            )
        )
        if b.cost_of_goods is None:
            lines.append(t("bk.profit.goods_unknown", lang, waste=m(b.waste)))
        else:
            lines.append(t("bk.profit.goods", lang, goods=m(b.cost_of_goods), waste=m(b.waste)))
    return "\n".join(lines)
