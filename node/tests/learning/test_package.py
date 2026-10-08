import os

import pytest
from sqlmodel import Session, select

from mia.core.models import Actor, Event, Person
from mia.learning.package import (
    ARTIFACTS,
    ModelCard,
    PromotionRefused,
    _atomic_write,
    active_version,
    package_dir,
    promote,
    read_card,
    write_card,
)
from mia.settings import get_settings
from tests.learning.helpers import card, write_package


def test_card_round_trip() -> None:
    write_card(card())
    assert read_card("r", "v1") == card()
    assert read_card("r", "v1").with_real is False
    write_card(card().model_copy(update={"with_real": True}))
    assert read_card("r", "v1").with_real is True


def test_promote_refuses_failed_gate_and_missing_signature(
    session: Session, people: dict[str, Person]
) -> None:
    actor = Actor.person(people["Helena"])
    write_card(card(passed=False))
    with pytest.raises(PromotionRefused, match="gate"):
        promote(session, actor, "r", "v1", signed_by="Allan")
    write_card(card(passed=True))
    with pytest.raises(PromotionRefused, match="sign"):
        promote(session, actor, "r", "v1", signed_by="")
    with pytest.raises(PromotionRefused, match="sign"):
        promote(session, actor, "r", "v1", signed_by="   ")
    assert active_version("r") is None
    assert session.exec(select(Event).where(Event.action == "skill_model.promoted")).all() == []


def test_promote_missing_card_is_refused(session: Session, people: dict[str, Person]) -> None:
    actor = Actor.person(people["Helena"])
    with pytest.raises(PromotionRefused) as err:
        promote(session, actor, "r", "v9", signed_by="Allan")
    assert str(err.value) == "r@v9 not found"


def test_promote_corrupt_card_is_refused_and_does_not_activate(
    session: Session, people: dict[str, Person]
) -> None:
    actor = Actor.person(people["Helena"])
    write_card(card())
    (package_dir("r", "v1") / "card.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PromotionRefused, match=r"^r@v1 card is unreadable: "):
        promote(session, actor, "r", "v1", signed_by="Allan")
    assert active_version("r") is None
    assert session.exec(select(Event).where(Event.action == "skill_model.promoted")).all() == []


def test_active_version_empty_marker_is_none() -> None:
    marker = get_settings().MIA_MODELS_DIR / "r" / "ACTIVE"
    marker.parent.mkdir(parents=True)
    marker.write_text("  \n", encoding="utf-8")
    assert active_version("r") is None


def test_promote_marks_active_keeps_previous_and_emits_event(
    session: Session, people: dict[str, Person]
) -> None:
    actor = Actor.person(people["Helena"])
    write_package(card(version="v1"))
    write_package(card(version="v2"))
    promote(session, actor, "r", "v1", signed_by="Allan")
    promote(session, actor, "r", "v2", signed_by="Allan")
    assert active_version("r") == "v2"
    assert read_card("r", "v1").signed_by == "Allan"  # kept for rollback
    assert read_card("r", "v2").signed_at is not None
    events = session.exec(select(Event).where(Event.action == "skill_model.promoted")).all()
    assert [e.entity_id for e in events] == ["r@v1", "r@v2"]
    assert events[1].before == {"active": "v1"}
    assert events[1].after == {"active": "v2", "signed_by": "Allan"}


def test_promote_does_not_emit_when_marker_write_fails(
    session: Session, people: dict[str, Person]
) -> None:
    actor = Actor.person(people["Helena"])
    write_package(card())
    (get_settings().MIA_MODELS_DIR / "r" / "ACTIVE").mkdir()  # a directory: write_text fails
    with pytest.raises(OSError):
        promote(session, actor, "r", "v1", signed_by="Allan")
    assert session.exec(select(Event).where(Event.action == "skill_model.promoted")).all() == []


def test_failed_replace_keeps_old_active_and_leaves_no_temp_file(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = Actor.person(people["Helena"])
    write_package(card(version="v1"))
    write_package(card(version="v2"))
    promote(session, actor, "r", "v1", signed_by="Allan")
    real_replace = os.replace

    def fail_on_marker(src: str, dst: object) -> None:
        if str(dst).endswith("ACTIVE"):
            raise OSError("boom")
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", fail_on_marker)
    with pytest.raises(OSError, match="boom"):
        promote(session, actor, "r", "v2", signed_by="Allan")
    marker = get_settings().MIA_MODELS_DIR / "r" / "ACTIVE"
    assert marker.read_text("utf-8") == "v1"
    assert sorted(p.name for p in marker.parent.iterdir()) == ["ACTIVE", "v1", "v2"]
    assert len(session.exec(select(Event).where(Event.action == "skill_model.promoted")).all()) == 1


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        ("model.onnx", "model.onnx: sha256 does not match card artifacts"),
        ("tokenizer.json", "tokenizer.json: sha256 does not match card artifacts"),
        ("-model.onnx", "model.onnx: file is missing"),
        ("-tokenizer.json", "tokenizer.json: file is missing"),
        ("/model.onnx", "model.onnx: file is unreadable (IsADirectoryError)"),
    ],
)
def test_promote_refuses_missing_or_corrupt_artifacts(
    session: Session, people: dict[str, Person], damage: str, reason: str
) -> None:
    actor = Actor.person(people["Helena"])
    write_package(card(version="v1"))
    promote(session, actor, "r", "v1", signed_by="Allan")
    write_package(card(version="v2"))
    target = package_dir("r", "v2") / damage.lstrip("-/")
    if damage.startswith("-"):
        target.unlink()
    elif damage.startswith("/"):
        target.unlink()
        target.mkdir()
    else:
        target.write_bytes(b"wrong bytes")
    with pytest.raises(PromotionRefused) as err:
        promote(session, actor, "r", "v2", signed_by="Allan")
    assert str(err.value) == f"r@v2 cannot be loaded: {reason}"
    assert active_version("r") == "v1"
    assert read_card("r", "v2").signed_by is None  # refused before any write
    assert len(session.exec(select(Event).where(Event.action == "skill_model.promoted")).all()) == 1


