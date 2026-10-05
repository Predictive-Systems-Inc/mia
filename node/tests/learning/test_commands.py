from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mia.api.main import app
from mia.cli import main
from mia.learning import commands
from mia.learning.package import ModelCard, active_version, read_card, write_card
from mia.learning.schema import Record, load_records, write_records

ROLE_YAML = """
id: tr
job_summary: j
responsibilities: [x]
counterparts: [{role: c, share: 1.0}]
languages: [en]
countries: [FI]
styles: {informal: 1.0}
intents:
  - {id: tr.a, description: d, counterparts: [c], risk: read, label_en: A}
targets: {train_min: 1, dev: 1, test: 1}
"""


def rec(i: int, text: str, intent: str = "tr.a", status: str = "pending") -> Record:
    return Record.model_validate(
        {
            "id": f"tr/{i}",
            "role": "tr",
            "intent": intent,
            "lang": "en",
            "text": text,
            "counterpart": "c",
            "style": "informal",
            "split": "train",
            "source": "t",
            "review": {"status": status},
        }
    )


@pytest.fixture
def skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway role `tr` under a temporary agents folder."""
    monkeypatch.setattr(commands, "AGENTS", tmp_path / "agents")
    folder = tmp_path / "agents" / "tr" / "skill"
    (folder / "data").mkdir(parents=True)
    (folder / "role.yaml").write_text(ROLE_YAML, encoding="utf-8")
    return folder


def test_validate_reports_missing_role(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skills", "validate", "nobody"]) == 1
    assert "role.yaml not found" in capsys.readouterr().out


def test_validate_reports_errors_and_exit_1(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_records(skill / "data" / "train.jsonl", [rec(1, "im sick today", intent="tr.zzz")])
    assert main(["skills", "validate", "tr"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert "error: unknown intent tr.zzz in tr/1" in out
    assert "error: tr.a/en train 0 < 1" in out
    assert out[-1] == "1 records, 5 errors, 3 warnings"


def test_validate_clean_data_exit_0(skill: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for i, (name, text) in enumerate(
        [("train", "im sick today"), ("dev", "cant come tomorrow"), ("test", "fever, staying home")]
    ):
        write_records(
            skill / "data" / f"{name}.jsonl", [rec(i, text).model_copy(update={"split": name})]
        )
    other = rec(9, "what a lovely day", intent="other")
    write_records(skill / "data" / "train.jsonl", [rec(0, "im sick today"), other])
    assert main(["skills", "validate", "tr"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert not [line for line in out if line.startswith("error")]
    assert out[-1] == "4 records, 0 errors, 3 warnings"


def test_validate_rejects_a_bad_public_yaml(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (skill / "public.yaml").write_text(
        "datasets:\n  - {name: n, source: s, version: '1', licence: CC-BY-NC-4.0, use: train}\n",
        encoding="utf-8",
    )
    assert main(["skills", "validate", "tr"]) == 1
    assert "error: public.yaml: " in capsys.readouterr().out


def test_split_writes_train_and_dev(skill: Path, capsys: pytest.CaptureFixture[str]) -> None:
    texts = ["im sick today", "cant come tomorrow", "fever, staying home", "home sick"]
    write_records(
        skill / "data" / "reviewed.jsonl",
        [rec(i, t, status="kept") for i, t in enumerate(texts)]
        + [rec(9, "dropped one entirely", status="dropped")],
    )
    assert main(["skills", "split", "tr", "--seed", "3"]) == 0
    assert capsys.readouterr().out.strip() == "train=3 dev=1"
    train = load_records(skill / "data" / "train.jsonl")
    dev = load_records(skill / "data" / "dev.jsonl")
    assert len(train) == 3 and len(dev) == 1
    assert {r.split for r in train} == {"train"} and {r.split for r in dev} == {"dev"}
    assert "tr/9" not in {r.id for r in train + dev}
    assert not (skill / "data" / "test.jsonl").exists()


def test_split_unknown_intent_is_an_error_not_a_traceback(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_records(skill / "data" / "reviewed.jsonl", [rec(1, "hello", intent="tr.zzz")])
    assert main(["skills", "split", "tr"]) == 1
    assert capsys.readouterr().out == "error: unknown intent tr.zzz\n"


def test_split_missing_role_and_missing_reviewed(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["skills", "split", "tr"]) == 1
    assert capsys.readouterr().out == f"reviewed.jsonl not found in {skill / 'data'}\n"
    assert main(["skills", "split", "nobody"]) == 1
    assert "role.yaml not found" in capsys.readouterr().out


def test_train_without_learning_group_explains(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_torch(name: str) -> object:
        raise ImportError("torch missing")

    monkeypatch.setattr(commands, "import_module", no_torch)
    assert main(["skills", "train", "dispatcher"]) == 2
    assert capsys.readouterr().out == "install the learning group: uv sync --group learning\n"


def card(version: str, passed: bool = True) -> ModelCard:
    from tests.learning.test_package import card as base

    return base(passed=passed, version=version).model_copy(update={"role": "tr"})


def test_promote_without_a_package_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    capsys.readouterr()
    assert main(["skills", "promote", "tr", "v1", "--signed-by", "Allan"]) == 1
    assert capsys.readouterr().out == "tr@v1 not found\n"
    assert active_version("tr") is None


def test_promote_failed_gate_is_refused_with_the_reason(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    write_card(card("v1", passed=False))
    capsys.readouterr()
    assert main(["skills", "promote", "tr", "v1", "--signed-by", "Allan"]) == 1
    assert capsys.readouterr().out == "tr@v1 failed the gate: ['coverage']\n"
    assert active_version("tr") is None


def test_promote_activates_signs_and_emits_event(capsys: pytest.CaptureFixture[str]) -> None:
    from sqlmodel import select

    from mia.core.db import session_scope
    from mia.core.models import Event

    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    write_card(card("v1"))
    capsys.readouterr()
    assert main(["skills", "promote", "tr", "v1", "--signed-by", "Allan"]) == 0
    assert capsys.readouterr().out == "tr@v1 is active (signed by Allan)\n"
    assert active_version("tr") == "v1" and read_card("tr", "v1").signed_by == "Allan"
    with session_scope() as session:
        events = session.exec(select(Event).where(Event.action == "skill_model.promoted")).all()
    assert [(e.entity_id, e.actor_id) for e in events] == [("tr@v1", events[0].actor_id)]
    assert events[0].after == {"active": "v1", "signed_by": "Allan"}


def test_promote_and_harvest_need_exactly_one_branch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["migrate"]) == 0  # no seed: zero branches
    capsys.readouterr()
    msg = "the database has 0 branches; run `mia seed` or fix the data\n"
    assert main(["skills", "promote", "tr", "v1", "--signed-by", "A"]) == 1
    assert capsys.readouterr().out == msg
    assert main(["skills", "harvest", "tr"]) == 1
    assert capsys.readouterr().out == msg


def test_harvest_prints_the_count(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    capsys.readouterr()
    assert main(["skills", "harvest", "dispatcher"]) == 0
    assert capsys.readouterr().out == "0 new candidates\n"


def test_health_includes_skills(branch: object, monkeypatch: pytest.MonkeyPatch) -> None:
    from mia.skills import runtime

    status = {"dispatcher": {"status": "active", "version": "v7"}}
    monkeypatch.setattr(runtime, "_status", status)
    assert TestClient(app).get("/health").json()["skills"] == status
