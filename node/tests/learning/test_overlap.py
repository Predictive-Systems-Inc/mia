import numpy as np

from mia.learning.overlap import (
    Item,
    Thresholds,
    analyse,
    calibrate,
    found_pairs,
    recall,
    render,
    review_pairs,
    unfindable,
)


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


def test_dense_intent_does_not_recurse_and_is_one_group() -> None:
    n = 1500
    emb = unit(*[[1, i * 1e-6, 0] for i in range(n)])
    rep = analyse(items(*["a"] * n), emb, TH)
    assert [s.size for s in rep.clusters["a"]] == [n]


def test_suspect_tie_between_own_and_other_label_is_not_flagged() -> None:
    # arc at 0, 10, 20, 30 degrees; every record has one a and one b among its 2 neighbours
    angles = np.radians([0, 10, 20, 30])
    emb = unit(*[[float(np.cos(t)), float(np.sin(t)), 0.0] for t in angles])
    its = items("a", "a", "b", "b")
    assert analyse(its, emb, TH.model_copy(update={"suspect_share": 0.5})).suspects == []


def test_close_pair_and_paraphrase_thresholds_are_inclusive() -> None:
    th = TH.model_copy(update={"close_pair": 0.0, "paraphrase": 0.0})
    at = analyse(items("a", "b"), unit([1, 0], [0, 1]), th)  # cosine exactly 0.0
    assert len(at.close_pairs) == 1 and len(at.paraphrases) == 1
    past = analyse(items("a", "b"), unit([1, 0], [-0.01, 1]), th)  # cosine just below 0.0
    assert past.close_pairs == [] and past.paraphrases == []


def test_small_groups_fold_into_the_main_group() -> None:
    emb = unit([1, 0], [1, 0.01], [1, 0.02], [0, 1])
    th = TH.model_copy(update={"min_cluster": 3})
    assert [s.size for s in analyse(items("a", "a", "a", "a"), emb, th).clusters["a"]] == [4]
    th1 = TH.model_copy(update={"min_cluster": 1})
    assert [s.size for s in analyse(items("a", "a", "a", "a"), emb, th1).clusters["a"]] == [3, 1]


def test_no_narrow_when_the_other_intent_is_wider() -> None:
    # w has two close groups (tight overall); n is wide and sits on one of them
    w = [[1, 0.01, 0], [1, 0.02, 0], [0.866, 0.5, 0], [0.866, 0.51, 0]]
    n = [[1, 0.5, 0], [1, -0.5, 0], [1, 0, 0.5], [1, 0, -0.5]]
    th = TH.model_copy(update={"cluster": 0.99})
    rep = analyse(items(*["w"] * 4, *["n"] * 4), unit(*w, *n), th)
    assert [len(rep.clusters["w"]), len(rep.clusters["n"])] == [2, 1]
    assert rep.candidates == []  # one hit: neither merge nor narrow


def test_split_is_skipped_when_a_sub_cluster_overlaps_another_intent() -> None:
    # same data as the narrow case; groups are far enough to split if that branch were reached
    its = items("w", "w", "w", "w", "n", "n")
    emb = unit([1, 0, 0], [1, 0.05, 0], [0.6, 0.8, 0], [0.62, 0.78, 0], [1, 0.01, 0], [1, 0.02, 0])
    th = TH.model_copy(update={"split": 0.9})
    assert [(c.intent, c.kind) for c in analyse(its, emb, th).candidates] == [("w", "narrow")]


def test_merge_when_two_sub_clusters_overlap_the_same_intent() -> None:
    a, b = np.radians(20), np.radians(-20)
    m = [[np.cos(a), np.sin(a), 0], [np.cos(a), np.sin(a) + 0.01, 0]]
    m += [[np.cos(b), np.sin(b), 0], [np.cos(b), np.sin(b) - 0.01, 0]]
    th = TH.model_copy(update={"cluster": 0.99})
    rep = analyse(items(*["m"] * 4, "x", "x"), unit(*m, [1, 0, 0], [1, 0.001, 0]), th)
    assert [(c.intent, c.kind, c.others) for c in rep.candidates] == [("m", "merge", ["x"])]


