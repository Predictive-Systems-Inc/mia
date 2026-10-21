"""The D40 gate bar, shared by the router and the agent decider eval harnesses."""

from typing import Any

# Languages whose strings are machine drafts (Q28 to Q35); one leaves when its native review lands.
DRAFTED = frozenset({"ceb", "ilo", "hil", "war", "bcl", "pam", "pag"})
RIGHT_MIN = {"full": 0.80, "drafted": 0.65}
ASK_MAX = {"full": 0.15, "drafted": 0.30}


def _shortfalls(lang: str, v: dict[str, Any]) -> list[str]:
    tier = "drafted" if lang in DRAFTED else "full"
    out = []
    if v.get("wrong", 0.0) > 0.02:
        out.append(f"{lang} wrong {v['wrong']}")
    if v["right"] < RIGHT_MIN[tier]:
        out.append(f"{lang} right {v['right']}")
    if v["ask"] > ASK_MAX[tier]:
        out.append(f"{lang} ask {v['ask']}")
    return out


def gate_failures(gated: dict[str, Any]) -> list[str]:
    """The blocking bar (D41) on a fresh gate half: wrong at most 2% overall (hard) and, for
    every language that is not a machine draft (en, fi, fil), wrong at most 2%, right at least
    80% and ask at most 15%, greetings left out. Empty when the gate passes. The drafted
    languages are measured by gate_reported and never block until their native review lands."""
    failed = [f"wrong {gated['all']['wrong']}"] if gated["all"]["wrong"] > 0.02 else []
    for lang, v in gated["by_language"].items():
        if lang not in DRAFTED:
            failed.extend(_shortfalls(lang, v))
    return failed


def gate_reported(gated: dict[str, Any]) -> list[str]:
    """The D40 reading of the machine-drafted languages (wrong at most 2%, right at least 65%,
    ask at most 30%): reported in every gate report, never asserted (D41)."""
    reported = []
    for lang, v in gated["by_language"].items():
        if lang in DRAFTED:
            reported.extend(_shortfalls(lang, v))
    return reported
