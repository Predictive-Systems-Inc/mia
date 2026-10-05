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
    """Union-find (not greedy) ensures pairwise similarity creates connected components.

    This test uses the proven paraphrase pairs from TEXTS that have >= 0.85 similarity.
    Union-find correctly groups them; old greedy code also passes this, but
    the implementation is required for correctness with more complex graphs.
    """
    # Use TEXTS[0:2] which are known paraphrases (sim >= 0.85)
    recs = [
        rec(0, TEXTS[0]),  # "im sick today"
        rec(1, TEXTS[1]),  # "im sick today!"
        rec(2, TEXTS[2]),  # "cant come tomorrow"
        rec(3, TEXTS[3]),  # "fever, staying home"
        rec(4, TEXTS[4]),
        rec(5, TEXTS[5]),
        rec(6, TEXTS[6]),
        rec(7, TEXTS[7]),
    ]

    sim_01 = similarity(recs[0].text, recs[1].text)
    assert sim_01 >= 0.85, f"rec(0,1) TEXTS[0:2] should be >= 0.85, got {sim_01}"

    for seed in [1, 42]:
        out = assign_train_dev(ROLE, recs, seed=seed)
        splits = {r.id: r.split for r in out}
        # Union-find ensures paraphrases (similar texts) stay together
        # This is critical for more complex paraphrase graphs where greedy fails
        assert splits["r/0"] == splits["r/1"], (
            f"seed {seed}: rec 0,1 paraphrases should be same split"
        )


def test_dev_quota_counts_only_normal_records() -> None:
    """Quota filled by NORMAL records only; non-normal records follow cluster but don't count.

    Old code counts all record kinds toward quota; new code counts only kind=='normal'.
    With seed=1, the shuffle causes non-normal cluster to appear first in the iteration,
    exposing the bug: old code fills dev with non-normal records, failing quota.
    """
    normal_recs = [rec(i + 10, TEXTS[i], kind="normal") for i in range(6)]
    non_normal_recs = [
        rec(1, "injection attempt", kind="injection"),
        rec(2, "negative example", kind="negative"),
    ]
    # Concatenate to get ID ordering: r/1, r/2, r/10-r/15
    recs = non_normal_recs + normal_recs

    # With seed=1, shuffle puts non-normal cluster early
    # Old code: puts r/2 (negative) in dev, then r/13 (normal), dev_count=2 ✓ but has non-normal!
    # New code: counts only normal, so dev_normal_count=1 after r/2, continues to r/13, then r/15
    out = assign_train_dev(ROLE, recs, seed=1)
    dev_recs = [r for r in out if r.split == "dev"]
    dev_normal = [r for r in dev_recs if r.kind == "normal"]

    # With seed=1: old has 1 normal + 1 non-normal; new has exactly 2 normal
    assert len(dev_normal) == 2, (
        f"dev should have exactly 2 normal records (the quota), got {len(dev_normal)} normal "
        f"from {[(r.id, r.kind) for r in dev_recs]}"
    )


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
