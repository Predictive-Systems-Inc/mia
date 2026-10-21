"""The eval sets' test messages, one CSV per agent (cases/<agent_id>.csv, router.csv for the
router), and the loader every <agent>_cases.py builds its Case objects with.

Columns (HEADER): intent is the expected action, "ask" for a short row that should ask, or the
expected agent id in router.csv; message is the text as staff type it; lang is en, fil or fi;
half is tune, gate, short or spent; role is the sender's role; previous is Mia's last message
in the thread. The argument columns are blank when unused: item (an item name, or a code as
typed), amount (integer minor units), number (a count), date (an ISO date, or a "+Nd" token:
N days after the set's TODAY, which the set's own on() resolves), provider, category, kiosk,
direction and unit. extra is a JSON object for anything else a set carries (its scenario, the
remainder of an expected dict, several items, a router case's active agent and group), blank
otherwise. A run's results CSV (write_results) sits beside its raw json in docs/research."""

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FOLDER = Path(__file__).parent
HEADER = (
    "intent", "message", "lang", "half", "role", "previous", "item", "amount", "number", "date",
    "provider", "category", "kiosk", "direction", "unit", "extra",
)  # fmt: skip
ARGS = HEADER[6:15]
INTS = frozenset({"amount", "number"})
LANGS = frozenset({"en", "fil", "fi"})
HALVES = frozenset({"tune", "gate", "short", "spent"})
RESULTS = ("message", "lang", "half", "intent", "predicted", "confidence", "score", "missing")


@dataclass(frozen=True)
class Row:
    intent: str
    message: str
    lang: str
    half: str
    role: str
    previous: str
    args: dict[str, Any]  # the non-blank argument columns, amount and number as int
    extra: dict[str, Any]

    def expected(self, rename: dict[str, str] | None = None) -> dict[str, Any]:
        """A set's expected dict: the argument columns (renamed column -> key) and extra's
        "expected" remainder (the keys with no column, and None values)."""
        back = rename or {}
        return {back.get(k, k): v for k, v in self.args.items()} | self.extra.get("expected", {})

    def items(self) -> list[tuple[str, int | None]]:
        """The (item, quantity) pairs: extra's "items" when several, else the item and number
        columns (quantity None when the number is blank), else none."""
        if "items" in self.extra:
            return [(name, n) for name, n in self.extra["items"]]
        return [(self.args["item"], self.args.get("number"))] if "item" in self.args else []


def path(name: str) -> Path:
    return FOLDER / f"{name}.csv"


def header(name: str) -> tuple[str, ...]:
    """The CSV's header row as written."""
    with path(name).open(encoding="utf-8", newline="") as f:
        return tuple(next(csv.reader(f)))


def _parse(line: int, raw: dict[str, str]) -> Row:
    if raw["lang"] not in LANGS or raw["half"] not in HALVES or not raw["message"]:
        raise ValueError(f"line {line}: lang, half or message: {raw}")
    args = {k: int(raw[k]) if k in INTS else raw[k] for k in ARGS if raw[k] != ""}
    extra = json.loads(raw["extra"]) if raw["extra"] else {}
    if not isinstance(extra, dict):
        raise TypeError(f"line {line}: extra is no JSON object")
    common = (raw[k] for k in HEADER[:6])
    return Row(*common, args=args, extra=extra)


def read(name: str) -> list[Row]:
    """Every row of cases/<name>.csv in file order; raises ValueError (TypeError for an extra
    that is no object) naming the line when the header is not HEADER or a row does not parse."""
    if header(name) != HEADER:
        raise ValueError(f"{path(name)}: header is not {HEADER}")
    with path(name).open(encoding="utf-8", newline="") as f:
        return [_parse(n, raw) for n, raw in enumerate(csv.DictReader(f), start=2)]


def write(name: str, rows: list[dict[str, Any]]) -> None:
    """Writes rows (HEADER keys; extra a dict, written as JSON when not empty) to the CSV."""
    with path(name).open("w", encoding="utf-8", newline="") as f:
        out = csv.DictWriter(f, HEADER, lineterminator="\n")
        out.writeheader()
        for r in rows:
            extra = r.get("extra") or {}
            text = json.dumps(extra, ensure_ascii=False) if extra else ""
            out.writerow({k: r.get(k, "") for k in HEADER} | {"extra": text})


def write_results(
    raw: Path,
    results: list[dict[str, Any]],
    intent: str = "expected_action",
    predicted: str = "action",
) -> Path:
    """The run's results CSV beside its raw json (<name>.results.csv), one row per result with
    the RESULTS columns (intent and predicted read from the named result keys); refuses to
    overwrite an earlier run's file."""
    out = raw.with_name(raw.name.removesuffix(".raw.json") + ".results.csv")
    with out.open("x", encoding="utf-8", newline="") as f:  # "x": never overwrites
        w = csv.writer(f, lineterminator="\n")
        w.writerow(RESULTS)
        for r in results:
            row = (r["text"], r["lang"], r["half"], r[intent], r.get(predicted))
            w.writerow((*row, r.get("confidence"), r.get("score"), r.get("missing")))
    return out
