"""Training rows for the shared labels (spec 2026-10-06-skill-models-design, Gate 2 finding of
12 Oct 2026). A role model's label space is its own intents, the 87 conversation intents and
`other`, but the role's generated data holds only the first and a little of the last. The
intent evaluation set (tests/evals/intents.jsonl, every role, en and fi) supplies the rest:
conversation rows keep their label, another role's rows become `other` (they are outside this
role's intents, which is what `other` means), and the role's own rows are left out because that
set is the benchmark the whole pipeline is measured on.

Rows keep the set's split (train or test); about one train row in six goes to dev by a stable
hash of its id, so the calibration step has rows for these labels too. The rows are data (rule
8): only their text and labels are read, nothing in them is executed.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, get_args

from mia.learning.schema import OTHER, Record, Style

CONVERSATION = "conversation."
SOURCE = "eval:tests/evals/intents.jsonl"
EVAL_DATASET = Path(__file__).resolve().parents[2] / "tests" / "evals" / "intents.jsonl"
DEV_SHARE = 6  # one train row in six goes to dev
_STYLES = set(get_args(Style))


def _split(row: dict[str, Any]) -> str:
    if row.get("split") == "test":
        return "test"
    digest = hashlib.sha256(str(row["id"]).encode()).digest()
    return "dev" if digest[0] % DEV_SHARE == 0 else "train"


def shared_records(role: str, path: Path) -> list[Record]:
    """The shared labels' records for `role` from the evaluation set at `path`, in file order.
    A row of the role itself is skipped; a row of another role is labelled `other`."""
    out: list[Record] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        intent = str(row["intent"])
        if intent.startswith(f"{role}."):
            continue
        shared = intent.startswith(CONVERSATION)
        style: Style = row["style"] if row.get("style") in _STYLES else "informal"
        out.append(
            Record(
                id=str(row["id"]),
                role=role,
                intent=intent if shared else OTHER,
                lang=row["lang"],
                text=row["text"],
                counterpart=str(row.get("role") or "unknown"),
                style=style,
                kind="normal" if shared else "other",
                split=_split(row),  # type: ignore[arg-type]
                source=SOURCE,
            )
        )
    return out
