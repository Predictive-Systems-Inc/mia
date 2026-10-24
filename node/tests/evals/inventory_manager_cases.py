"""The inventory manager decider eval set (spec 2026-10-19-inventory-manager, sections 4 and
10): what the clerks, head staff and owner of Ferino's bibingka kiosks send, ten messages per
scenario in English and Filipino, split into halves by seed (no text in both halves). The rows
are cases/inventory_manager.csv (its columns in cases/__init__.py: one item in the item and
number columns, several in extra); this module loads them. test_inventory_manager_evals.py runs
it.

Synthetic, written by Claude, not native speakers (D18). The Filipino rows are drafts for a kiosk
clerk texting on a phone (Q28). The regional language rows (ceb, hil, war, bcl) were dropped on 21
Oct 2026 to keep the run short; they are in git history. Item and ingredient names and short codes
are the seed's (mia/templates/retail/seed.py). A bare number is a count, never a time; the tune half
writes times "2pm" or "16:00", the gate half also "3 pm" and "alas 2" (strip_times takes them out).

Halves: every 19 Oct row (the first tune half with the spent first gate half folded in, and the
19 Oct gate half) is spent, both halves ran; the harness never runs a spent
row. The 21 Oct rows (for the D40 rerun) are the fresh set: ten new seeds per scenario, the
even seeds the tune half and the odd seeds the gate half; message n of a scenario is one seed
in every language, so a seed's languages share a half.

The short half (D42): twelve en and twelve fil messages as clerks, head staff and the
owner type on a phone (lowercase, no punctuation, digits, one to six words), the en and fil
written apart, not translations; two per language are ambiguous and should ask ("ask"). Its one
rule is no wrong write (gate.wrong_writes); its expected items are reported, never a bar."""

from dataclasses import dataclass, field
from typing import Any, Literal

from tests.evals import cases


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str
    role: str  # clerk (Ana), supervisor (Marites) or owner (Rosa)
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "gate", "spent", "short"] = "tune"
    # report_stock: sold_out, count, leftover, waste, low, or on_hand (a count or leftover
    # question with no number: Mia answers how many are left)
    expected_kind: str = ""
    # (item or ingredient name, quantity); None for a message with no number
    expected_items: list[tuple[str, int | None]] = field(default_factory=list)
    # "reason" for a waste without one, "quantity" for a waste with no number (Mia asks)
    expected_missing: str | None = None


GATED_LANGS = ("en", "fil")
# Words in the cases that name an item but are no name word or short code: Jev maps them.
SYNONYMS = {"Coconut": {"coconuts"}}
# scenario -> (expected action, expected kind): the 19 Oct sets, then the fresh set's
SCENARIOS: dict[str, tuple[str, str]] = {
    "sold_out": ("report_stock", "sold_out"),
    "counts_left": ("report_stock", "count"),
    "leftovers": ("report_stock", "leftover"),
    "waste": ("report_stock", "waste"),
    "low_ingredient": ("report_stock", "low"),
    "bake_plan": ("bake_plan", ""),
    "whats_low": ("whats_low", ""),
    "place_order": ("place_order", ""),
    "receive": ("receive", ""),
    "reply_only": ("reply_only", ""),
}
FRESH: dict[str, tuple[str, str]] = SCENARIOS | {
    "on_hand": ("report_stock", "on_hand"),
    "waste_no_number": ("report_stock", "waste"),
}


def _case(row: cases.Row) -> Case:
    half: Any = row.half
    kind, missing = row.extra.get("kind", ""), row.extra.get("missing")
    return Case(
        row.lang,
        row.extra["scenario"],
        row.message,
        row.intent,
        row.role,
        row.previous,
        half,
        kind,
        row.items(),
        missing,
    )


CASES: list[Case] = [_case(r) for r in cases.read("inventory_manager")]
