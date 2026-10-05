"""Intent catalogue, English intent dataset and classification metrics (pure: no model).

The catalogue is docs/capabilities.md (one table row per intent); the dataset is intents_en.yaml
beside this file. Unit tested in tests/test_intent_metrics.py; used by the classification eval.
"""

import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

REPO = Path(__file__).resolve().parents[3]
CATALOGUE_PATH = REPO / "docs" / "capabilities.md"
DATASET_PATH = Path(__file__).with_name("intents_en.yaml")
OTHER = "other"
ROLE_CODES = {
    "C": "cleaner",
    "S": "supervisor",
    "O": "office",
    "A": "accountant",
    "CL": "client",
    "L": "lead",
    "AP": "applicant",
}
ROLES = frozenset(ROLE_CODES.values())
ROW = re.compile(r"^\| ([a-z_]+\.[a-z_]+) \|")


class CatalogueIntent(BaseModel):
    id: str
    meaning: str
    roles: frozenset[str]
    triggers: frozenset[str]
    built: str

    @property
    def agent(self) -> str:
        return agent_of(self.id)

    @property
    def by_message(self) -> bool:
        return "msg" in self.triggers


class Example(BaseModel):
    intent: str
    role: str
    text: str
    split: str = "train"
    near: str | None = None  # a hard negative: sounds like `near`, labelled with its true intent
    kind: str | None = None  # "injection" for injection attempts (labelled other)


@dataclass
class Result:
    example: Example
    predicted: str
    confidence: float
    seconds: float

    @property
    def correct(self) -> bool:
        return self.predicted == self.example.intent


def agent_of(intent: str) -> str:
    """The owning agent (area) of an intent id; `other` for the out-of-scope label."""
    return intent.split(".", 1)[0] if "." in intent else intent


def _roles(who: str) -> frozenset[str]:
    if who.strip() == "all":
        return ROLES
    if who.strip() == "-":
        return frozenset()
    return frozenset(ROLE_CODES[code.strip()] for code in who.split(","))


def load_catalogue(path: Path = CATALOGUE_PATH) -> dict[str, CatalogueIntent]:
    """Every intent row of the catalogue, by id. Raises on a duplicate id or a short row."""
    out: dict[str, CatalogueIntent] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 13:
            raise ValueError(f"catalogue row needs 13 cells: {line}")
        intent_id, meaning, who, trig = cells[:4]
        if intent_id in out:
            raise ValueError(f"duplicate intent {intent_id}")
        out[intent_id] = CatalogueIntent(
            id=intent_id,
            meaning=meaning,
            roles=_roles(who),
            triggers=frozenset(t.strip() for t in trig.split(",")),
            built=cells[11],
        )
    return out


def load_dataset(path: Path = DATASET_PATH) -> list[Example]:
    """All examples, flattened from {intent: [ {role, text, ...}, ... ]}."""
    raw: dict[str, list[dict[str, Any]]] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Example(intent=intent, **row) for intent, rows in raw.items() for row in rows]


def _rate(good: int, total: int) -> float:
    return round(good / total, 4) if total else 0.0


def _tally(results: list[Result], key: Any) -> dict[str, dict[str, float]]:
    groups: dict[str, list[Result]] = {}
    for r in results:
        groups.setdefault(key(r), []).append(r)
    return {
        k: {
            "n": len(v),
            "correct": sum(r.correct for r in v),
            "accuracy": _rate(sum(r.correct for r in v), len(v)),
        }
        for k, v in sorted(groups.items())
    }


def macro_f1(pairs: list[tuple[str, str]]) -> float:
    """Unweighted mean F1 over every label that occurs as gold or prediction."""
    labels = {g for g, _ in pairs} | {p for _, p in pairs}
    scores = []
    for label in labels:
        tp = sum(1 for g, p in pairs if g == label and p == label)
        fp = sum(1 for g, p in pairs if g != label and p == label)
        fn = sum(1 for g, p in pairs if g == label and p != label)
        scores.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return round(statistics.fmean(scores), 4) if scores else 0.0


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return round(ordered[round(q * (len(ordered) - 1))], 3)


