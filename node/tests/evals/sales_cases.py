"""The sales supervisor decider eval set (spec 2026-10-19-sales-supervisor, section 9): what
the clerks, head staff and owner of Ferino's bibingka kiosks send, in English and Filipino.
The rows are cases/sales_supervisor.csv (its columns in cases/__init__.py: one item in the item
and number columns, several in extra); this module loads them. test_sales_supervisor_evals.py
runs it.

Three sets, no text in two of them: spent (twenty messages per scenario
and language, both halves scored on 19 Oct; kept so they are never written or scored again, the
harness skips them), and the fresh set (ten per scenario and language for the D40
rerun, written on 21 Oct before any run of them and absent from every earlier raw file): its
even seeds tune, its odd seeds gate.

Synthetic, written by Claude, not native speakers (D18). The Filipino rows are drafts for a kiosk
clerk texting on a phone (Q28). The regional language rows (ceb, hil, war, bcl) were dropped on 21
Oct 2026 to keep the run short; they are in git history. Item names and short codes are the seed's
(mia/templates/retail/seed.py).

The short half (D42): sixteen en and sixteen fil messages as clerks, head staff and the
owner type on a phone (lowercase, no punctuation, digits, one to six words), the en and fil
written apart, not translations; two per language are ambiguous and should ask ("ask"). Four
per language are receipts (record, void, refund, read) and run on a receipts kiosk (extra
"source"; the tender, typed total, receipt number and which in extra). Its one
rule is no wrong write (gate.wrong_writes); its expected items are reported, never a bar."""

from dataclasses import dataclass, field
from typing import Any, Literal

from tests.evals import cases

# spent: scored in an earlier gate run, never run again; tune and gate: the fresh set.
Half = Literal["tune", "spent", "gate", "short"]


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str
    role: str  # clerk (Ana), supervisor (Marites) or owner (Rosa)
    expected_items: list[tuple[str, int]] = field(default_factory=list)  # (item name, quantity)
    previous: str = ""  # Mia's last message in the thread
    half: Half = "tune"
    source: str = "counts"  # the kiosk's sales source the row runs on (receipts or counts)


GATED_LANGS = ("en", "fil")
# scenario -> expected action
SCENARIOS: dict[str, str] = {
    "counts_codes": "report_sales",
    "counts_names": "report_sales",
    "correction": "correct_sales",
    "today": "sales_today",
    "target": "set_target",
    "period": "sales_period",
    "branch_item": "sales_period",
    "why": "why_answer",
    "reply_only": "reply_only",
}


def _case(row: cases.Row) -> Case:
    half: Any = row.half
    items: Any = row.items()
    return Case(
        row.lang,
        row.extra["scenario"],
        row.message,
        row.intent,
        row.role,
        items,
        row.previous,
        half,
        row.extra.get("source", "counts"),
    )


CASES: list[Case] = [_case(r) for r in cases.read("sales_supervisor")]
