import random

from mia.learning.pairs import triplets


def test_triplets_pair_same_label_and_a_different_negative() -> None:
    by_label = {"a": ["a1", "a2", "a3"], "b": ["b1", "b2"], "c": ["c1"]}
    out = triplets(by_label, 50, random.Random(0))
    assert len(out) == 50
    owner = {t: k for k, ts in by_label.items() for t in ts}
    for anchor, pos, neg in out:
        assert anchor != pos and owner[anchor] == owner[pos] != owner[neg]
        assert owner[anchor] != "c"  # a label with one example cannot anchor


def test_triplets_need_two_labels_and_one_with_two_examples() -> None:
    assert triplets({"a": ["a1", "a2"]}, 5, random.Random(0)) == []
    assert triplets({"a": ["a1"], "b": ["b1"]}, 5, random.Random(0)) == []
