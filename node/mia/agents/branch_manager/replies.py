"""Reply blocks for the branch manager: each tool result worded from bm.* keys (money through
format_money, dates as ISO, theme ids as sales.theme.* labels), the experiment and price cards,
and the conversation replies. Code words every reply; no model writes one. Tips and quotes come
only from branch_manager_tips rows (the tool's output); a note's text never reaches a reply."""

from collections.abc import Mapping
from typing import Any

from mia.agents.branch_manager.models import Experiment
from mia.agents.branch_manager.tools import (
    WORDED,
    CoachingOutput,
    HowToSellOutput,
    ItemOut,
    MonthlyOutput,
    PersonOut,
    WeeklyOutput,
)
from mia.agents.decider import Decision
from mia.agents.sales_supervisor.actions import THEMES
from mia.chat.blocks import ApprovalCardBlock, Block, CardField, TextBlock
from mia.core.money import format_money
from mia.i18n import t
from mia.i18n.strings import STRINGS

CAPABILITIES = "bm.capabilities"
CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
}
MONEY_KEYS = ("price", "sum")  # rationale values in minor units
Names = Mapping[str, str]  # item, person and branch ids -> names
Options = dict[str, dict[str, Any]]  # button label -> the decision a tap runs


def keep_or_revert(row: Experiment, lang: str) -> Options:
    """The experiment's Keep (its tested price) and Revert (its old price) buttons, each with
    the decide_experiment_result decision a tap runs."""
    options: Options = {}
    for keep, key, price in ((True, "keep", row.to_price), (False, "revert", row.from_price)):
        label = t(f"bm.experiment.{key}", lang, price=format_money(price, row.currency, lang))
        args = {"experiment_id": row.id, "keep": keep}
        decision = Decision(action="decide_experiment_result", args=args, confidence=1.0)
        options[label] = decision.model_dump(mode="json")
    return options


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action: a greeting, thanks or goodbye, else (an
    injection included) what the agent can do."""
    return [TextBlock(text=t(CONVERSATION_KEYS.get(kind, CAPABILITIES), lang))]


def _text(key: str, lang: str, **values: Any) -> list[Block]:
    return [TextBlock(text=t(key, lang, **values))]


def refusal_key(message: str) -> str:
    """The bm.refused.<reason> key of a tool refusal's reason, else bm.no_record."""
    if message == "range":  # sales.SalesRangeError: a period too long to read
        return "sales.refused.range"
    key = f"bm.refused.{message}"
    return key if key in STRINGS["en"] else "bm.no_record"


def coaching_text(out: CoachingOutput, lang: str, names: Names, currency: str = "PHP") -> str:
    """The period, one line per person (units, amount and the 30 days before; improved ones
    say so), most units first, and the pairing of two items by name."""
    start, end = out.start.isoformat(), out.end.isoformat()
    lines = [t("bm.coaching.head", lang, start=start, end=end, **WORDED)]
    for r in out.rows:
        key = "bm.coaching.row_improved" if r.improved else "bm.coaching.row"
        amount = format_money(r.amount, currency, lang)
        lines.append(t(key, lang, name=r.name, units=r.units, amount=amount, before=r.before_units))
    if not out.rows:
        lines.append(t("bm.coaching.none", lang, **WORDED))
    if out.pairing is not None:
        first, second = (names.get(i, "") for i in out.pairing)
        lines.append(t("bm.coaching.pairing", lang, first=first, second=second))
    return "\n".join(lines)


def how_to_sell(out: HowToSellOutput, lang: str) -> list[Block]:
    """The branch's own reasons first (theme labels, never note text), then the tips (row text
    and source)."""
    blocks: list[Block] = []
    themes = [t(f"sales.theme.{th}", lang) for th in out.themes if th in THEMES]
    if themes:
        blocks += _text("bm.how_to_sell.themes", lang, themes=", ".join(themes))
    blocks += [
        _text("bm.how_to_sell.tip", lang, text=tip.text, source=tip.source)[0] for tip in out.tips
    ]
    return blocks or _text("bm.how_to_sell.none", lang)


def score_text(
    units: int | None,
    amount: int | None,
    days: int,
    done: bool,
    strategy: str,
    item: str,
    lang: str,
) -> str:
    """So far (running) or the result (done, naming the strategy and the item) in percent
    against the baseline; not enough data without a baseline to compare."""
    if units is None or amount is None:
        return t("bm.experiment.not_enough", lang, **WORDED)
    if done:
        return t(
            "bm.experiment.result",
            lang,
            strategy=strategy,
            item=item,
            units=units,
            amount=amount,
            days=days,
        )
    return t("bm.experiment.so_far", lang, units=units, amount=amount, days=days)


def rationale_text(name_key: str, rationale: Mapping[str, Any], currency: str, lang: str) -> str:
    """The engine's numbers for the strategy in words (bm.rationale.<strategy>); "" without
    them or without a wording."""
    key = name_key.replace("bm.strategy.", "bm.rationale.")
    if not rationale or key not in STRINGS["en"]:
        return ""
    values = {
        k: format_money(int(v), currency, lang) if k in MONEY_KEYS else v
        for k, v in rationale.items()
    }
    return t(key, lang, **WORDED, **values)