def test_promote_refuses_a_card_without_digests(
    session: Session, people: dict[str, Person]
) -> None:
    write_card(card())
    with pytest.raises(PromotionRefused) as err:
        promote(session, Actor.person(people["Helena"]), "r", "v1", signed_by="Allan")
    assert str(err.value) == "r@v1 cannot be loaded: model.onnx: no sha256 in card artifacts"
    assert active_version("r") is None


def test_atomic_write_removes_the_temp_file_when_the_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = get_settings().MIA_MODELS_DIR / "r"

    def fail(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="disk full"):
        _atomic_write(folder / "ACTIVE", "v1")
    assert list(folder.iterdir()) == []


def test_cards_without_kind_load_as_encoder_packages() -> None:
    raw = card().model_dump()
    raw.pop("kind")
    raw.pop("prefix")
    raw.pop("with_real")
    loaded = ModelCard.model_validate(raw)
    assert loaded.kind == "encoder" and loaded.prefix == "" and loaded.with_real is False


def test_artifact_lists_per_kind() -> None:
    assert ARTIFACTS["encoder"] == ("model.onnx", "tokenizer.json")
    assert ARTIFACTS["contrastive"] == ("model.onnx", "tokenizer.json")
    assert ARTIFACTS["knn"] == ("model.onnx", "tokenizer.json", "examples.npy", "examples.json")


def test_knn_packages_need_their_example_files(session: Session, people: dict[str, Person]) -> None:
    c = card(version="v1").model_copy(update={"kind": "knn"})
    write_package(c)  # writes only model.onnx and tokenizer.json with digests
    with pytest.raises(PromotionRefused) as err:
        promote(session, Actor.person(people["Helena"]), "r", "v1", signed_by="Allan")
    assert str(err.value) == "r@v1 cannot be loaded: examples.npy: no sha256 in card artifacts"
