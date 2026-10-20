"""Reply blocks for the production planner: each tool result worded from pp.* keys (money through
format_money in minor units, quantities in the ingredient's unit, dates as ISO, items, kiosks and
ingredients by name from `names`), the plan, recipe and dispatch cards with the decisions their
buttons run, and the conversation replies. Code words every reply; no model writes one, and every
number in a reply is one a tool computed."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from mia.agents.decider import Decision
from mia.agents.production_planner.tools import (
    BatchOut,
    CapacityOut,
    DispatchOut,
    PlanOut,
    RecipeInput,
    SheetOut,
    YieldOut,
)
from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.core.money import format_money
from mia.i18n import t

CAPABILITIES = "pp.capabilities"
CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
}
Names = Mapping[str, str]  # item, ingredient and branch ids -> names
Options = dict[str, dict[str, Any]]  # button label -> the decision a tap runs


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action: a greeting, thanks or goodbye, else (an
    injection included) what the agent can do."""
    return [TextBlock(text=t(CONVERSATION_KEYS.get(kind, CAPABILITIES), lang))]


def amount(quantity_milli: int) -> str:
    """Thousandths of a unit as a plain number: 2000 is 2, 1500 is 1.5."""
    return str(Decimal(quantity_milli) / 1000)


def _decision(action: str, **args: Any) -> dict[str, Any]:
    return Decision(action=action, args=args, confidence=1.0).model_dump(mode="json")


def plan_text(out: PlanOut, names: Names, lang: str) -> str:
    """The plan: its date, status and free oven minutes, then per item its batches and pieces
    (one batch more when stock runs low) and per kiosk its pieces, forecast, orders and
    leftover (no forecast: not enough data)."""
    status = t(f"pp.plan.status.{out.status}", lang)
    lines = [
        t(
            "pp.plan.head",
            lang,
            date=out.production_date.isoformat(),
            status=status,
            minutes=out.minutes_free,
        )
    ]
    for x in out.lines:
        key = "pp.plan.line_more" if x.more else "pp.plan.line"
        item = names.get(x.item_id, "")
        lines.append(t(key, lang, item=item, batches=x.batches, pieces=x.pieces))
        for k in x.kiosks:
            key = "pp.plan.kiosk" if k.forecast is not None else "pp.plan.kiosk_no_forecast"
            lines.append(
                t(
                    key,
                    lang,
                    kiosk=names.get(k.branch_id, ""),
                    pieces=k.pieces,
                    forecast=k.forecast,
                    orders=k.orders,
                    leftover=k.leftover,
                )
            )
    return "\n".join(lines)


def plan_card(out: PlanOut, names: Names, lang: str) -> tuple[list[Block], Options]:
    """The plan with a Confirm button while it is a draft: the button runs confirm_plan for
    the plan's production date (the turn holds it until production starts that day)."""
    blocks: list[Block] = [TextBlock(text=plan_text(out, names, lang))]
    if out.status != "draft":
        return blocks, {}
    day = out.production_date.isoformat()
    options = {t("pp.plan.confirm", lang): _decision("confirm_plan", production_date=day)}
    return [*blocks, QuickRepliesBlock(options=list(options))], options


def changed_text(out: PlanOut, item_id: str, names: Names, lang: str) -> str:
    """The item's batches and pieces after a change, and the oven minutes left."""
    line = next((x for x in out.lines if x.item_id == item_id), None)
    return t(
        "pp.change.done",
        lang,
        item=names.get(item_id, ""),
        batches=line.batches if line else 0,
        pieces=line.pieces if line else 0,
        date=out.production_date.isoformat(),
        minutes=out.minutes_free,
    )


def _ingredient(ingredient_id: str, milli: int, unit: str, names: Names, lang: str) -> str:
    name = names.get(ingredient_id, "")
    return t("pp.ingredient.line", lang, ingredient=name, amount=amount(milli), unit=unit)


def sheet_text(out: SheetOut, names: Names, lang: str) -> str:
    """The batch sheet: the batches and their yield, each ingredient times the batches (its
    cost when it has a pack price), then the cost per batch and per piece, or that the cost is
    not known while an ingredient has no pack price (Q55)."""
    item = names.get(out.item_id, "")
    lines = [t("pp.sheet.head", lang, item=item, batches=out.batches, pieces=out.batch_yield)]
    for x in out.lines:
        line = _ingredient(x.ingredient_id, x.quantity_milli, x.unit, names, lang)
        if x.cost is not None:
            cost = format_money(x.cost, out.currency, lang)
            line = t("pp.ingredient.cost", lang, line=line, cost=cost)
        lines.append(line)
    if out.cost_per_batch is None or out.cost_per_piece is None:
        lines.append(t("pp.sheet.cost_unknown", lang))
    else:
        batch = format_money(out.cost_per_batch, out.currency, lang)
        piece = format_money(out.cost_per_piece, out.currency, lang)
        lines.append(t("pp.sheet.cost", lang, batch=batch, piece=piece))
    return "\n".join(lines)


