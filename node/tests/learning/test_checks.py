from mia.learning.checks import check_records, normalize, similarity
from mia.learning.schema import IntentSpec, Record, RoleSpec, Targets


def role(train: int = 2, dev: int = 1, test: int = 1) -> RoleSpec:
    return RoleSpec(
        id="r",
        job_summary="j",
        responsibilities=["x"],
        counterparts=[],
        languages=["en"],
        countries=["FI"],
        styles={"informal": 1.0},
        intents=[
            IntentSpec(
                id="r.a",
                description="d",
                counterparts=["cleaner"],
                risk="read",
                label_en="A",
            )
        ],
        targets=Targets(train_min=train, dev=dev, test=test),
    )


def rec(i: int, text: str, split: str, intent: str = "r.a", kind: str = "normal") -> Record:
    return Record(
        id=f"r/{i}",
        role="r",
        intent=intent,
        lang="en",
        text=text,
        counterpart="cleaner",
        style="informal",
        split=split,
        source="teacher:t",
        kind=kind,  # type: ignore[arg-type]
    )


def test_normalize_and_similarity() -> None:
    assert normalize("  Hi!!  I'm SICK ") == "hi im sick"
    assert similarity("im sick today", "im sick today!") > 0.85
    assert similarity("im sick today", "show my shifts") < 0.3


def test_clean_dataset_passes() -> None:
    recs = [
        rec(1, "im sick today", "train"),
        rec(2, "cant come in tomorrow", "train"),
        rec(3, "running a fever, staying home", "dev"),
        rec(4, "not feeling well, off today", "test"),
        rec(5, "what time does the store open", "train", intent="other", kind="other"),
    ]
    report = check_records(role(), recs, conversation=[])
    assert report.ok, report.errors


def test_unknown_label_is_an_error() -> None:
    report = check_records(role(), [rec(1, "hello", "train", intent="r.zzz")], conversation=[])
    assert any("unknown intent r.zzz" in e for e in report.errors)


def test_paraphrase_across_splits_is_leakage() -> None:
    recs = [rec(1, "im sick today", "train"), rec(2, "im sick today!", "test")]
    report = check_records(role(train=1, dev=0, test=1), recs, conversation=[])
    assert any("leakage" in e for e in report.errors)


def test_missing_quota_is_an_error() -> None:
    report = check_records(role(train=5), [rec(1, "im sick", "train")], conversation=[])
    assert any("r.a/en train 1 < 5" in e for e in report.errors)


def test_duplicate_ids_are_an_error() -> None:
    recs = [rec(1, "im sick today", "train"), rec(1, "cant come", "train")]
    report = check_records(role(train=1, dev=0, test=0), recs, conversation=[])
    assert any("duplicate id r/1" in e for e in report.errors)


def test_unknown_negative_of_is_an_error() -> None:
    r = rec(1, "im sick today", "train").model_copy(update={"negative_of": "r.zzz"})
    report = check_records(role(train=1, dev=0, test=0), [r], conversation=[])
    assert "unknown negative_of r.zzz in r/1" in report.errors


def test_language_mismatch_is_a_warning() -> None:
    r = rec(1, "olen sairas tänään enkä pääse huomenna", "train")
    report = check_records(role(train=1, dev=0, test=0), [r], conversation=[])
    assert f"r/1 may not be en: {r.text!r}" in report.warnings
    assert not [e for e in report.errors if "r/1" in e]


def mix(negative: int, other: int, injection: int, safety: int = 1, total: int = 100) -> list[str]:
    """Warnings for a dataset of `total` records with the given kind counts (rest normal)."""
    kinds = ["negative"] * negative + ["other"] * other + ["injection"] * injection
    kinds += ["safety"] * safety
    kinds += ["normal"] * (total - len(kinds))
    recs = [
        rec(i, f"m{i}", "train", intent="other" if k in ("other", "injection") else "r.a", kind=k)
        for i, k in enumerate(kinds)
    ]
    return check_records(role(train=0, dev=0, test=0), recs, conversation=[]).warnings


