"""The branch manager decider eval set (spec 2026-10-19-branch-manager, scenarios 3 to 7, and the
weekly summary, monthly letter, short code and keep asks): what Ferino's owner, head staff and
clerks send, in English and Filipino. The rows are cases/branch_manager.csv (its columns in
cases/__init__.py, the price in the amount column); this module loads them.
test_branch_manager_evals.py runs it.

Every earlier row is spent: the first set (ten seeds per scenario; the even ones tuned, the odd ones
scored in run 1, branch-manager-2026-10-20-2049.raw.json) and the run 2 set (five seeds per
scenario, scored in run 2, branch-manager-2026-10-20-2120.raw.json, which fails D40 on bcl and
war). They are kept so no text is written again; the harness never runs them. The fresh rows are
the set for the D40 rerun: ten new seeds per scenario, even seeds tune, odd seeds gate, no text
in any earlier raw file or in a spent row (the shape test greps them). A seed's languages share
a half.

Synthetic, written by Claude, not native speakers (D18). The Filipino rows are drafts for an owner
or a clerk texting on a phone (Q28). The regional language rows (ceb, hil, war, bcl) were dropped on
21 Oct 2026 to keep the run short; they are in git history. Items are named as clerks type them
(Classic, Salted egg, Box of 4), never "bibingka" alone (a short code, not an item). Typed
experiments cover every strategy kind (price: charm, anchor, increase, decoy; promo: volume,
markdown, seasonal; bundle) and some name no strategy. Prices are digits find_prices reads; a price
change names its day with a word find_dates reads (a weekday, "Nov 1", "Nobyembre 2", bukas, ugma,
buwas, sa aga). The run pins today to TODAY, the bm fixture's Monday, so the weekdays resolve the
same on every run; the shape test checks each expected price, date and short code is a candidate
code gives Jev.

The short half (D42): twelve en and twelve fil messages as the owner and head staff type
on a phone (lowercase, no punctuation, digits, one to six words), the en and fil written apart,
not translations; two per language are ambiguous and should ask ("ask"). Its one rule is no
wrong write (gate.wrong_writes); its expected item and price are reported, never a bar."""

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
    role: str  # a role of a seeded Ferino's person (clerk Ana, supervisor Marites, owner Rosa)
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "spent", "gate", "short"] = "tune"
    # item (a seeded item name), price (minor units), code, keep, strategy (a name_key's last
    # part, reported only), kind (price, promo or bundle, reported only)
    expected: dict[str, Any] = field(default_factory=dict)


GATED_LANGS = ("en", "fil")
TODAY = dt.date(2026, 10, 26)  # a Monday, the bm fixture's day
# scenario: expected action
SEEDS: dict[str, str] = {
    "coaching": "coaching_who",
    "how_to_sell": "how_to_sell",
    "experiment_price": "propose_experiment",
    "experiment_promo": "propose_experiment",
    "change_price": "change_price",
    "short_code": "set_short_code",
    "weekly": "weekly_summary",
    "monthly": "monthly_letter",
    "keep": "decide_experiment_result",
}
SCENARIOS = tuple(SEEDS)


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
        row.expected({"amount": "price"}),
    )


CASES: list[Case] = [_case(r) for r in cases.read("branch_manager")]
