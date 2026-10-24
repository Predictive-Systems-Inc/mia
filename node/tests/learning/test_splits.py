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


def test_clusters_are_transitive(monkeypatch) -> None:
    """Union-find (not greedy) ensures transitive closure in similarity graphs.

    Creates an artificial similarity graph where:
    - a~b (sim=1.0)
    - b~c (sim=1.0)
    - a!~c (sim=0.0)

    Old greedy code processes [a, c, b] (sorted by id) and creates [[a,b], [c]].
    New union-find code correctly groups all three: [[a,b,c]].
    """

    # Monkeypatch similarity to control the graph structure
    def fake_similarity(text_a: str, text_b: str) -> float:
        # Pairs that match: (a,b) and (b,c) both have sim=1.0
        # Pair that doesn't: (a,c) has sim=0.0
        pair = tuple(sorted([text_a, text_b]))
        if pair in [("a", "b"), ("b", "c")]:
            return 1.0
        return 0.0

    monkeypatch.setattr("mia.learning.splits.similarity", fake_similarity)

    # Create records: a, c, b (sorted by id so a is first, c second, b third)
    recs = [
        rec(1, "a"),  # r/1
        rec(2, "c"),  # r/2
        rec(3, "b"),  # r/3
        rec(10, TEXTS[0]),  # unrelated records to set up dev quota
        rec(11, TEXTS[1]),
        rec(12, TEXTS[2]),
    ]

    # Direct test of _clusters: old code creates 2 clusters, new code creates 1
    from mia.learning.splits import _clusters

    clusters = _clusters(recs[:3])  # [a, c, b] in sorted order
    cluster_ids = [[r.id for r in c] for c in clusters]
    # With union-find, all three should be in one cluster
    assert len(clusters) == 1, (
        f"union-find should create 1 cluster, got {len(clusters)}: {cluster_ids}"
    )
    assert {r.id for r in clusters[0]} == {"r/1", "r/2", "r/3"}, (
        f"cluster should contain all three records, got {cluster_ids}"
    )

    # Test via assign_train_dev: a, b, c should stay together across seeds
    for seed in [1, 42]:
        out = assign_train_dev(ROLE, recs, seed=seed)
        splits = {r.id: r.split for r in out}
        assert splits["r/1"] == splits["r/2"] == splits["r/3"], (
            f"seed {seed}: a, b, c should be in same split (transitive), got {splits}"
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


def test_shared_labels_split_with_the_light_quota() -> None:
    """`other` and conversation.* records have no IntentSpec in the role; they still split."""
    recs = [rec(i, t) for i, t in enumerate(TEXTS)]
    shared = [
        rec(100 + i, f"hello there {i}").model_copy(update={"intent": "conversation.greeting"})
        for i in range(4)
    ] + [rec(200 + i, f"weather chat {i}").model_copy(update={"intent": "other"}) for i in range(4)]
    out = assign_train_dev(ROLE, recs + shared, seed=1)
    for intent in ("conversation.greeting", "other"):
        assert sum(r.intent == intent and r.split == "dev" for r in out) == ROLE.targets.dev


def test_other_records_carry_kind_other_and_still_fill_only_the_dev_quota() -> None:
    """The generator writes `other` records with kind "other"; they are that label's normal
    examples, so dev takes its quota of them and the rest train (not all of them in dev)."""
    recs = [rec(i, t) for i, t in enumerate(TEXTS)]
    others = [
        rec(200 + i, f"weather chat {i}", kind="other").model_copy(update={"intent": "other"})
        for i in range(6)
    ]
    out = assign_train_dev(ROLE, recs + others, seed=1)
    assert sum(r.intent == "other" and r.split == "dev" for r in out) == ROLE.targets.dev
    assert sum(r.intent == "other" and r.split == "train" for r in out) == 4
