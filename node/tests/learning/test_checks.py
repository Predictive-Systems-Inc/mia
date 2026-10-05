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