def test_mix_at_each_boundary_gives_no_warning() -> None:
    assert mix(negative=15, other=4, injection=1) == []  # other and injection 5%
    assert mix(negative=15, other=11, injection=1) == []  # other and injection 12%


def test_mix_just_past_each_boundary_warns() -> None:
    assert mix(negative=14, other=6, injection=1) == ["hard negatives 14% < 15%"]
    assert mix(negative=15, other=3, injection=1) == ["other and injection 4% outside 5 to 12%"]
    assert mix(negative=15, other=12, injection=1) == ["other and injection 13% outside 5 to 12%"]
    # injection 1/101, just under 1%
    assert mix(negative=16, other=6, injection=1, total=101) == ["injection attempts under 1%"]
    assert mix(negative=15, other=6, injection=0) == ["injection attempts under 1%"]


def test_no_safety_records_warns() -> None:
    assert mix(negative=15, other=6, injection=1, safety=0) == ["no safety records"]


def test_no_other_records_is_an_error() -> None:
    recs = [rec(1, "im sick today", "train")]
    report = check_records(role(train=1, dev=0, test=0), recs, conversation=[])
    assert report.errors == ["no records labelled other"]


def test_same_text_with_two_intents_is_an_error() -> None:
    r = role(train=0, dev=0, test=0)
    r.intents.append(r.intents[0].model_copy(update={"id": "r.b"}))
    recs = [
        rec(1, "Is it ok to mix bleach?", "train"),
        rec(2, "is it ok to mix bleach", "test", intent="r.b"),
        rec(3, "other text", "dev", intent="other", kind="other"),
    ]
    report = check_records(r, recs, conversation=[])
    assert "same text with two intents: 'is it ok to mix bleach' (r.a, r.b)" in report.errors


def test_same_text_with_the_same_intent_is_not_an_error() -> None:
    recs = [rec(1, "im sick", "train"), rec(2, "Im sick!", "test")]
    report = check_records(role(train=0, dev=0, test=0), recs, conversation=[])
    assert not [e for e in report.errors if "two intents" in e]


def test_two_intent_errors_list_at_most_five_examples() -> None:
    r = role(train=0, dev=0, test=0)
    r.intents.append(r.intents[0].model_copy(update={"id": "r.b"}))
    recs = [rec(i, f"text {i}", "train") for i in range(7)]
    recs += [rec(10 + i, f"text {i}", "train", intent="r.b") for i in range(7)]
    report = check_records(r, recs, conversation=[])
    assert len([e for e in report.errors if "two intents" in e]) == 5


def _shadow(intent_id: str) -> list[str]:
    r = role(train=0, dev=0, test=0)
    r.intents[0] = r.intents[0].model_copy(update={"id": intent_id})
    conv = ["conversation.emergency", "conversation.kb_payday", "conversation.greeting"]
    return check_records(r, [], conversation=conv).errors


def test_role_intent_shadowing_a_conversation_suffix_is_an_error() -> None:
    assert "role intent site_manager.emergency duplicates conversation.emergency" in _shadow(
        "site_manager.emergency"
    )


def test_role_intent_matching_kb_suffix_is_an_error() -> None:
    assert "role intent hr.payday duplicates conversation.kb_payday" in _shadow("hr.payday")


def test_role_intent_without_a_matching_suffix_is_not_an_error() -> None:
    assert not [e for e in _shadow("dispatcher.report_absence") if "duplicates" in e]


def test_record_equal_to_a_conversation_example_is_a_warning() -> None:
    recs = [rec(1, "Good morning, Mia!", "train")]
    report = check_records(
        role(train=0, dev=0, test=0), recs, [], conversation_examples=["good morning mia"]
    )
    assert "r/1 equals a conversation.yaml example: 'Good morning, Mia!'" in report.warnings
