"""Bake-off decision and report (pure; spec embedding review section 4)."""

from mia.learning.package import ModelCard

GRID_EDGE = 0.5  # lowest temperature metrics.fit_temperature tries


def choose_winner(cards: list[ModelCard], role_has_slots: bool) -> ModelCard | None:
    """Best macro F1, then coverage, among cards that passed the gate (the first on a full tie).
    A role with slot intents keeps the encoder (the only kind with slot heads). None when no
    card qualifies."""
    ok = [c for c in cards if c.gate.passed and (c.kind == "encoder" or not role_has_slots)]
    return max(ok, key=lambda c: (c.report.macro_f1, c.report.coverage), default=None)


def render_bakeoff(
    cards: list[ModelCard], winner: ModelCard | None, latency_ms: dict[str, float]
) -> str:
    """Markdown: the winner line, one table row per card (latency nan when not measured), a
    line naming cards whose temperature hit the grid edge, and the no-promotion note."""
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
    edge = [c.version for c in cards if c.temperature == GRID_EDGE]
    if edge:
        rows += [
            "",
            (
                f"Temperature at the grid edge ({GRID_EDGE}; SCALE may be too small, coverage "
                f"understated): {', '.join(edge)}"
            ),
        ]
    head = f"Winner: {winner.kind} {winner.version}" if winner else "Winner: none passed the gate"
    return "\n".join(
        [
            "# Bake-off",
            "",
            head,
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
