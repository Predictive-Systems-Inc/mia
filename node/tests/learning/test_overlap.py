import numpy as np
import pytest

from mia.learning.overlap import (
    Item,
    Thresholds,
    analyse,
    centre,
    found_pairs,
    recall,
    recall_at,
    render,
    review_pairs,
    unfindable,
)


def unit(*rows: list[float]) -> np.ndarray:
    m = np.array(rows, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def items(*labels: str) -> list[Item]:
    return [Item(id=f"r{i}", intent=label, text=f"text {i}") for i, label in enumerate(labels)]


def deg(d: float) -> list[float]:
    return [float(np.cos(np.radians(d))), float(np.sin(np.radians(d))), 0.0]


TH = Thresholds(paraphrase=0.99, min_cluster=2, k=2, suspect_share=0.5)


def test_centre_separates_rows_that_share_an_offset() -> None:
    emb = unit([5, 1, 0], [5, -1, 0], [5, 0, 1], [5, 0, -1])
    assert float(emb[0] @ emb[1]) == pytest.approx(24 / 26, abs=1e-6)  # 0.923, above 0.9
    c = centre(emb)
    assert c == pytest.approx(np.array([[0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]), abs=1e-6)
    assert float(c[0] @ c[1]) == pytest.approx(-1.0, abs=1e-6)  # below 0.5
    raw = analyse(items("a", "b", "c", "d"), emb, TH, centred=False)
    assert [(p.a, p.b, p.similarity) for p in raw.ranked][-2:] == [
        ("a", "b", 0.923),
        ("c", "d", 0.923),
    ]
    centred = analyse(items("a", "b", "c", "d"), emb, TH)
    assert [(p.a, p.b, p.similarity) for p in centred.ranked][-2:] == [
        ("a", "b", -1.0),
        ("c", "d", -1.0),
    ]


def test_centre_keeps_zero_rows_and_empty_input() -> None:
    assert centre(unit([1, 2, 3])).tolist() == [[0.0, 0.0, 0.0]]
    assert centre(np.zeros((0, 3), dtype=np.float32)).shape == (0, 3)


# one record per intent, raw rows: ab 0.8, bc 0.6, every other pair 0.0
ABCD = unit([1, 0, 0], [0.8, 0.6, 0], [0, 1, 0], [0, 0, 1])


def test_ranked_lists_every_pair_most_similar_first_ties_by_name() -> None:
    rep = analyse(items("a", "b", "c", "d"), ABCD, TH, centred=False)
    assert [(p.a, p.b, p.similarity) for p in rep.ranked] == [
        ("a", "b", 0.8),
        ("b", "c", 0.6),
        ("a", "c", 0.0),
        ("a", "d", 0.0),
        ("b", "d", 0.0),
        ("c", "d", 0.0),
    ]
    top2 = analyse(items("a", "b", "c", "d"), ABCD, TH.model_copy(update={"top_pairs": 2}), False)
    assert [(p.a, p.b) for p in top2.ranked] == [("a", "b"), ("b", "c")]


def test_nearest_per_intent_with_ties_by_name() -> None:
    rep = analyse(items("a", "b", "c", "d"), ABCD, TH, centred=False)
    near = {n: [(p.b, p.similarity) for p in ps] for n, ps in rep.nearest.items()}
    assert near == {
        "a": [("b", 0.8), ("c", 0.0)],
        "b": [("a", 0.8), ("c", 0.6)],
        "c": [("b", 0.6), ("a", 0.0)],
        "d": [("a", 0.0), ("b", 0.0)],
    }
    assert all(p.a == n for n, ps in rep.nearest.items() for p in ps)


def test_close_pairs_are_the_union_of_ranked_and_nearest() -> None:
    th = TH.model_copy(update={"top_pairs": 1})
    rep = analyse(items("a", "b", "c", "d"), ABCD, th, centred=False)
    assert [(p.a, p.b, p.similarity) for p in rep.close_pairs] == [
        ("a", "b", 0.8),
        ("b", "c", 0.6),
        ("a", "c", 0.0),
        ("a", "d", 0.0),
        ("b", "d", 0.0),
    ]
    none = analyse(items("a", "b", "c", "d"), ABCD, th.model_copy(update={"nearest": 0}), False)
    assert [(p.a, p.b) for p in none.close_pairs] == [("a", "b")]


def within_percentile(labels: list[str], emb: np.ndarray, q: float) -> float:
    c = emb - emb.mean(axis=0)
    c = c / np.linalg.norm(c, axis=1, keepdims=True)
    vals = []
    for n in sorted(set(labels)):
        rows = c[[i for i, x in enumerate(labels) if x == n]]
        vals += (rows @ rows.T)[np.triu_indices(len(rows), 1)].tolist()
    assert len(vals) == 3 + 6  # a has 3 pairs, b has 6, c has none
    return float(np.percentile(vals, q))


def test_link_threshold_is_the_percentile_of_within_intent_pairs() -> None:
    labels = ["a"] * 3 + ["b"] * 4 + ["c"]
    emb = unit(*np.random.default_rng(7).normal(size=(8, 6)).tolist())
    rep = analyse(items(*labels), emb, TH)
    assert rep.link_threshold == pytest.approx(within_percentile(labels, emb, 75), abs=1e-6)
    assert rep.link_percentile == 75.0
    p50 = analyse(items(*labels), emb, TH.model_copy(update={"link_percentile": 50.0}))
    assert p50.link_threshold == pytest.approx(within_percentile(labels, emb, 50), abs=1e-6)
    assert p50.link_threshold != pytest.approx(rep.link_threshold, abs=1e-3)


def test_link_threshold_is_one_when_no_intent_has_two_records() -> None:
    rep = analyse(items("a", "b", "c"), unit([1, 0, 0], [0, 1, 0], [0, 0, 1]), TH)
    assert rep.link_threshold == 1.0
    assert {n: [s.size for s in subs] for n, subs in rep.clusters.items()} == {
        "a": [1],
        "b": [1],
        "c": [1],
    }


def test_merge_when_two_sub_clusters_sit_closer_to_other_intents() -> None:
    # m has one group on x and one on y; m's own centroid lies between them
    its = items("m", "m", "m", "m", "x", "x", "y", "y")
    emb = unit(
        [1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 1, 0], [1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 1, 0]
    )
    th = TH.model_copy(update={"link_percentile": 50.0})
    rep = analyse(its, emb, th, centred=False)
    assert rep.link_threshold == pytest.approx(0.5, abs=1e-6)
    assert [(c.intent, c.kind, c.others) for c in rep.candidates] == [("m", "merge", ["x", "y"])]
    assert [(s.size, s.nearest, s.similarity) for s in rep.clusters["m"]] == [
        (2, "x", 1.0),
        (2, "y", 1.0),
    ]


def test_merge_when_two_sub_clusters_sit_closer_to_the_same_intent() -> None:
    # groups at +10 and -10 degrees sit on x; a third group (z axis) pulls m's centroid away
    m = [deg(10), deg(10), deg(-10), deg(-10), [0, 0, 1], [0, 0, 1]]
    rep = analyse(items(*["m"] * 6, "x", "x"), unit(*m, [1, 0, 0], [1, 0, 0]), TH, centred=False)
    assert rep.link_threshold == pytest.approx(0.9397 + 0.25 * (1 - 0.9397), abs=1e-4)
    assert [s.nearest for s in rep.clusters["m"]] == ["x", "x", None]
    assert [(c.intent, c.kind, c.others) for c in rep.candidates] == [("m", "merge", ["x"])]


def own_vs_other(x_angle: float) -> list[tuple[str, str, list[str]]]:
    # m: groups at 0 and 90 degrees, own centroid at 45; x is one record at x_angle
    emb = unit(deg(0), deg(0), deg(90), deg(90), deg(x_angle))
    rep = analyse(items("m", "m", "m", "m", "x"), emb, TH, centred=False)
    assert rep.link_threshold == pytest.approx(0.75, abs=1e-6)
    assert [s.size for s in rep.clusters["m"]] == [2, 2]
    return [(c.intent, c.kind, c.others) for c in rep.candidates]


def test_narrow_when_one_sub_cluster_sits_closer_to_a_tighter_intent() -> None:
    assert own_vs_other(-44) == [("m", "narrow", ["x"])]  # cos 44 > cos 45


def test_no_candidate_when_the_sub_cluster_is_closer_to_its_own_intent() -> None:
    assert own_vs_other(-46) == []  # cos 46 < cos 45; groups at 90 degrees are not far


def test_a_tie_with_its_own_intent_is_not_closer() -> None:
    rep = analyse(items("a", "a", "b", "b"), unit(*[[1, 0, 0]] * 4), TH, centred=False)
    assert [(s.nearest, s.similarity) for s in rep.clusters["a"]] == [(None, 1.0)]


def narrow_against(spread_z: float) -> list[tuple[str, str]]:
    # m: groups on x and y; n: two records at +-spread_z around x (spread 1 - cos 45 at 1.0)
    emb = unit([1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 1, 0], [1, 0, spread_z], [1, 0, -spread_z])
    rep = analyse(items("m", "m", "m", "m", "n", "n"), emb, TH, centred=False)
    assert [(s.size, s.nearest) for s in rep.clusters["m"]] == [(2, "n"), (2, None)]
    return [(c.intent, c.kind) for c in rep.candidates]


def test_narrow_needs_the_other_intent_strictly_tighter() -> None:
    assert narrow_against(1.0) == []  # same spread as m
    assert narrow_against(0.9) == [("m", "narrow")]


def test_no_narrow_when_the_other_intent_is_wider() -> None:
    # w: tight groups at 0 and 30 degrees; n is wide and centred on w's first group
    w = [deg(0), deg(0), deg(30), deg(30)]
    n = [[1, 0.5, 0], [1, -0.5, 0], [1, 0, 0.5], [1, 0, -0.5]]
    th = TH.model_copy(update={"link_percentile": 85.0})
    rep = analyse(items(*["w"] * 4, *["n"] * 4), unit(*w, *n), th, centred=False)
    assert [(s.size, s.nearest) for s in rep.clusters["w"]] == [(2, "n"), (2, None)]
    assert rep.candidates == []  # one hit, but n is wider: no narrow (and no split)


def split_kinds(second: list[float], centred: bool) -> list[tuple[str, str]]:
    emb = unit([1, 0, 0], [1, 0, 0], second, second, [0, 0, 1], [0, 0, 1])
    th = TH.model_copy(update={"link_percentile": 60.0})
    rep = analyse(items("s", "s", "s", "s", "z", "z"), emb, th, centred=centred)
    assert [s.size for s in rep.clusters["s"]] == [2, 2]
    return [(c.intent, c.kind) for c in rep.candidates]


def test_split_needs_sub_clusters_below_zero() -> None:
    assert split_kinds([0, 1, 0], centred=False) == []  # cosine exactly 0 is not far
    assert split_kinds([-0.01, 1, 0], centred=False) == [("s", "split")]


def test_split_uses_centred_rows_by_default() -> None:
    # two groups 0.2 rad apart in raw space; centring puts them on opposite sides
    emb = unit([1, 0.1, 0], [1, 0.1, 0], [1, -0.1, 0], [1, -0.1, 0])
    assert [(c.intent, c.kind) for c in analyse(items(*["s"] * 4), emb, TH).candidates] == [
        ("s", "split")
    ]
    raw = analyse(items(*["s"] * 4), emb, TH, centred=False)
    assert [s.size for s in raw.clusters["s"]] == [2, 2] and raw.candidates == []


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


def test_suspect_tie_between_own_and_other_label_is_not_flagged() -> None:
    # arc at 0, 10, 20, 30 degrees; every record has one a and one b among its 2 neighbours
    emb = unit(deg(0), deg(10), deg(20), deg(30))
    its = items("a", "a", "b", "b")
    assert analyse(its, emb, TH, centred=False).suspects == []


def test_paraphrase_threshold_is_inclusive_on_raw_rows() -> None:
    th = TH.model_copy(update={"paraphrase": 0.0})
    at = analyse(items("a", "b"), unit([1, 0], [0, 1]), th)  # raw cosine exactly 0.0
    assert len(at.paraphrases) == 1 and at.paraphrase_intent_pairs == [["a", "b"]]
    past = analyse(items("a", "b"), unit([1, 0], [-0.01, 1]), th)  # raw cosine just below 0.0
    assert past.paraphrases == [] and past.paraphrase_total == 0


def test_small_groups_fold_into_the_main_group() -> None:
    emb = unit([1, 0], [1, 0.01], [1, 0.02], [0, 1])
    th = TH.model_copy(update={"min_cluster": 3, "link_percentile": 50.0})
    rep = analyse(items("a", "a", "a", "a"), emb, th, centred=False)
    assert [s.size for s in rep.clusters["a"]] == [4]
    th1 = th.model_copy(update={"min_cluster": 1})
    assert [s.size for s in analyse(items(*"aaaa"), emb, th1, False).clusters["a"]] == [3, 1]


def test_tiny_inputs_do_not_crash() -> None:
    empty = analyse([], np.zeros((0, 3), dtype=np.float32), TH)
    assert empty == type(empty)()
    one = analyse(items("a", "a"), unit([1, 0, 0], [1, 0.01, 0]), TH)
    assert one.ranked == [] and one.nearest == {"a": []} and one.candidates == []


def test_dense_intent_does_not_recurse_and_is_one_group() -> None:
    n = 1500
    emb = unit(*[deg(90 * i / n) for i in range(n)])  # a quarter arc: neighbours always link
    rep = analyse(items(*["a"] * n), emb, TH)
    assert [s.size for s in rep.clusters["a"]] == [n]


def test_render_lists_every_section() -> None:
    th = TH.model_copy(update={"top_pairs": 2})
    text = render(analyse(items("a", "b", "c", "d"), ABCD, th, centred=False))
    assert text.startswith("# Overlap review\n\n## Ranked pairs (top 2)\n\n")
    assert "| a | b | 0.8 |\n| b | c | 0.6 |\n\n## Nearest intents" in text
    assert "| intent | 1st | 2nd |\n|---|---|---|\n| a | b (0.8) | c (0.0) |\n" in text
    for heading in ("## Suspect labels", "## Paraphrases across intents", "## Candidates"):
        assert heading in text
    assert text.endswith("\nLink threshold: 1.000 (p75 of within-intent similarity)\n")


def test_render_shows_a_merge_candidate() -> None:
    its = items("m", "m", "m", "m", "x", "x", "y", "y")
    emb = unit(
        [1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 1, 0], [1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 1, 0]
    )
    th = TH.model_copy(update={"link_percentile": 50.0})
    assert "| m | merge | x, y |" in render(analyse(its, emb, th, centred=False))


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
    rep = analyse(its, emb, TH.model_copy(update={"top_pairs": 1, "nearest": 0}))
    assert found_pairs(rep) == {frozenset({"a", "b"})}
    assert recall(rep, {frozenset({"a", "b"}), frozenset({"a", "c"})}) == 0.5
    assert recall(rep, set()) == 1.0


def test_recall_at_counts_expected_pairs_within_the_top_k() -> None:
    names = [f"i{n:02d}" for n in range(11)]  # 55 intent pairs
    labels = [n for n in names for _ in range(2)]
    emb = unit(*np.random.default_rng(3).normal(size=(22, 8)).tolist())
    c = emb - emb.mean(axis=0)
    c = c / np.linalg.norm(c, axis=1, keepdims=True)
    cent = np.array([c[2 * k : 2 * k + 2].mean(axis=0) for k in range(11)])
    cent = cent / np.linalg.norm(cent, axis=1, keepdims=True)
    sims = cent @ cent.T
    pairs = sorted(((sims[i, j], i, j) for i in range(11) for j in range(i + 1, 11)), reverse=True)
    expected = {frozenset({names[pairs[r][1]], names[pairs[r][2]]}) for r in (0, 2, 49)}
    got = recall_at(items(*labels), emb, expected, ks=(1, 2, 3, 49, 50, 120))
    third = pytest.approx(1 / 3)
    assert got == {
        1: third,
        2: third,
        3: pytest.approx(2 / 3),
        49: pytest.approx(2 / 3),
        50: 1.0,
        120: 1.0,
    }
    assert set(recall_at(items(*labels), emb, expected)) == {40, 80, 120}
    assert recall_at(items(*labels), emb, expected)[40] == pytest.approx(2 / 3)


def test_recall_at_is_one_when_nothing_is_expected() -> None:
    assert recall_at(items("a", "b"), unit([1, 0], [0, 1]), set()) == {40: 1.0, 80: 1.0, 120: 1.0}


def test_found_pairs_counts_paraphrase_pairs_beyond_the_display_cap() -> None:
    its = items(*["a"] * 15, *["b"] * 15, "c")
    rows = [[1, 0, 0]] * 30 + [[0.99, 0.14, 0]]
    rep = analyse(its, unit(*rows), Thresholds(top_pairs=0, nearest=0))
    assert len(rep.paraphrases) == 200 and rep.close_pairs == []
    assert rep.paraphrase_total == 225 + 30
    assert {frozenset({"a", "c"}), frozenset({"b", "c"}), frozenset({"a", "b"})} <= found_pairs(rep)
    assert {tuple(p) for p in rep.paraphrase_intent_pairs} == {("a", "b"), ("a", "c"), ("b", "c")}


def test_unfindable_names_pairs_with_an_intent_without_items() -> None:
    ab, ax, xy = (frozenset(p) for p in ({"a", "b"}, {"a", "x"}, {"x", "y"}))
    assert unfindable({ab, ax, xy}, {"a", "b"}) == {ax, xy}
    assert unfindable({ab}, {"a", "b"}) == set()
