"""The customer service decider eval set (spec 2026-10-19-customer-service, scenarios 1 to 8):
what Ferino's customers (scenarios 1 to 7, the customer side) and its clerks and head staff
(scenario 8, the staff side) send, ten messages per scenario in English and Filipino and five
more for the gate. The rows are cases/customer_service.csv (its columns in cases/__init__.py: an
order's lines in the item and number columns or extra, its day a +Nd token in the date column,
its time in extra); this module loads them. test_customer_service_evals.py runs it.

Three sets, no text in two of them: the tune half (the even seeds of the ten), the spent gate
half (the odd seeds, scored in run 1, customer-service-2026-10-20-0125.raw.json, which failed;
kept so it is never written again and never scored again: the harness skips it) and the fresh
gate half (written before any run of them). The tune half also has cases
outside scenarios 1 to 8 (a price or a cancel with a count, security, greetings,
language switches); the gate stays scenarios 1 to 8.

Synthetic, written by Claude, not native speakers (D18). The Filipino rows are drafts for a customer
or a clerk texting on a phone (Q28). The regional language rows (ceb, hil, war, bcl) were dropped on
21 Oct 2026 to keep the run short; they are in git history. The run pins today to TODAY, a Tuesday
(the cs fixture seeds Ferino's on the same day, so Mila's 15:00 pickup is today's one order on the
staff side). Orders name their counts in digits, their time as code reads it (8am, 5:30pm, alas 4)
and their day with a word find_dates reads (bukas, tomorrow, a weekday, or none for today); the
shape test checks each one parses to the expected lines, time and day.

The short half (D42): twelve en and twelve fil messages as customers and clerks type on
a phone (lowercase, no punctuation, digits, one to six words), the en and fil written apart, not
translations; two per language are ambiguous and should ask ("ask"). Its side is its role (a
customer, or staff). Its one rule is no wrong write (gate.wrong_writes); its expected lines,
time, day and language are reported, never a bar."""

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
    role: str  # customer (the seeded Mila), or a seeded person's role (clerk, supervisor)
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "gate", "spent", "short"] = "tune"
    expected_language: str = ""  # language_switch only: the language asked for
    # place_order only: (item name, quantity) in message order, "HH:MM", a day offset "+Nd"
    expected_lines: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    expected_time: str = ""
    expected_day: str = ""


GATED_LANGS = ("en", "fil")
TODAY = dt.date(2026, 10, 20)  # a Tuesday, the cs fixture's day
SCENARIOS = (
    "hours", "prices", "place_order", "order_status", "delivery_area", "complaint",
    "cancel_order", "staff",
)  # fmt: skip
TUNE_ONLY_SCENARIOS = ("not_an_order", "security", "greeting", "language_switch")
UNGATED = {"greeting", "language_switch", "staff_resolve_complaint"}  # tune half only


def on(offset: str) -> str:
    """An offset "+Nd" as the ISO date N days after TODAY."""
    return (TODAY + dt.timedelta(days=int(offset[1:-1]))).isoformat()


def _case(row: cases.Row) -> Case:
    half: Any = row.half
    lines: Any = tuple(row.items())
    return Case(
        row.lang,
        row.extra["scenario"],
        row.message,
        row.intent,
        row.role,
        row.previous,
        half,
        row.extra.get("language", ""),
        lines,
        row.extra.get("time", ""),
        row.args.get("date", ""),
    )


CASES: list[Case] = [_case(r) for r in cases.read("customer_service")]
