import numpy as np

from mia.learning.overlap import Item, Thresholds, analyse, render


def unit(*rows: list[float]) -> np.ndarray:
    m = np.array(rows, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def items(*labels: str) -> list[Item]:
    return [Item(id=f"r{i}", intent=label, text=f"text {i}") for i, label in enumerate(labels)]


TH = Thresholds(
    close_pair=0.9,
    paraphrase=0.99,
    cluster=0.9,
    overlap=0.9,
    split=0.5,
    min_cluster=2,
    k=2,
    suspect_share=0.5,
)


def test_close_pair_and_paraphrase() -> None:
    its = items("a", "a", "b", "b")
    emb = unit([1, 0, 0], [1, 0.01, 0], [1, 0.02, 0], [0.99, 0.03, 0])
    rep = analyse(its, emb, TH)
    assert [(p.a, p.b) for p in rep.close_pairs] == [("a", "b")]
    assert {(p.a_intent, p.b_intent) for p in rep.paraphrases} == {("a", "b")}


def test_far_intents_give_nothing() -> None:
    rep = analyse(
        items("a", "a", "b", "b"), unit([1, 0, 0], [1, 0.01, 0], [0, 1, 0], [0, 1, 0.01]), TH
    )
    assert rep.close_pairs == [] and rep.paraphrases == [] and rep.candidates == []


def test_suspect_label() -> None:
    # r2 is labelled a but sits among b records
    its = items("a", "a", "a", "b", "b", "b", "b")
    emb = unit(
        [1, 0, 0],
        [1, 0.01, 0],
        [0, 1, 0.05],
        [0, 1, 0],
        [0, 1, 0.001],
        [0, 1, 0.002],
        [0, 1, 0.003],
    )
    rep = analyse(its, emb, TH)
    assert [(s.id, s.intent, s.neighbours_label) for s in rep.suspects] == [("r2", "a", "b")]
    assert rep.suspects[0].share == 1.0


def test_merge_candidate_when_two_sub_clusters_overlap_other_intents() -> None:
    # intent m has one sub-cluster near x and one near y
    its = items("m", "m", "m", "m", "x", "x", "y", "y")
    emb = unit(
        [1, 0, 0],
        [1, 0.01, 0],
        [0, 1, 0],
        [0, 1, 0.01],
        [1, 0.02, 0],
        [1, 0.03, 0],
        [0, 1, 0.02],
        [0, 1, 0.03],
    )
    rep = analyse(its, emb, TH)
    merge = [c for c in rep.candidates if c.kind == "merge"]
    assert [(c.intent, c.others) for c in merge] == [("m", ["x", "y"])]
    assert len(rep.clusters["m"]) == 2


def test_split_candidate_when_sub_clusters_are_far_and_overlap_nothing() -> None:
    its = items("s", "s", "s", "s", "z", "z")
    emb = unit([1, 0, 0], [1, 0.01, 0], [0, 1, 0], [0, 1, 0.01], [0, 0, 1], [0, 0.01, 1])
    rep = analyse(its, emb, TH)
    assert [(c.intent, c.kind) for c in rep.candidates] == [("s", "split")]


def test_narrow_candidate_when_one_sub_cluster_overlaps_a_tighter_intent() -> None:
    # w is wide (two groups); one group sits on the tight intent n
    its = items("w", "w", "w", "w", "n", "n")
    emb = unit([1, 0, 0], [1, 0.05, 0], [0.6, 0.8, 0], [0.62, 0.78, 0], [1, 0.01, 0], [1, 0.02, 0])
    th = TH.model_copy(update={"split": 0.0})  # the w groups are not far enough to split
    rep = analyse(its, emb, th)
    assert [(c.intent, c.kind, c.others) for c in rep.candidates] == [("w", "narrow", ["n"])]


def test_small_intents_are_one_group_and_tiny_inputs_do_not_crash() -> None:
    rep = analyse(items("a", "b"), unit([1, 0, 0], [0, 1, 0]), TH)
    assert len(rep.clusters["a"]) == 1 and rep.clusters["a"][0].size == 1
    empty = analyse([], np.zeros((0, 3), dtype=np.float32), TH)
    assert empty.close_pairs == [] and empty.clusters == {}
    one = analyse(items("a", "a"), unit([1, 0, 0], [1, 0.01, 0]), TH)
    assert one.close_pairs == [] and one.candidates == []


def test_render_lists_every_section() -> None:
    its = items("m", "m", "m", "m", "x", "x", "y", "y")
    emb = unit(
        [1, 0, 0],
        [1, 0.01, 0],
        [0, 1, 0],
        [0, 1, 0.01],
        [1, 0.02, 0],
        [1, 0.03, 0],
        [0, 1, 0.02],
        [0, 1, 0.03],
    )
    text = render(analyse(its, emb, TH))
    for heading in (
        "## Close intents",
        "## Suspect labels",
        "## Paraphrases across intents",
        "## Candidates",
    ):
        assert heading in text
    assert "| m | merge | x, y |" in text
