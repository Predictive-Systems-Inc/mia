"""Training triplets for the contrastive contender (pure, no torch)."""

import random


def triplets(
    by_label: dict[str, list[str]], n: int, rng: random.Random
) -> list[tuple[str, str, str]]:
    """n (anchor, positive, negative) triplets: anchor and positive share a label with at least
    two texts, the negative has another label. Empty when no such triplet exists."""
    anchors = sorted(k for k, ts in by_label.items() if len(ts) >= 2)
    if not anchors or len(by_label) < 2:
        return []
    out = []
    for _ in range(n):
        a = rng.choice(anchors)
        anchor, pos = rng.sample(by_label[a], 2)
        neg_label = rng.choice(sorted(k for k in by_label if k != a))
        out.append((anchor, pos, rng.choice(by_label[neg_label])))
    return out
