"""The hr officer decider eval set (spec 2026-10-19-hr-officer, sections 4 and 10): what
Ferino's clerks, head staff and owner send, ten messages per scenario in English and Filipino,
split into halves by seed (even seeds tune, odd seeds gate; a seed's languages share a half, so
no text is in both). The rows are cases/hr_officer.csv (its columns in cases/__init__.py: the
expected slots in extra); this module loads them. test_hr_officer_evals.py runs it.

Synthetic, written by Claude, not native speakers (D18). The Filipino rows are drafts for a
clerk texting on a phone (Q28). The regional language rows (ceb, hil, war, bcl) were dropped on
21 Oct 2026 to keep the run short; they are in git history. Dates are written as clerks write
them ("next week Monday", "sa susunod na linggo Lunes", "Dec 25", "bukas"); the run pins today
to TODAY, a Monday, so weekday phrases are stable and Christmas is inside the fourteen days a
holiday question picks from. The shape test checks every leave date is a find_dates candidate.
Expected inputs are offsets from TODAY ("+7d"), resolved by on().

The short half (D42): twelve en and twelve fil messages as clerks and the owner type on a
phone (lowercase, no punctuation, digits, one to six words), the en and fil written apart, not
translations; two per language are ambiguous and should ask ("ask"). Its one rule is no wrong
write (gate.wrong_writes); its expected slots are reported, never a bar. Its dates were written
for a Tuesday in November (PP_TODAY): "dec 2" and "nov 30" are past on this TODAY."""

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
    half: Literal["tune", "gate", "short"] = "tune"
    # file_leave {"start", "end"} and holiday_pay {"day"} as offsets; contributions {"which"}
    expected_slots: dict[str, str] = field(default_factory=dict)


GATED_LANGS = ("en", "fil")
TODAY = dt.date(2026, 12, 14)  # a Monday
SCENARIOS = (
    "my_hours", "payday", "thirteenth", "contributions", "file_leave", "leave_balance",
    "holiday_pay", "my_payslip", "certificate", "reply_only",
)  # fmt: skip


def on(value: str) -> str:
    """An offset "+Nd" as the ISO date N days after TODAY; any other value as it is."""
    if value.startswith("+") and value.endswith("d"):
        return (TODAY + dt.timedelta(days=int(value[1:-1]))).isoformat()
    return value


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
        row.extra.get("slots", {}),
    )


CASES: list[Case] = [_case(r) for r in cases.read("hr_officer")]
