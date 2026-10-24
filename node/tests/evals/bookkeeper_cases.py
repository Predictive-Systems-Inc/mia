"""The bookkeeper decider eval set (spec 2026-10-20-bookkeeper, scenarios 1 to 8, and the
balances, journal, tax and profit asks): what Ferino's head staff and owner send, ten messages
per scenario in English and Filipino. The rows are cases/bookkeeper.csv (its columns in
cases/__init__.py); this module loads them. test_bookkeeper_evals.py runs it.

Halves by seed: the even seeds of a scenario are the tune half, the odd seeds the gate half, and
a seed's languages share a half (no text in both halves, shape test). Scenario 10's security asks
(three injected instructions and one expense over the owner's limit) are tune-only, never gated.

Spent rows: the first set, whose tune and gate halves were both scored (the runs of 21 October 2026,
docs/research/bookkeeper-2026-10-21-0052 to 0054.raw.json). They keep half "spent", stay for the
shape tests and are never selected for a run. The fresh rows are the D40 rerun's seeds: no fresh
text was ever scored (shape test), and they cover the intents of the 0054 gate's wrong and ask rows
in other words.

The short half (D42): twelve en and twelve fil messages as head staff and the owner type
on a phone (lowercase, no punctuation, digits, one to six words), the en and fil written apart,
not translations; two per language are ambiguous and should ask ("ask"). Its one rule is no
wrong write (gate.wrong_writes); its expected amount is reported, never a bar.

Synthetic, written by Claude, not native speakers (D18). The Filipino rows are drafts for head staff
or the owner texting on a phone (Q28). The regional language rows (ceb, hil, war, bcl) were dropped
on 21 Oct 2026 to keep the run short; they are in git history. Amounts are written as head staff
type them ("12,450", "₱3,210", "P500", "1,500.50"); "2k" or "20k" is not read as an amount by
parsing.find_prices, so no case uses it (a "2k" gets the ask for the amount). The run pins today to
TODAY, the bk fixture's Tuesday, so "kahapon", "last week" and "this quarter" resolve the same on
every run; the shape test checks each expected amount is a candidate code gives Jev and each
provider is the one the text names."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

from tests.evals import cases


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str
    role: str  # a role of a seeded Ferino's person (supervisor Marites, owner Rosa)
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "gate", "spent", "short"] = "tune"
    # amount (minor units), provider (a SETTLERS or PLATFORMS value), category (CATEGORIES),
    # kind (petty cash: spend or refill)
    expected: dict[str, Any] = field(default_factory=dict)


GATED_LANGS = ("en", "fil")
TODAY = dt.date(2026, 11, 3)  # a Tuesday, the bk fixture's day
OWNER = "owner"
SUPERVISOR = "supervisor"
# scenario: (expected action, sender role)
SCENARIOS: dict[str, tuple[str, str]] = {
    "cash_count": ("cash_count", SUPERVISOR),
    "settlement": ("settlement", SUPERVISOR),
    "payout": ("payout", SUPERVISOR),
    "expense": ("expense", SUPERVISOR),
    "petty_cash": ("petty_cash", SUPERVISOR),
    "deposit": ("deposit", SUPERVISOR),
    "not_built": ("not_built", SUPERVISOR),
    "balances": ("balances", SUPERVISOR),
    "journal": ("journal", OWNER),
    "tax_quarter": ("tax_quarter", OWNER),
    "profit": ("profit", OWNER),
}


def _case(row: cases.Row) -> Case:
    half: Any = row.half
    return Case(
        row.lang,
        row.extra["scenario"],
        row.message,
        row.intent,
        row.role,
        row.previous,
        half,
        row.expected(),
    )


CASES: list[Case] = [_case(r) for r in cases.read("bookkeeper")]
