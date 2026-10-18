"""The shared labels' training rows: the model's label space holds the 87 conversation intents
and `other`, but a role's own data has none of the former and few of the latter. The intent
evaluation set (tests/evals/intents.jsonl) has both: conversation rows keep their label, other
roles' rows become `other`, the role's own rows are left out (they are the benchmark)."""

import json
from pathlib import Path

from mia.learning.shared_rows import shared_records


def _row(i: int, intent: str, split: str = "train", lang: str = "en", **extra: object) -> str:
    row = {
        "id": f"{intent}/{lang}/{i:03d}",
        "intent": intent,
        "lang": lang,
        "text": f"message {i}",
        "role": "cleaner",
        "style": "informal",
        "slots": {"date": "today"},
        "negative_of": None,
        "split": split,
        **extra,
    }
    return json.dumps(row)


def test_conversation_rows_keep_their_label_and_other_roles_become_other(tmp_path: Path) -> None:
    path = tmp_path / "intents.jsonl"
    path.write_text(
        "\n".join(
            [
                _row(1, "conversation.greeting"),
                _row(2, "sales.new_lead"),
                _row(3, "shift_supervisor.report_absence"),  # the role's own rows stay out
                _row(4, "conversation.thanks", split="test", lang="fi"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    recs = shared_records("shift_supervisor", path)
    assert [(r.intent, r.kind, r.split) for r in recs] == [
        ("conversation.greeting", "normal", "train"),
        ("other", "other", "train"),
        ("conversation.thanks", "normal", "test"),
    ]
    assert recs[0].id == "conversation.greeting/en/001"
    assert recs[0].role == "shift_supervisor" and recs[0].counterpart == "cleaner"
    assert recs[0].slots == {} and recs[0].source == "eval:tests/evals/intents.jsonl"
    assert recs[1].negative_of is None and recs[2].lang == "fi"


def test_a_share_of_train_rows_goes_to_dev_and_the_split_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "intents.jsonl"
    path.write_text(
        "\n".join(_row(i, "conversation.greeting") for i in range(60)) + "\n", encoding="utf-8"
    )
    once = shared_records("shift_supervisor", path)
    again = shared_records("shift_supervisor", path)
    dev = [r.id for r in once if r.split == "dev"]
    assert 5 <= len(dev) <= 15  # about one in six
    assert [r.split for r in once] == [r.split for r in again]


def test_unknown_style_and_missing_fields_do_not_break_a_row(tmp_path: Path) -> None:
    path = tmp_path / "intents.jsonl"
    path.write_text(
        _row(1, "conversation.greeting", style="shouting", role=None) + "\n", encoding="utf-8"
    )
    (rec,) = shared_records("shift_supervisor", path)
    assert rec.style == "informal" and rec.counterpart == "unknown"
