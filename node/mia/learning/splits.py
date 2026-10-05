"""Assign train and dev. Test is written by a different model family and is never reassigned."""

import random
from collections import defaultdict

from mia.learning.checks import LEAK, similarity
from mia.learning.schema import Record, RoleSpec


def _clusters(records: list[Record]) -> list[list[Record]]:
    clusters: list[list[Record]] = []
    for r in records:
        home = next((c for c in clusters if similarity(c[0].text, r.text) >= LEAK), None)
        if home is None:
            clusters.append([r])
        else:
            home.append(r)
    return clusters


def assign_train_dev(role: RoleSpec, records: list[Record], seed: int = 0) -> list[Record]:
    """Dev gets its quota per intent and language first; paraphrase clusters never split."""
    rng = random.Random(seed)
    buckets: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for r in records:
        if r.split != "test":
            buckets[(r.intent, r.lang)].append(r)
    split_of: dict[str, str] = {}
    for (intent_id, _lang), bucket in sorted(buckets.items()):
        spec = role.intent(intent_id)
        need = role.targets.quota(spec, "dev") if spec else max(1, len(bucket) // 6)
        clusters = _clusters(sorted(bucket, key=lambda r: r.id))
        rng.shuffle(clusters)
        dev = 0
        for cluster in clusters:
            target = "dev" if dev < need else "train"
            dev += len(cluster) if target == "dev" else 0
            for r in cluster:
                split_of[r.id] = target
    return [
        r.model_copy(update={"split": split_of[r.id]}) if r.id in split_of else r for r in records
    ]
