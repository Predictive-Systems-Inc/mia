from mia.learning.checks import similarity
from mia.learning.schema import IntentSpec, Record, RoleSpec, Targets
from mia.learning.splits import assign_train_dev

ROLE = RoleSpec(
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
            counterparts=["c"],
            risk="read",
            label_en="A",
        )
    ],
    targets=Targets(dev=2),
)


def rec(i: int, text: str, split: str = "train") -> Record:
    return Record(
        id=f"r/{i}",
        role="r",
        intent="r.a",
        lang="en",
        text=text,
        counterpart="c",
        style="informal",
        split=split,
        source="t",
    )  # type: ignore[arg-type]


TEXTS = [
    "im sick today",
    "im sick today!",
    "cant come tomorrow",
    "fever, staying home",
    "off work today, unwell",
    "not coming in, flu",
    "home sick",
    "feeling awful, no work",
]


def test_dev_quota_and_test_untouched() -> None:
    recs = [rec(i, t) for i, t in enumerate(TEXTS)] + [rec(99, "sick, sorry", split="test")]
    out = assign_train_dev(ROLE, recs, seed=1)
    assert sum(r.split == "dev" for r in out) >= 2
    assert next(r for r in out if r.id == "r/99").split == "test"


def test_paraphrases_stay_together_and_result_is_stable() -> None:
    recs = [rec(i, t) for i, t in enumerate(TEXTS)]
    a = assign_train_dev(ROLE, recs, seed=1)
    b = assign_train_dev(ROLE, recs, seed=1)
    assert [r.split for r in a] == [r.split for r in b]
    s = {r.text: r.split for r in a}
    assert similarity("im sick today", "im sick today!") >= 0.85
    assert s["im sick today"] == s["im sick today!"]
