import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mia.api.main import app
from mia.cli import main
from mia.learning import commands
from mia.learning.package import ModelCard, active_version, read_card, write_card
from mia.learning.schema import Record, load_records, write_records
from tests.learning.helpers import card as base_card
from tests.learning.helpers import write_package

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
    assert out[-1] == "1 records, 5 errors, 4 warnings"


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
    assert out[-1] == "4 records, 0 errors, 4 warnings"


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


def test_train_surfaces_real_import_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(exc: Exception):  # type: ignore[no-untyped-def]
        def raiser(name: str) -> object:
            raise exc

        return raiser

    monkeypatch.setattr(commands, "import_module", broken(ImportError("bug")))
    with pytest.raises(ImportError, match="bug"):
        main(["skills", "train", "dispatcher"])
    monkeypatch.setattr(commands, "import_module", broken(ModuleNotFoundError("x", name="mia.x")))
    with pytest.raises(ModuleNotFoundError):
        main(["skills", "train", "dispatcher"])


def test_train_missing_learning_package_gives_the_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def raiser(name: str) -> object:
        raise ModuleNotFoundError("No module named 'torch'", name="torch")

    monkeypatch.setattr(commands, "import_module", raiser)
    assert main(["skills", "train", "dispatcher"]) == 2
    assert capsys.readouterr().out == "install the learning group: uv sync --group learning\n"