def report(
    results: list[Result], catalogue: dict[str, CatalogueIntent], top: int = 15
) -> dict[str, Any]:
    """Accuracy overall, per area, per role, macro-F1, top confusions, latency and calibration.

    `invalid` counts predictions that are neither a catalogue id nor `other` (always wrong).
    """
    n = len(results)
    pairs = [(r.example.intent, r.predicted) for r in results]
    confusions = Counter((g, p) for g, p in pairs if g != p)
    confident = [r for r in results if r.confidence >= 0.8]
    per_intent = _tally(results, lambda r: r.example.intent)
    weakest = sorted(per_intent.items(), key=lambda kv: (kv[1]["accuracy"], -kv[1]["n"]))
    seconds = [r.seconds for r in results] or [0.0]
    hard = [r for r in results if r.example.near]
    injections = [r for r in results if r.example.kind == "injection"]
    return {
        "n": n,
        "accuracy": _rate(sum(r.correct for r in results), n),
        "area_accuracy": _rate(sum(agent_of(g) == agent_of(p) for g, p in pairs), n),
        "macro_f1": macro_f1(pairs),
        "invalid": sum(1 for _, p in pairs if p != OTHER and p not in catalogue),
        "by_area": _tally(results, lambda r: agent_of(r.example.intent)),
        "by_role": _tally(results, lambda r: r.example.role),
        "hard_negatives": {
            "n": len(hard),
            "accuracy": _rate(sum(r.correct for r in hard), len(hard)),
        },
        "injections": {
            "n": len(injections),
            "accuracy": _rate(sum(r.correct for r in injections), len(injections)),
        },
        "confusions": [[g, p, c] for (g, p), c in confusions.most_common(top)],
        "weakest_intents": [
            [k, v["correct"], v["n"]] for k, v in weakest[:top] if v["accuracy"] < 1
        ],
        "latency_s": {
            "mean": round(statistics.fmean(seconds), 3),
            "p50": _percentile(seconds, 0.5),
            "p95": _percentile(seconds, 0.95),
            "max": round(max(seconds), 3),
        },
        "calibration": {
            "confident_share": _rate(len(confident), n),
            "confident_accuracy": _rate(sum(r.correct for r in confident), len(confident)),
            "mean_confidence": round(statistics.fmean([r.confidence for r in results]), 3)
            if results
            else 0.0,
        },
    }


def format_report(rep: dict[str, Any], model: str) -> str:
    """A compact text version of report() for the console."""

    def table(rows: dict[str, dict[str, float]]) -> str:
        return ", ".join(
            f"{k} {v['correct']}/{v['n']} ({v['accuracy']:.0%})" for k, v in rows.items()
        )

    lat, cal, hard, inj = (
        rep["latency_s"],
        rep["calibration"],
        rep["hard_negatives"],
        rep["injections"],
    )
    head = f"intent classification: model={model} n={rep['n']} accuracy={rep['accuracy']:.1%}"
    scores = (
        f"area={rep['area_accuracy']:.1%} macro_f1={rep['macro_f1']:.3f} invalid={rep['invalid']}"
    )
    calibration = f"{cal['confident_accuracy']:.1%} (mean confidence {cal['mean_confidence']})"
    lines = [
        f"{head} {scores}",
        f"hard negatives {hard['accuracy']:.0%} of {hard['n']}, injections {inj['accuracy']:.0%} of {inj['n']}",
        f"latency mean {lat['mean']}s p50 {lat['p50']}s p95 {lat['p95']}s max {lat['max']}s",
        f"confidence>=0.8: {cal['confident_share']:.0%} of messages, accuracy {calibration}",
        "by area: " + table(rep["by_area"]),
        "by role: " + table(rep["by_role"]),
        "top confusions (gold -> predicted): "
        + "; ".join(f"{g} -> {p} x{c}" for g, p, c in rep["confusions"]),
        "weakest intents: " + "; ".join(f"{k} {c}/{n}" for k, c, n in rep["weakest_intents"]),
    ]
    return "\n".join(lines)
