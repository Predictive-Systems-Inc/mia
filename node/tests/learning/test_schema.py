import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mia.learning import catalogue
from mia.learning.schema import (
    IntentSpec,
    Record,
    Targets,
    load_records,
    load_role,
    write_records,
)

ROLE_YAML = """
id: dispatcher
job_summary: Keeps every visit staffed.
responsibilities: [record absences, find cover]
counterparts:
  - {role: cleaner, share: 0.8, channel: whatsapp}
  - {role: supervisor, share: 0.2, channel: web}
languages: [en, fi, fil]
countries: [FI]
styles: {informal: 0.3, terse: 0.15, typo: 0.15, indirect: 0.15, formal: 0.1, mixed: 0.1, context: 0.05}
intents:
  - id: dispatcher.report_absence
    description: Cannot work (sick, late, leaving early)
    counterparts: [cleaner]
    risk: write
    label_en: Report I'm sick
    slots: [reason, partial_day]
    handler: agent
    volume: high
  - id: dispatcher.my_visits
    description: Asks about own visits
    counterparts: [cleaner]
    risk: read
    label_en: Show my shifts
    handler: agent
"""


def test_role_loads_and_label_space(tmp_path: Path) -> None:
    path = tmp_path / "role.yaml"
    path.write_text(ROLE_YAML)
    role = load_role(path)
    assert role.intent("dispatcher.report_absence") is not None
    labels = role.label_space(["conversation.greeting"])
    assert labels == [
        "dispatcher.report_absence",
        "dispatcher.my_visits",
        "conversation.greeting",
        "other",
    ]


def test_quota_follows_volume_and_follow_up() -> None:
    t = Targets()
    high = IntentSpec(
        id="a.b",
        description="d",
        counterparts=["cleaner"],
        risk="write",
        label_en="x",
        volume="high",
    )
    normal = IntentSpec(
        id="a.c", description="d", counterparts=["cleaner"], risk="read", label_en="y"
    )
    follow = IntentSpec(
        id="a.d",
        description="d",
        counterparts=["cleaner"],
        risk="write",
        label_en="z",
        follow_up=True,
    )
    assert (t.quota(high, "train"), t.quota(high, "dev"), t.quota(high, "test")) == (100, 15, 30)
    assert (t.quota(normal, "train"), t.quota(normal, "dev"), t.quota(normal, "test")) == (
        30,
        10,
        20,
    )
    assert (t.quota(follow, "train"), t.quota(follow, "test")) == (60, 30)


def test_label_en_is_short() -> None:
    with pytest.raises(ValidationError):
        IntentSpec(id="a.b", description="d", counterparts=["c"], risk="read", label_en="x" * 21)


def test_tool_handler_needs_a_tool() -> None:
    with pytest.raises(ValidationError):
        IntentSpec(
            id="a.b",
            description="d",
            counterparts=["c"],
            risk="write",
            label_en="x",
            handler="tool",
        )


def test_records_round_trip_and_reject_unknown_fields(tmp_path: Path) -> None:
    rec = Record(
        id="dispatcher.report_absence/en/001",
        role="dispatcher",
        intent="dispatcher.report_absence",
        lang="en",
        text="sick today",
        counterpart="cleaner",
        style="terse",
        split="train",
        source="teacher:sonnet-5.5",
    )
    path = tmp_path / "train.jsonl"
    write_records(path, [rec])
    assert load_records(path) == [rec]
    bad = json.loads(path.read_text())
    bad["surprise"] = 1
    path.write_text(json.dumps(bad) + "\n")
    with pytest.raises(ValidationError):
        load_records(path)


def test_conversation_catalogue_has_safety_intents() -> None:
    ids = {c.id for c in catalogue.conversation_intents()}
    assert "conversation.greeting" in ids
    assert catalogue.safety_ids() and catalogue.safety_ids() <= ids
    # D31: 93 to 87 after five merges; distress runs the emergency script
    assert len(ids) == 87
    assert catalogue.safety_ids() == {
        "conversation.emergency",
        "conversation.chemical_exposure",
        "conversation.distress",
    }
