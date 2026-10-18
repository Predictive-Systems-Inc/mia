"""The Q40 gate bar, shared by the router and the agent decider eval harnesses."""

from typing import Any


def gate_failures(gated: dict[str, Any]) -> list[str]:
    """The Q40 bar on a fresh gate half: wrong at most 2% (hard), and per gated language right
    at least 80% and ask at most 15% (greetings left out). Empty when the gate passes."""
    failed = [f"wrong {gated['all']['wrong']}"] if gated["all"]["wrong"] > 0.02 else []
    for lang, v in gated["by_language"].items():
        if v["right"] < 0.80:
            failed.append(f"{lang} right {v['right']}")
        if v["ask"] > 0.15:
            failed.append(f"{lang} ask {v['ask']}")
    return failed
