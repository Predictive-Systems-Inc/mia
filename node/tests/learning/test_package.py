import os

import pytest
from sqlmodel import Session, select

from mia.core.models import Actor, Event, Person
from mia.learning.package import (
    PromotionRefused,
    active_version,
    package_dir,
    promote,
    read_card,
    write_card,
)
from mia.settings import get_settings
from tests.learning.helpers import card


def test_card_round_trip() -> None:
    write_card(card())
    assert read_card("r", "v1") == card()


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
    write_card(card(version="v1"))
    write_card(card(version="v2"))
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
    write_card(card())
    (get_settings().MIA_MODELS_DIR / "r" / "ACTIVE").mkdir()  # a directory: write_text fails
    with pytest.raises(OSError):
        promote(session, actor, "r", "v1", signed_by="Allan")
    assert session.exec(select(Event).where(Event.action == "skill_model.promoted")).all() == []


def test_failed_replace_keeps_old_active_and_leaves_no_temp_file(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = Actor.person(people["Helena"])
    write_card(card(version="v1"))
    write_card(card(version="v2"))
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
