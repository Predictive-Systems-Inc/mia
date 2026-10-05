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
