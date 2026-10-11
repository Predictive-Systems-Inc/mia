"""Teacher generation per coverage cell (spec section 4, step 4). Synthetic data only (D18).

Only the role plan (descriptions, labels, styles, slot names) goes to the teacher. Harvested
candidates and real messages are never read here.
"""

import logging
import math
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior

from mia.agents.base import build_model
from mia.agents.dispatcher.rules import rules_model
from mia.learning.schema import OTHER, Kind, Lang, Record, RoleSpec, Split, Style

log = logging.getLogger(__name__)
OTHER_SHARE = 0.08  # spec section 6: `other` is 5 to 10% of the data


class Cell(BaseModel):
    intent: str
    lang: Lang
    counterpart: str
    style: Style
    count: int
    kind: Kind = "normal"


class GeneratedMessage(BaseModel):
    """Teacher output. It is data: validated here, then filtered in `_keep`."""

    text: str = ""
    context: str = ""
    slots: dict[str, str] = Field(default_factory=dict)


def plan_cells(role: RoleSpec, split: Split, per_cell: int | None) -> list[Cell]:
    """Cells for every intent by language by counterpart by style, plus `other` cells.

    Each intent's per-language quota is split over its counterparts (by share) and the role's
    styles (by share), rounded up. `other` gets OTHER_SHARE of the per-language intent total,
    split over styles, with the role's first counterpart as the speaker. `per_cell` replaces
    every count.
    """
    cells: list[Cell] = []
    shares = {c.role: c.share for c in role.counterparts}
    for intent in role.intents:
        need = role.targets.quota(intent, split)
        speakers = intent.counterparts or ["unknown"]
        total_share = sum(shares.get(s, 1.0) for s in speakers)
        for lang in role.languages:
            for speaker in speakers:
                for style, share in role.styles.items():
                    n = per_cell or math.ceil(need * share * shares.get(speaker, 1.0) / total_share)
                    if n:
                        cells.append(
                            Cell(
                                intent=intent.id,
                                lang=lang,
                                counterpart=speaker,
                                style=style,
                                count=n,
                            )
                        )
    total = sum(role.targets.quota(i, split) for i in role.intents)
    speaker = role.counterparts[0].role if role.counterparts else "unknown"
    for lang in role.languages:
        for style, share in role.styles.items():
            n = per_cell or math.ceil(total * OTHER_SHARE * share)
            if n:
                cells.append(
                    Cell(
                        intent=OTHER,
                        lang=lang,
                        counterpart=speaker,
                        style=style,
                        count=n,
                        kind="other",
                    )
                )
    return cells


def _keep(msg: GeneratedMessage, allowed_slots: set[str]) -> str | None:
    """None when the message is usable, else the reason it is dropped."""
    if not msg.text.strip():
        return "empty text"
    if not set(msg.slots) <= allowed_slots:
        return "unknown slot"
    return None


def _ask(role: RoleSpec, cell: Cell) -> str:
    spec = role.intent(cell.intent)
    what = f"{cell.intent} ({spec.description})" if spec else "other: outside the role's intents"
    slots = f" Slots you may fill: {', '.join(spec.slots)}." if spec and spec.slots else ""
    return (
        f"Role: {role.id}. Intent: {what}. Language: {cell.lang}. "
        f"Speaker: {cell.counterpart}. Style: {cell.style}.{slots} "
        f"Write {cell.count} different messages."
    )


async def generate(
    role: RoleSpec,
    cells: list[Cell],
    model_name: str,
    prompt: str,
    split: Split,
    transport: Any = None,  # test seam: an httpx transport below egress (rule 6: no httpx here)
    drops: dict[str, int] | None = None,
) -> list[Record]:
    """One teacher call per cell; returns records, never more than `count` per cell.

    Messages with empty text or slot names outside the intent's slots are dropped and counted
    by reason in `drops` (when given). Ids are f"{intent}/{lang}/{tag}/{n:04d}".
    """
    agent: Agent[None, list[GeneratedMessage]] = Agent(
        build_model(model_name, rules_model(), transport=transport),
        output_type=list[GeneratedMessage],
        instructions=prompt,
        retries=2,
    )
    tag = model_name.replace("/", "-")
    out: list[Record] = []
    for cell in cells:
        spec = role.intent(cell.intent)
        allowed = set(spec.slots) if spec else set()
        try:
            result = await agent.run(_ask(role, cell))
        except UnexpectedModelBehavior as exc:  # one cell's bad output never ends the run
            log.warning("cell %s/%s skipped: %s", cell.intent, cell.lang, exc)
            if drops is not None:
                drops["model_error"] = drops.get("model_error", 0) + cell.count
            continue
        for msg in result.output[: cell.count]:
            reason = _keep(msg, allowed)
            if reason:
                log.warning("dropped teacher message in %s/%s: %s", cell.intent, cell.lang, reason)
                if drops is not None:
                    drops[reason] = drops.get(reason, 0) + 1
                continue
            out.append(
                Record(
                    id=f"{cell.intent}/{cell.lang}/{tag}/{len(out):04d}",
                    role=role.id,
                    intent=cell.intent,
                    lang=cell.lang,
                    text=msg.text,
                    context=msg.context,
                    counterpart=cell.counterpart,
                    style=cell.style,
                    slots=msg.slots,
                    kind=cell.kind,
                    split=split,
                    source=f"teacher:{model_name}",
                )
            )
    return out
