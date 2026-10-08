from mia.learning.bakeoff import choose_winner, render_bakeoff
from mia.learning.metrics import TEMPERATURE_GRID
from mia.learning.package import ModelCard
from tests.learning.helpers import card


def scored(
    kind: str, f1: float, cov: float, passed: bool = True, temperature: float = 1.0
) -> ModelCard:
    c = card(version=f"v1-{kind}")
    return c.model_copy(
        update={
            "kind": kind,
            "temperature": temperature,
            "report": c.report.model_copy(update={"macro_f1": f1, "coverage": cov}),
            "gate": c.gate.model_copy(update={"passed": passed}),
        }
    )


def test_winner_is_best_macro_f1_among_passing_then_coverage() -> None:
    a, b, c = (
        scored("encoder", 0.9, 0.8),
        scored("knn", 0.92, 0.7),
        scored("contrastive", 0.92, 0.75),
    )
    assert choose_winner([a, b, c], role_has_slots=False) is c
    assert choose_winner([a, c, b], role_has_slots=False) is c


def test_failed_gate_never_wins_and_slots_keep_the_encoder() -> None:
    a, b = scored("encoder", 0.8, 0.8), scored("knn", 0.99, 0.99)
    assert choose_winner([a, b], role_has_slots=True) is a
    assert choose_winner([a, b], role_has_slots=False) is b
    assert choose_winner([scored("knn", 0.99, 0.99, passed=False)], role_has_slots=False) is None
    failed_best = scored("contrastive", 0.99, 0.99, passed=False)
    assert choose_winner([a, failed_best], role_has_slots=False) is a
    assert choose_winner([b], role_has_slots=True) is None
    assert choose_winner([], role_has_slots=False) is None


def test_render_has_one_row_per_contender_and_names_the_winner() -> None:
    a, b = scored("encoder", 0.9, 0.8), scored("knn", 0.85, 0.9, passed=False)
    text = render_bakeoff([a, b], a, {a.version: 21.0, b.version: 9.5})
    lines = text.splitlines()
    assert lines[0] == "# Bake-off"
    assert lines[2] == "Winner: encoder v1-encoder"
    assert "| encoder | v1-encoder | 0.900 | 0.800 | 1.000 | 0.000 | 1.000 | passed | 21.0 |" in (
        lines
    )
    assert "| knn | v1-knn | 0.850 | 0.900 | 1.000 | 0.000 | 1.000 | failed | 9.5 |" in lines
    assert "No contender is promoted by the bake-off" in text
    assert not any(line.startswith("Temperature at the grid edge") for line in lines)


def test_render_without_a_winner_or_latency() -> None:
    a = scored("knn", 0.5, 0.5, passed=False)
    lines = render_bakeoff([a], None, {}).splitlines()
    assert lines[2] == "Winner: none passed the gate"
    assert "| knn | v1-knn | 0.500 | 0.500 | 1.000 | 0.000 | 1.000 | failed | nan |" in lines


def test_render_flags_a_temperature_at_either_grid_edge() -> None:
    edge = scored("knn", 0.9, 0.9, temperature=TEMPERATURE_GRID[0])
    inside = scored("contrastive", 0.9, 0.9, temperature=TEMPERATURE_GRID[1])
    ok = scored("encoder", 0.9, 0.9, temperature=1.0)
    top = scored("knn", 0.9, 0.9, temperature=TEMPERATURE_GRID[-1]).model_copy(
        update={"version": "v2-knn"}
    )
    below_top = scored("knn", 0.9, 0.9, temperature=TEMPERATURE_GRID[-2])
    lines = render_bakeoff([ok, edge, inside, top, below_top], ok, {}).splitlines()
    assert (
        "Temperature at the grid edge (0.5; SCALE may be too small, coverage understated): v1-knn"
    ) in lines
    assert "Temperature at the grid ceiling (5; the model is overconfident): v2-knn" in lines
    assert sum(line.startswith("Temperature at the grid") for line in lines) == 2
    assert not any(
        line.startswith("Temperature at the grid")
        for line in render_bakeoff([ok, inside, below_top], ok, {}).splitlines()
    )


def test_fit_temperature_searches_the_shared_grid() -> None:
    assert (TEMPERATURE_GRID[0], len(TEMPERATURE_GRID)) == (0.5, 91)
    assert abs(TEMPERATURE_GRID[-1] - 5.0) < 1e-9


def test_render_names_kinds_excluded_for_slots() -> None:
    enc = scored("encoder", 0.8, 0.8)
    knn, con = scored("knn", 0.9, 0.9), scored("contrastive", 0.9, 0.9)
    failed = scored("contrastive", 0.9, 0.9, passed=False)
    lines = render_bakeoff([enc, knn, con], enc, {}, role_has_slots=True).splitlines()
    assert lines[2:5] == [
        "Winner: encoder v1-encoder",
        "excluded: knn, contrastive (role has slot intents)",
        "",
    ]
    failed_enc = scored("encoder", 0.8, 0.8, passed=False)
    lines = render_bakeoff([failed_enc, knn, failed], None, {}, role_has_slots=True).splitlines()
    assert lines[2:4] == ["Winner: none (excluded: knn (role has slot intents))", ""]
    lines = render_bakeoff([enc, knn], enc, {}).splitlines()
    assert lines[2:4] == ["Winner: encoder v1-encoder", ""]
    lines = render_bakeoff([failed_enc, failed], None, {}, role_has_slots=True).splitlines()
    assert lines[2] == "Winner: none passed the gate"
