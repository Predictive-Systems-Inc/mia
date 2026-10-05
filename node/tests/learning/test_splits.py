import pytest

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


def rec(
    i: int,
    text: str,
    split: str = "train",
    kind: str = "normal",
) -> Record:
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
        kind=kind,  # type: ignore[arg-type]
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


def test_clusters_are_transitive() -> None:
    """Chain: A~B and B~C >= 0.85 means all three must land in same split via union-find."""
    # Use long base text with minor variations to maintain high similarity in chain
    base = (
        "please contact me tomorrow morning about the important meeting with the team "
        "to discuss the project status and timeline for the upcoming release and deployment "
        "schedule and any concerns or issues that need to be addressed in the next quarter "
        "regarding the software development and implementation of new features and updates "
        "that have been requested by the stakeholders and clients"
    )
    a = base
    b = base.replace("morning", "afternoon")  # One word change: A~B
    c = base.replace("team", "group")  # Different word change: B~C

    sim_ab = similarity(a, b)
    sim_bc = similarity(b, c)
    assert sim_ab >= 0.85, f"A~B should be >= 0.85, got {sim_ab}"
    assert sim_bc >= 0.85, f"B~C should be >= 0.85, got {sim_bc}"

    recs = [rec(0, a), rec(1, b), rec(2, c)]
    for seed in [1, 2, 42]:
        out = assign_train_dev(ROLE, recs, seed=seed)
        splits = {r.text: r.split for r in out}
        assert splits[a] == splits[b] == splits[c], (
            f"seed {seed}: A, B, C should be in same split (transitively connected), got {splits}"
        )


def test_dev_quota_counts_only_normal_records() -> None:
    """Negative/injection records still follow their cluster split but don't count toward quota."""
    normal_recs = [rec(i, TEXTS[i], kind="normal") for i in range(6)]
    non_normal_recs = [
        rec(10, "wrong", kind="negative"),
        rec(11, "wrong", kind="injection"),
    ]
    recs = normal_recs + non_normal_recs
    out = assign_train_dev(ROLE, recs, seed=1)
    dev_normal_count = sum(1 for r in out if r.split == "dev" and r.kind == "normal")
    assert dev_normal_count >= 2, f"dev should have >= 2 normal records, got {dev_normal_count}"


def test_unknown_intent_raises_error() -> None:
    """Unknown intent should raise ValueError, not silently fall back."""
    recs = [
        Record(
            id="r/0",
            role="r",
            intent="unknown.intent",
            lang="en",
            text="test",
            counterpart="c",
            style="informal",
            split="train",
            source="t",
        )
    ]
    with pytest.raises(ValueError, match="unknown intent unknown.intent"):
        assign_train_dev(ROLE, recs, seed=1)
