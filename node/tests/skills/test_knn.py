import numpy as np

from mia.skills.knn import SCALE, knn_logits


def test_knn_logits_mean_of_top_k_per_label_and_floor_for_missing_labels() -> None:
    sims = np.array([0.9, 0.7, 0.2, 0.8], dtype=np.float32)
    labels = np.array([0, 0, 1, 0])
    out = knn_logits(sims, labels, n_labels=3, k=2)
    assert np.allclose(out, [SCALE * 0.85, SCALE * 0.2, -SCALE])


def test_knn_logits_k_larger_than_examples_uses_all() -> None:
    out = knn_logits(np.array([0.5], dtype=np.float32), np.array([1]), n_labels=2, k=5)
    assert np.allclose(out, [-SCALE, SCALE * 0.5])
