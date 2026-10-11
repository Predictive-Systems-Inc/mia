"""Bake-off decision and report (pure; spec embedding review section 4)."""

from mia.learning.metrics import TEMPERATURE_GRID
from mia.learning.package import ModelCard


def choose_winner(cards: list[ModelCard], role_has_slots: bool) -> ModelCard | None:
    """Best macro F1, then coverage, among cards that passed the gate (the first on a full tie).
    A role with slot intents keeps the encoder (the only kind with slot heads). None when no
    card qualifies."""
    ok = [c for c in cards if c.gate.passed and (c.kind == "encoder" or not role_has_slots)]
    return max(ok, key=lambda c: (c.report.macro_f1, c.report.coverage), default=None)


def render_bakeoff(
    cards: list[ModelCard],
    winner: ModelCard | None,
    latency_ms: dict[str, float],
    *,
    role_has_slots: bool = False,
) -> str:
    """Markdown: the winner line (naming kinds that passed the gate but were excluded because
    the role has slot intents), one table row per card (latency nan when not measured), lines
    naming cards whose temperature hit either end of the grid, and the no-promotion note."""
    rows = [
        "| kind | version | macro F1 | coverage | accuracy | ECE | safety recall | gate | ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cards:
        r = c.report
        rows.append(
            f"| {c.kind} | {c.version} | {r.macro_f1:.3f} | {r.coverage:.3f} | {r.accuracy:.3f} "
            f"| {r.ece:.3f} | {r.safety_recall:.3f} | {'passed' if c.gate.passed else 'failed'} "
            f"| {latency_ms.get(c.version, float('nan')):.1f} |"
        )
    floor, ceiling = TEMPERATURE_GRID[0], TEMPERATURE_GRID[-1]
    low = [c.version for c in cards if c.temperature == floor]
    high = [c.version for c in cards if c.temperature == ceiling]
    notes = []
    if low:
        notes.append(
            f"Temperature at the grid edge ({floor:g}; SCALE may be too small, coverage "
            f"understated): {', '.join(low)}"
        )
    if high:
        notes.append(
            f"Temperature at the grid ceiling ({ceiling:g}; the model is overconfident): "
            f"{', '.join(high)}"
        )
    if notes:
        rows += ["", *notes]
    excluded = [c.kind for c in cards if role_has_slots and c.gate.passed and c.kind != "encoder"]
    why = f"excluded: {', '.join(excluded)} (role has slot intents)" if excluded else ""
    if winner:
        head = [f"Winner: {winner.kind} {winner.version}", *([why] if why else [])]
    else:
        head = [f"Winner: none ({why})" if why else "Winner: none passed the gate"]
    return "\n".join(
        [
            "# Bake-off",
            "",
            *head,
            "",
            *rows,
            "",
            (
                "No contender is promoted by the bake-off; promote the winner with "
                "`mia skills promote <role> <version> --signed-by NAME` after Gate 2."
            ),
            "",
        ]
    )