def recipe_card(
    args: RecipeInput, names: Names, lang: str, units: Mapping[str, str] | None = None
) -> list[Block]:
    """The recipe read from the message, to check before it is stored, and its Save button
    (the decision behind it is the caller's: recipe_save)."""
    lines = [
        t(
            "pp.recipe.card",
            lang,
            item=names.get(args.item_id, ""),
            pieces=args.batch_yield,
            minutes=args.oven_minutes,
        )
    ]
    for x in args.lines:
        unit = (units or {}).get(x.ingredient_id, "")
        lines.append(_ingredient(x.ingredient_id, x.quantity_milli, unit, names, lang))
    return [
        TextBlock(text="\n".join(lines)),
        QuickRepliesBlock(options=[t("pp.recipe.save", lang)]),
    ]


def recipe_save(args: RecipeInput, lang: str) -> Options:
    """The Save button of recipe_card: set_recipe with the recipe's args, marked saved."""
    return {t("pp.recipe.save", lang): _decision("set_recipe", **args.model_dump(), save=True)}


def recipe_text(args: RecipeInput, names: Names, lang: str) -> str:
    """The recipe saved: the item, its pieces per batch and oven minutes."""
    return t(
        "pp.recipe.saved",
        lang,
        item=names.get(args.item_id, ""),
        pieces=args.batch_yield,
        minutes=args.oven_minutes,
    )


def batch_text(out: BatchOut, names: Names, lang: str) -> str:
    """The batch's good pieces of its planned yield, its waste and reason, and the item's
    yield percent of the day so far; after the plan's last batch, that the lists are out."""
    common = {
        "item": names.get(out.item_id, ""),
        "batch": out.batch_no,
        "good": out.good,
        "planned": out.planned_yield,
        "percent": out.day_percent or 0,
    }
    if out.waste:
        reason = t(f"pp.reason.{out.reason or 'other'}", lang)
        text = t("pp.batch.done", lang, waste=out.waste, reason=reason, **common)
    else:
        text = t("pp.batch.done_clean", lang, **common)
    return "\n".join([text, t("pp.batch.last", lang)]) if out.last else text


def dispatch_text(out: DispatchOut, names: Names, lang: str) -> str:
    """The dispatch to one kiosk: its date and status, then each item and its pieces."""
    head = t(
        "pp.dispatch.head",
        lang,
        kiosk=names.get(out.branch_id, ""),
        date=out.business_date.isoformat(),
        status=t(f"pp.dispatch.status.{out.status}", lang),
    )
    lines = [
        t("pp.dispatch.line", lang, item=names.get(x["item_id"], ""), quantity=x["quantity"])
        for x in out.lines
    ]
    return "\n".join([head, *lines])


def dispatch_card(out: DispatchOut, names: Names, lang: str) -> tuple[list[Block], Options]:
    """The dispatch with a "Delivered: <kiosk>" button while it is packed: the button runs
    delivered for that kiosk and date (the turn holds it to the end of that date)."""
    blocks: list[Block] = [TextBlock(text=dispatch_text(out, names, lang))]
    if out.status != "packed":
        return blocks, {}
    label = t("pp.dispatch.delivered", lang, kiosk=names.get(out.branch_id, ""))
    day = out.business_date.isoformat()
    options = {label: _decision("delivered", kiosk_id=out.branch_id, business_date=day)}
    return [*blocks, QuickRepliesBlock(options=list(options))], options


def capacity_text(out: CapacityOut, names: Names, lang: str) -> str:
    """Whether the pieces asked about fit (when an item and pieces were asked) and the free
    oven minutes of the day, then each item's free pieces."""
    key = {None: "pp.capacity.free", True: "pp.capacity.fits", False: "pp.capacity.no_fit"}
    lines = [t(key[out.fits], lang, date=out.day.isoformat(), minutes=out.minutes_free)]
    for item_id, pieces in out.per_item.items():
        lines.append(t("pp.capacity.item", lang, item=names.get(item_id, ""), pieces=pieces))
    return "\n".join(lines)


def yield_text(out: YieldOut, names: Names, lang: str) -> str:
    """The day's yield per item: good of planned, waste and percent."""
    lines = [t("pp.yield.head", lang, date=out.day.isoformat())]
    for x in out.items:
        lines.append(
            t(
                "pp.yield.line",
                lang,
                item=names.get(x.item_id, ""),
                good=x.good,
                planned=x.planned,
                waste=x.waste,
                percent=x.percent or 0,
            )
        )
    return "\n".join(lines)