def test_paraphrases_are_sorted_and_capped_with_total_shown() -> None:
    n = 201
    # n records of a and n of b, all identical in pairs: n * n cross pairs
    emb = unit(*[[1, 0, 0]] * (2 * n))
    rep = analyse(items(*["a"] * n, *["b"] * n), emb, TH)
    assert rep.paraphrase_total == n * n and len(rep.paraphrases) == 200
    assert "Showing 200 of 40401." in render(rep)


REVIEW = """# Intent overlap review

## Decisions

| Pair | Decision | Rule | Records moved |
| --- | --- | --- | --- |
| hr.payday / conversation.kb_payday | removed | 1 | 23 |
| sales.price_question / kb_prices | removed | 1 | 20 |
| client_service.update_contact / admin.update_client / bookkeeper.billing_details | one | 3 | 38 |
| client_service.service_faq / kb_services, kb_pets | removed | 1 | 5 |
| conversation.kb_cleaning_howto / kb_surface_care (no dilution records) | narrower | n | 9 |
| **hr.x** / **kb_y** | bold | 1 | 1 |

## Removed records
| id | text |
| --- | --- |
| x/en/1 | not a pair |
"""


def test_review_pairs_parses_the_decisions_table() -> None:
    assert review_pairs(REVIEW) == {
        frozenset({"hr.payday", "conversation.kb_payday"}),
        frozenset({"sales.price_question", "conversation.kb_prices"}),
        frozenset({"client_service.update_contact", "admin.update_client"}),
        frozenset({"client_service.update_contact", "bookkeeper.billing_details"}),
        frozenset({"admin.update_client", "bookkeeper.billing_details"}),
        frozenset({"client_service.service_faq", "conversation.kb_services"}),
        frozenset({"client_service.service_faq", "conversation.kb_pets"}),
        frozenset({"conversation.kb_cleaning_howto", "conversation.kb_surface_care"}),
        frozenset({"hr.x", "conversation.kb_y"}),
    }


def test_recall_counts_pairs_found_by_any_signal() -> None:
    its = items("a", "a", "b", "b", "c", "c")
    emb = unit([1, 0, 0], [1, 0.01, 0], [1, 0.02, 0], [0.99, 0.03, 0], [0, 0, 1], [0, 0.01, 1])
    rep = analyse(its, emb, TH)
    assert found_pairs(rep) >= {frozenset({"a", "b"})}
    assert recall(rep, {frozenset({"a", "b"}), frozenset({"a", "c"})}) == 0.5
    assert recall(rep, set()) == 1.0


def test_calibrate_picks_thresholds_within_the_flag_budget() -> None:
    its = items("a", "a", "b", "b", "c", "c")
    emb = unit([1, 0, 0], [1, 0.01, 0], [0.9, 0.44, 0], [0.88, 0.47, 0], [0, 0, 1], [0, 0.01, 1])
    th, r = calibrate(its, emb, {frozenset({"a", "b"})}, budget=1.0)
    assert r == 1.0
    rep = analyse(its, emb, th)
    assert len(found_pairs(rep)) <= 1


def test_calibrate_falls_back_when_nothing_fits_the_budget() -> None:
    # three near-identical intents: every grid point flags 3 pairs, the limit is 1
    th, r = calibrate(
        items("a", "b", "c"),
        unit([1, 0, 0], [1, 0.01, 0], [1, 0.02, 0]),
        {frozenset({"a", "b"})},
        budget=1.0,
    )
    assert (th, r) == (Thresholds(), 0.0)


def test_found_pairs_counts_paraphrase_pairs_beyond_the_display_cap() -> None:
    its = items(*["a"] * 15, *["b"] * 15, "c")
    rows = [[1, 0, 0]] * 30 + [[0.99, 0.14, 0]]
    rep = analyse(its, unit(*rows))
    assert len(rep.paraphrases) == 200
    assert rep.paraphrase_total == 225 + 30
    assert {frozenset({"a", "c"}), frozenset({"b", "c"}), frozenset({"a", "b"})} <= found_pairs(rep)
    assert {tuple(p) for p in rep.paraphrase_intent_pairs} == {("a", "b"), ("a", "c"), ("b", "c")}


def test_unfindable_names_pairs_with_an_intent_without_items() -> None:
    ab, ax, xy = (frozenset(p) for p in ({"a", "b"}, {"a", "x"}, {"x", "y"}))
    assert unfindable({ab, ax, xy}, {"a", "b"}) == {ax, xy}
    assert unfindable({ab}, {"a", "b"}) == set()