def experiment_waiting(
    approval_id: str, summary: str, facts: dict[str, str], lang: str
) -> list[Block]:
    """The requester's reply: the experiment waits for the owner, with its card (strategy,
    item, price move, dates, rationale, guard rails, baseline, status)."""
    card = ApprovalCardBlock(
        approval_id=approval_id, title=t("bm.experiment.approval_title", lang), summary=summary
    )
    card.fields = [
        CardField(label=t(f"bm.field.{k}", lang), value=v) for k, v in facts.items() if v
    ]
    card.fields.append(CardField(label=t("field.status", lang), value=card.status))
    return [TextBlock(text=t("bm.experiment.waiting", lang, summary=summary)), card]


def price_waiting(approval_id: str, summary: str, lang: str) -> list[Block]:
    """The requester's reply: the price change waits for the owner, with its card."""
    card = ApprovalCardBlock(
        approval_id=approval_id, title=t("bm.price.approval_title", lang), summary=summary
    )
    card.fields = [CardField(label=t("field.status", lang), value=card.status)]
    return [TextBlock(text=t("bm.price.waiting", lang, summary=summary)), card]


def short_code(out: ItemOut, lang: str) -> list[Block]:
    """The item and every code it can now be typed as."""
    return _text("bm.short_code.set", lang, item=out.name, codes=", ".join(out.codes))


def person(out: PersonOut, days: int, lang: str) -> list[Block]:
    """add_person: who was added with which role where, then the invite to forward (the wa.me
    link when there is one, the LINK code always) or the linked number by its last four digits;
    set_phone: the linked number only. The full number is never worded."""
    lines = []
    if out.created:
        lines.append(t("bm.person.added", lang, name=out.name, role=out.role, branch=out.branch))
    if out.phone_last4 is not None:
        lines.append(t("bm.person.phone_linked", lang, name=out.name, last4=out.phone_last4))
    elif out.invite_code is not None:
        key = "bm.person.invite" if out.invite_link else "bm.person.invite_code"
        code, link = out.invite_code, out.invite_link
        lines.append(t(key, lang, name=out.name, link=link, code=code, days=days))
    return [TextBlock(text="\n".join(lines))]


def weekly(out: WeeklyOutput, names: Names, currency: str, lang: str) -> list[Block]:
    """The week, then per branch: the amount against the summed target, the best and slowest
    item, the waste and the running experiment's progress."""

    def money(amount: int) -> str:
        return format_money(amount, currency, lang)

    lines = [t("bm.weekly.head", lang, start=out.start.isoformat(), end=out.end.isoformat())]
    for b in out.branches:
        branch = names.get(b.branch_id, "")
        if b.best_item is None:
            lines.append(t("bm.weekly.no_counts", lang, branch=branch))
            continue
        best, worst = names.get(b.best_item, ""), names.get(b.worst_item or "", "")
        key = "bm.weekly.branch" if b.target is not None else "bm.weekly.branch_no_target"
        target = money(b.target) if b.target is not None else ""
        lines.append(
            t(
                key,
                lang,
                branch=branch,
                amount=money(b.amount),
                target=target,
                best=best,
                worst=worst,
            )
        )
        if b.waste:
            waste = ", ".join(f"{names.get(i, '')} {q}" for i, q in sorted(b.waste.items()))
            lines.append(t("bm.weekly.waste", lang, items=waste))
        e = b.experiment
        if e is not None:
            lines.append(score_text(e.units_pct, e.amount_pct, e.days, False, "", "", lang))
    return [TextBlock(text="\n".join(lines))]


def monthly(out: MonthlyOutput, names: Names, lang: str) -> list[Block]:
    """The month's numbers letter: the amount against the target, the best days, the amount
    per person, the experiments decided (strategy, item, status). A template, no prose."""

    def money(amount: int) -> str:
        return format_money(amount, out.currency, lang)

    span = {"start": out.start.isoformat(), "end": out.end.isoformat(), "amount": money(out.amount)}
    if out.target is not None:
        lines = [t("bm.monthly.head", lang, target=money(out.target), **span)]
    else:
        lines = [t("bm.monthly.head_no_target", lang, **span)]
    if out.best_days:
        days = ", ".join(f"{d.isoformat()} {money(a)}" for d, a in out.best_days)
        lines.append(t("bm.monthly.best_days", lang, days=days))
    for pid, amount in sorted(out.clerks.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(t("bm.monthly.clerk", lang, name=names.get(pid, ""), amount=money(amount)))
    for e in out.decided:
        lines.append(
            t(
                "bm.monthly.experiment",
                lang,
                strategy=t(e.strategy, lang),
                item=names.get(e.new_item_id or e.item_id, ""),
                status=t(f"bm.status.{e.status}", lang),
            )
        )
    return [TextBlock(text="\n".join(lines))]