def test_validate_malformed_jsonl_is_an_error_not_a_traceback(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = skill / "data" / "train.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    assert main(["skills", "validate", "tr"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith(f"error: {path}: ")
    assert not any(line.startswith("Traceback") for line in out)


def card(version: str, passed: bool = True) -> ModelCard:
    return base_card(passed=passed, version=version).model_copy(update={"role": "tr"})


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
    write_package(card("v1"))
    capsys.readouterr()
    assert main(["skills", "promote", "tr", "v1", "--signed-by", "Allan"]) == 0
    assert capsys.readouterr().out == "tr@v1 is active (signed by Allan)\n"
    assert active_version("tr") == "v1" and read_card("tr", "v1").signed_by == "Allan"
    with session_scope() as session:
        events = session.exec(select(Event).where(Event.action == "skill_model.promoted")).all()
    assert [(e.entity_id, e.actor_type, e.actor_id) for e in events] == [
        ("tr@v1", "system", "system")
    ]
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


def test_invalid_role_yaml_is_reported_not_raised(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (skill / "role.yaml").write_text("id: tr\n", encoding="utf-8")
    assert main(["skills", "validate", "tr"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "role.yaml is invalid: 7 validation errors for RoleSpec"
    assert out[1] == "job_summary"


def test_train_prints_the_gate_result(
    skill: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[Path, str | None, bool]] = []

    def train_role(folder: Path, base_model: str | None, with_real: bool) -> ModelCard:
        calls.append((folder, base_model, with_real))
        return card("v7", passed=False)

    monkeypatch.setattr(
        commands, "import_module", lambda name: SimpleNamespace(train_role=train_role)
    )
    assert main(["skills", "train", "tr", "--base-model", "b", "--with-real"]) == 0
    assert capsys.readouterr().out == "tr@v7: gate failed\n  coverage\n"
    assert calls == [(skill, "b", True)]
    monkeypatch.setattr(
        commands,
        "import_module",
        lambda name: SimpleNamespace(train_role=lambda *a, **k: card("v8")),
    )
    assert main(["skills", "train", "tr"]) == 0
    assert capsys.readouterr().out == "tr@v8: gate passed\n"


def test_train_kind_dispatches_to_the_contender(
    skill: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, Path, str | None, bool]] = []
    modules: list[str] = []

    def fake(kind: str, version: str):  # type: ignore[no-untyped-def]
        def run(folder: Path, embedding_model: str | None = None, with_real: bool = False):  # type: ignore[no-untyped-def]
            calls.append((kind, folder, embedding_model, with_real))
            return card(version)

        return run

    def load(name: str) -> object:
        modules.append(name)
        return SimpleNamespace(
            train_knn=fake("knn", "v1-knn"), train_contrastive=fake("contrastive", "v1-c")
        )

    monkeypatch.setattr(commands, "import_module", load)
    assert main(["skills", "train", "tr", "--kind", "knn", "--embedding-model", "m"]) == 0
    assert capsys.readouterr().out == "tr@v1-knn: gate passed\n"
    assert main(["skills", "train", "tr", "--kind", "contrastive", "--with-real"]) == 0
    assert capsys.readouterr().out == "tr@v1-c: gate passed\n"
    assert calls == [("knn", skill, "m", False), ("contrastive", skill, None, True)]
    assert modules == ["mia.learning.contenders", "mia.learning.contenders"]


def test_train_rejects_an_unknown_kind_and_kind_encoder_trains_the_encoder(
    skill: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(["skills", "train", "tr", "--kind", "svm"])
    capsys.readouterr()
    seen: list[str] = []

    def load(name: str) -> object:
        seen.append(name)
        return SimpleNamespace(train_role=lambda *a, **k: card("v9"))

    monkeypatch.setattr(commands, "import_module", load)
    assert main(["skills", "train", "tr", "--kind", "encoder"]) == 0
    assert capsys.readouterr().out == "tr@v9: gate passed\n"
    assert seen == ["mia.learning.train"]


def test_bakeoff_prints_each_contender_and_the_winner(
    skill: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a = card("v1").model_copy(update={"kind": "encoder"})
    b = card("v1-knn", passed=False).model_copy(update={"kind": "knn"})
    folders: list[Path] = []

    def bakeoff(folder: Path) -> tuple[list[ModelCard], ModelCard | None]:
        folders.append(folder)
        return [a, b], a

    monkeypatch.setattr(commands, "import_module", lambda name: SimpleNamespace(bakeoff=bakeoff))
    assert main(["skills", "bakeoff", "tr"]) == 0
    assert capsys.readouterr().out == (
        "encoder v1: macro F1 1.000, gate passed\n"
        "knn v1-knn: macro F1 1.000, gate failed\n"
        "winner: encoder v1\n"
    )
    assert folders == [skill]
    monkeypatch.setattr(
        commands, "import_module", lambda name: SimpleNamespace(bakeoff=lambda f: ([b], None))
    )
    assert main(["skills", "bakeoff", "tr"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "winner: none"


def test_bakeoff_missing_learning_package_gives_the_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def raiser(name: str) -> object:
        raise ModuleNotFoundError("No module named 'torch'", name="torch")

    monkeypatch.setattr(commands, "import_module", raiser)
    assert main(["skills", "bakeoff", "dispatcher"]) == 2
    assert main(["skills", "train", "dispatcher", "--kind", "knn"]) == 2
    assert capsys.readouterr().out == ("install the learning group: uv sync --group learning\n" * 2)


def _no_import(name: str) -> object:
    raise AssertionError(f"imported {name}")


def test_train_refuses_embedding_model_for_the_encoder(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(commands, "import_module", _no_import)
    assert main(["skills", "train", "tr", "--embedding-model", "m"]) == 1
    assert capsys.readouterr().out == (
        "--embedding-model applies to knn and contrastive; use --base-model for the encoder\n"
    )


@pytest.mark.parametrize("kind", ["knn", "contrastive"])
def test_train_refuses_base_model_for_the_embedding_kinds(
    kind: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(commands, "import_module", _no_import)
    assert main(["skills", "train", "tr", "--kind", kind, "--base-model", "b"]) == 1
    assert capsys.readouterr().out == (
        f"--base-model applies to the encoder kind; use --embedding-model for {kind}\n"
    )


def _dropped_test_fixture(skill: Path) -> None:
    other = rec(9, "what a lovely day", intent="other")
    write_records(skill / "data" / "train.jsonl", [rec(0, "im sick today"), other])
    write_records(
        skill / "data" / "dev.jsonl", [rec(1, "cant come").model_copy(update={"split": "dev"})]
    )
    write_records(
        skill / "data" / "test.jsonl",
        [
            rec(2, "fever, staying home", status="kept").model_copy(update={"split": "test"}),
            rec(3, "x", status="dropped").model_copy(update={"split": "test"}),
        ],
    )


def test_dropped_test_records_are_left_out_of_validate(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reviewer drops a test record in place; the quota check does not count it (the same
    rule split applies to reviewed.jsonl)."""
    _dropped_test_fixture(skill)
    assert main(["skills", "validate", "tr"]) == 0
    assert capsys.readouterr().out.splitlines()[-1].startswith("4 records,")


@pytest.mark.learning
def test_dropped_test_records_are_left_out_of_train(skill: Path) -> None:
    """The evaluation never sees a test record the reviewer dropped (train.py imports torch,
    so this half needs the learning group)."""
    from mia.learning.train import load_splits

    _dropped_test_fixture(skill)
    assert [r.id for r in load_splits(skill, shared=None)[3]] == ["tr/2"]


@pytest.mark.learning
def test_train_takes_the_shared_labels_rows_from_the_evaluation_set(skill: Path) -> None:
    """Conversation rows and other roles' rows (as `other`) join the splits; the role's own
    rows of the evaluation set stay out."""
    from mia.learning.train import load_splits

    _dropped_test_fixture(skill)
    shared = skill / "intents.jsonl"
    rows = [
        {
            "id": "conversation.greeting/en/001",
            "intent": "conversation.greeting",
            "lang": "en",
            "text": "hi there",
            "role": "cleaner",
            "style": "informal",
            "split": "test",
        },
        {
            "id": "sales.new_lead/en/001",
            "intent": "sales.new_lead",
            "lang": "en",
            "text": "a new client called",
            "role": "office",
            "style": "formal",
            "split": "train",
        },
        {
            "id": "tr.a/en/001",
            "intent": "tr.a",
            "lang": "en",
            "text": "mine",
            "role": "cleaner",
            "style": "informal",
            "split": "train",
        },
    ]
    shared.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    _, train, dev, test = load_splits(skill, shared=shared)
    assert [r.id for r in test] == ["tr/2", "conversation.greeting/en/001"]
    assert ("other", "other") in {(r.intent, r.kind) for r in train + dev}
    assert "tr.a/en/001" not in {r.id for r in train + dev + test}
