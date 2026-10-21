"""The retail router eval set (spec 2026-10-18-router-follow-up, decision 2): what clerks,
head staff and the owner of a bibingka shop send, gated in English and Filipino and reported in
Finnish. The rows are cases/router.csv (its columns in cases/__init__.py: the intent is the
expected agent id, "any" for a greeting or thanks, extra the active agent and the group of a
follow-up or switch); this module loads them. test_router_eval.py runs it.

Synthetic, written by Claude, not native speakers (D18). The Filipino and Finnish rows are
drafts for a kiosk clerk texting on a phone (Q28). The Finnish singles came from the intent
test split (intents.jsonl: the shift supervisor and conversation rows, no in-flow reply); each
of those is its own seed, even rows tune, odd rows spent. The regional language rows (ceb, hil,
war, bcl, ilo, pam, pag) were dropped on 21 Oct 2026 to keep the run short; they are in git
history."""

from dataclasses import dataclass
from typing import Any, Literal

from tests.evals import cases


@dataclass(frozen=True)
class Case:
    lang: str
    text: str
    expected: str  # an agent id, "any" (greeting or thanks: any agent is right) or "small_talk"
    active: str | None = None
    previous: str = ""
    group: str = "single"  # single | follow_up | switch
    half: Literal["tune", "spent", "gate"] = "tune"


GATED_LANGS = ("en", "fil")
REPORTED_LANGS = ("fi",)
# Agents scaffolded but without router cases yet; the gates step of /mia-build-agent empties this.
PENDING: set[str] = set()
# The agents router.csv has cases for (the shape test pins it; the scaffold reads this file).
ROUTED = (
    "bookkeeper",
    "branch_manager",
    "customer_service",
    "hr_officer",
    "inventory_manager",
    "production_planner",
    "sales_supervisor",
    "shift_supervisor",
)


def _case(row: cases.Row) -> Case:
    half: Any = row.half
    active, group = row.extra.get("active"), row.extra.get("group", "single")
    return Case(row.lang, row.message, row.intent, active, row.previous, group, half)


CASES: list[Case] = [_case(r) for r in cases.read("router")]
