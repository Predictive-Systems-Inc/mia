"""The D40 gate bar, shared by the router and the agent decider eval harnesses."""

from typing import Any

# Languages whose strings are machine drafts (Q28 to Q35); one leaves when its native review lands.
DRAFTED = frozenset({"ceb", "ilo", "hil", "war", "bcl", "pam", "pag"})
RIGHT_MIN = {"full": 0.80, "drafted": 0.65}
ASK_MAX = {"full": 0.15, "drafted": 0.30}


def gate_failures(gated: dict[str, Any]) -> list[str]:
    """The D40 bar on a fresh gate half: wrong at most 2% overall and in every gated language
    (hard), and per gated language right at least 80% and ask at most 15%, relaxed to 65% and
    30% for a machine-drafted language (DRAFTED), greetings left out. Empty when the gate
    passes."""
    failed = [f"wrong {gated['all']['wrong']}"] if gated["all"]["wrong"] > 0.02 else []
    for lang, v in gated["by_language"].items():
        tier = "drafted" if lang in DRAFTED else "full"
        if v.get("wrong", 0.0) > 0.02:
            failed.append(f"{lang} wrong {v['wrong']}")
        if v["right"] < RIGHT_MIN[tier]:
            failed.append(f"{lang} right {v['right']}")
        if v["ask"] > ASK_MAX[tier]:
            failed.append(f"{lang} ask {v['ask']}")
    return failed
