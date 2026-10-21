"""The production planner decider eval set (spec 2026-10-21-production-planner, scenarios 1 to 7
and 9 as chat asks): what the commissary head, the owner, the driver and a kiosk supervisor
send, in English and Filipino. The rows are cases/production_planner.csv (its columns in
cases/__init__.py); this module loads them. test_production_planner_evals.py runs it.

Two sets. The spent rows were scored by
the 0747 tune and 0748 gate runs and are kept only as a record: half "spent", never selected.
The fresh rows (written for the D40 rerun) are ten per scenario, halves by seed: the
even seeds of a scenario are the tune half, the odd seeds the gate half, and a seed's languages
share a half (no text in both halves, and no fresh text in a spent row or either raw file of
the earlier runs, shape test). They cover the intents the 0748 run got wrong or asked on with
other words: the dispatch texts name the delivery or the dispatch (so "how many pieces are we
getting" is not the plan question), the batch sheet asks name one item (an ingredient word is
never an item), and each change states its unit, its number and, for more or fewer, an add or
remove word of the language (the guards ask a change without a unit and never let an add or
remove word set; words.directions and words.units, shape test).

Scenario 1 is two asks (the plan, and "ok" answering the draft plan), scenario 7 two (a kiosk
supervisor asking what the delivery brings and the driver's delivered); scenario 2 (confirmed
orders in the plan) is asked as the plan. The draft plan Mia sent before every confirm (DRAFT)
is built from the reply keys (pp.plan.*), so it reads as the real reply in each language; the
CSV keeps it as text and the shape test checks it is still DRAFT.

Synthetic, written by Claude, not native speakers (D18). The Filipino rows are drafts for commissary
and kiosk staff texting on a phone (Q28). The regional language rows (ceb, hil, war, bcl) were
dropped on 21 Oct 2026 to keep the run short; they are in git history. The run pins today to TODAY
(PP_TODAY, a Tuesday) with tomorrow's plan drafted, so "bukas" and "tomorrow" name the plan's date.
Code reads every value Jev picks (rule 7), and the shape test checks it: each expected number is a
words.numbers candidate, each batch report a words.batch parse, each recipe a full words.recipe
parse (one part per comma, units and short codes code knows), each added or removed item a line of
the drafted plan, and each fresh item ask names that one item (words.named). No change text names
"today" (ngayon), which would ask for the plan of another day.

The short half (D42): twelve en and twelve fil messages as the commissary head, the
owner, the driver and a kiosk clerk type on a phone (lowercase, no punctuation, digits, one to
six words), the en and fil written apart, not translations; two per language are ambiguous and
should ask ("ask"). Its one rule is no wrong write (gate.wrong_writes); its expected item and
number are reported, never a bar."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

from mia.i18n import t
from tests.evals import cases


@dataclass(frozen=True)
class Case:
    lang: str
    scenario: str
    text: str
    expected_action: str  # an ACTIONS key
    # head (Nonoy, the commissary), owner (Rosa), driver (Berto), kiosk (Marites), clerk (Ana)
    role: str
    previous: str = ""  # Mia's last message in the thread
    half: Literal["tune", "gate", "spent", "short"] = "tune"  # spent: scored, never run again
    # item (an item name), kiosk (a branch name), direction (a DIRECTIONS key), number (a count)
    expected: dict[str, Any] = field(default_factory=dict)


GATED_LANGS = ("en", "fil")
TODAY = dt.date(2026, 11, 10)  # a Tuesday, PP_TODAY
HEAD, OWNER, DRIVER, KIOSK = "head", "owner", "driver", "kiosk"
# scenario: (spec scenario, expected action, sender role)
SCENARIOS: dict[str, tuple[int, str, str]] = {
    "plan": (1, "plan", HEAD),
    "confirm": (1, "confirm_plan", HEAD),
    "orders": (2, "plan", HEAD),
    "change": (3, "change_plan", HEAD),
    "batch_sheet": (4, "batch_sheet", HEAD),
    "recipe": (5, "set_recipe", OWNER),
    "batch": (6, "record_batch", HEAD),
    "dispatch": (7, "dispatch", KIOSK),
    "delivered": (7, "delivered", DRIVER),
    "capacity": (9, "capacity", OWNER),
}
# Mia's draft plan reply (replies.plan_text), the previous message of every confirm case: its
# head and lines from the reply keys of each language.
_DRAFTED = (("Classic", 3, 144), ("Special", 2, 72), ("Ube", 1, 36))


def _draft(lang: str) -> str:
    day = (TODAY + dt.timedelta(days=1)).isoformat()
    status = t("pp.plan.status.draft", lang)
    head = t("pp.plan.head", lang, date=day, status=status, minutes=120)
    lines = [t("pp.plan.line", lang, item=i, batches=b, pieces=p) for i, b, p in _DRAFTED]
    return "\n".join([head, *lines])


DRAFT: dict[str, str] = {lang: _draft(lang) for lang in GATED_LANGS}


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


CASES: list[Case] = [_case(r) for r in cases.read("production_planner")]
