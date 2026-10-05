"""Intent catalogue, intent dataset and classification metrics (pure: no model).

docs/capabilities.md is written by people; intents_catalogue.yaml beside this file is generated
from it (`uv run python -m tests.evals.intents` from node/) and is what generators, trainers and
the eval read. intents.jsonl holds one record per utterance (all languages, `lang` tells which).
Unit tested in tests/test_intent_metrics.py; used by test_intent_classification.py.
"""

import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
CAPABILITIES_MD = HERE.parents[2] / "docs" / "capabilities.md"
CATALOGUE_PATH = HERE / "intents_catalogue.yaml"
DATASET_PATH = HERE / "intents.jsonl"
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
PROCESSES = {
    "L2C": "Lead-to-Contract",
    "C2S": "Contract-to-Service",
    "S2C": "Service-to-Cash",
    "H2R": "Hire-to-Retire",
    "P2P": "Procure-to-Pay",
    "R2R": "Record-to-Report",
    "Plat": "platform",
}
STYLES = frozenset({"formal", "informal", "typo", "indirect", "terse", "mixed"})
ROW = re.compile(r"^\| ([a-z_]+\.[a-z_]+) \|")


class CatalogueIntent(BaseModel):
    id: str
    agent: str
    process: str
    label_en: str | None  # button label for clarifying questions (message intents, max 20)
    description: str
    roles: list[str]
    triggers: list[str]
    risk: str
    sensitivity: str
    approval: str
    legal_effect: bool
    system_of_record: str
    country: str
    phase: int
    built: str

    @property
    def by_message(self) -> bool:
        return "msg" in self.triggers


class Example(BaseModel):
    id: str  # <intent>/<lang>/<number>, stable once published
    intent: str
    lang: Literal["en", "fi", "fil", "mixed"]
    text: str
    role: str
    style: str
    slots: dict[str, Any] = Field(default_factory=dict)
    negative_of: str | None = None  # hard negative: looks like this intent, labelled with its own
    split: Literal["train", "test"] = "train"
    kind: Literal["injection"] | None = None  # injection attempts (labelled other)


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


def _roles(who: str) -> list[str]:
    if who.strip() == "all":
        return sorted(ROLES)
    if who.strip() == "-":
        return []
    return [ROLE_CODES[code.strip()] for code in who.split(",")]


def parse_capabilities(path: Path = CAPABILITIES_MD) -> list[CatalogueIntent]:
    """Every intent row of docs/capabilities.md in order. Raises on a duplicate or short row."""
    out: list[CatalogueIntent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 14:
            raise ValueError(f"catalogue row needs 14 cells: {line}")
        iid, label, meaning, who, trig, risk, sens, approval, legal, sor, ctry, ph, built, proc = (
            cells
        )
        if any(i.id == iid for i in out):
            raise ValueError(f"duplicate intent {iid}")
        out.append(
            CatalogueIntent(
                id=iid,
                agent=agent_of(iid),
                process=PROCESSES[proc],
                label_en=None if label == "-" else label,
                description=meaning,
                roles=_roles(who),
                triggers=[t.strip() for t in trig.split(",")],
                risk=risk,
                sensitivity=sens,
                approval=approval,
                legal_effect=legal == "y",
                system_of_record=sor,
                country=ctry,
                phase=int(ph),
                built=built,
            )
        )
    return out


def catalogue_yaml(intents: list[CatalogueIntent]) -> str:
    """The machine-readable catalogue file, generated from docs/capabilities.md."""
    head = (
        "# Generated from docs/capabilities.md; do not edit. Regenerate from node/ with:\n"
        "#   uv run python -m tests.evals.intents\n"
        "# Labels are these ids plus `other` (out of scope, injection attempts). Role codes, risk,\n"
        "# sensitivity and process are explained in the legend of docs/capabilities.md.\n"
    )
    body = yaml.safe_dump(
        {"intents": [i.model_dump() for i in intents]},
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    return head + body


def load_catalogue(path: Path = CATALOGUE_PATH) -> dict[str, CatalogueIntent]:
    """The catalogue by id."""
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))["intents"]
    return {row["id"]: CatalogueIntent(**row) for row in rows}


def load_dataset(path: Path = DATASET_PATH, lang: str | None = None) -> list[Example]:
    """All records of the JSONL dataset (one utterance per line), optionally one language."""
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [Example(**json.loads(line)) for line in lines if line.strip()]
    return [r for r in rows if lang is None or r.lang == lang]


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
    hard = [r for r in results if r.example.negative_of]
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


if __name__ == "__main__":
    CATALOGUE_PATH.write_text(catalogue_yaml(parse_capabilities()), encoding="utf-8")
