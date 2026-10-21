"""The retail shift supervisor decider eval set (spec 2026-10-21-shift-supervisor-retail, scenarios
1 to 10 as chat asks): what Ferino's clerks and head staff send, in English and Filipino.
The rows are cases/shift_supervisor.csv (its columns in cases/__init__.py: dates as ISO); this
module loads them. test_shift_retail_evals.py runs it.

Two sets per scenario. The spent rows (ten seeds) were scored in the runs of 21 Oct
2026 (shift-supervisor-retail-2026-10-21-0303, 0305 and 0306 in docs/research): kept for the
record and never selected. The fresh rows (ten new seeds for the D40 rerun) say the same
intents in words no run has scored (shape test): the even seeds of a scenario are the tune half,
the odd seeds the gate half, and a seed's languages share a half (no text in both halves).
Scenario 10 (security) is `reply_only`: injected instructions and other agents' subjects (cash,
stock, sales counts, pay, leave, supplier orders), gated like the rest.

Synthetic, written by Claude, not native speakers (D18). The Filipino rows are drafts for a clerk or
head staff texting on a phone (Q28). The regional language rows (ceb, hil, war, bcl) were dropped on
21 Oct 2026 to keep the run short; they are in git history. The run pins today to TODAY (RS_TODAY, a
Wednesday), so "bukas", "sa Sabado" and "Nov 1" resolve the same on every run. Every roster pattern
is one code reads in full (roster.parse_pattern within the Mall kiosk's 09:00 to 21:00), and every
corrected time is a parsing.find_times candidate (shape test). The fresh rows follow the code's rule
7 guards: a check-out names no clock time, an incident names no "ran out" word, and a cover ask
names the stall and a day.

The short half (D42): twelve en and twelve fil messages as clerks and head staff type on
a phone (lowercase, no punctuation, digits, one to six words), the en and fil written apart, not
translations; two per language are ambiguous and should ask ("ask"). Its one rule is no wrong
write (gate.wrong_writes); its expected dates are reported, never a bar."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

from tests.evals import cases

Half = Literal["tune", "gate", "spent", "short"]  # spent: scored in an earlier run, never selected


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str  # a RETAIL_ACTIONS key
    role: str  # clerk (Ana), supervisor (Marites, Mall kiosk), stall_supervisor (Jun)
    previous: str = ""  # Mia's last message in the thread
    half: Half = "tune"
    # person (first name; None is the sender's own), date (ISO), kind (incident), time ("HH:MM")
    expected: dict[str, Any] = field(default_factory=dict)


GATED_LANGS = ("en", "fil")
TODAY = dt.date(2026, 10, 28)  # a Wednesday, RS_TODAY
# scenario: (expected action, sender role)
SCENARIOS: dict[str, tuple[str, str]] = {
    "set_roster": ("set_roster", "supervisor"),
    "check_in": ("check_in", "clerk"),
    "check_out": ("check_out", "clerk"),
    "late": ("record_absence", "clerk"),
    "sick": ("record_absence", "clerk"),
    "find_cover": ("find_replacements", "stall_supervisor"),
    "assign_cover": ("assign_cover", "stall_supervisor"),
    "swap": ("swap", "clerk"),
    "correct_time": ("correct_time", "clerk"),
    "equipment": ("report_site_problem", "clerk"),
    "no_delivery": ("report_site_problem", "clerk"),
    "customer": ("report_site_problem", "clerk"),
    "week_roster": ("week_roster", "clerk"),
    "close_day": ("close_day", "supervisor"),
    "security": ("reply_only", "clerk"),
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


CASES: list[Case] = [_case(r) for r in cases.read("shift_supervisor")]
