"""Assign train and dev. Test is written by a different model family and is never reassigned."""

import random
from collections import defaultdict

from mia.learning.checks import LEAK, similarity
from mia.learning.schema import Record, RoleSpec


class _UnionFind:
    """Union-find for transitive closure of similarity relation."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px != py:
            self.parent[px] = py


# ponytail: pairwise O(n^2) per bucket. Upgrade to batch union (DSU with
# normalized-text MinHash/LSH) if buckets exceed a few thousand records.
def _clusters(records: list[Record]) -> list[list[Record]]:
    """Group records into transitive similarity clusters (connected components over LEAK)."""
    if not records:
        return []
    uf = _UnionFind(len(records))
    for i, r_i in enumerate(records):
        for j in range(i + 1, len(records)):
            if similarity(r_i.text, records[j].text) >= LEAK:
                uf.union(i, j)
    clusters_dict: dict[int, list[Record]] = defaultdict(list)
    for i, r in enumerate(records):
        clusters_dict[uf.find(i)].append(r)
    return list(clusters_dict.values())


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
        if not spec:
            raise ValueError(f"unknown intent {intent_id}")
        need = role.targets.quota(spec, "dev")
        clusters = _clusters(sorted(bucket, key=lambda r: r.id))
        rng.shuffle(clusters)
        dev_normal = 0
        for cluster in clusters:
            normal_count = sum(1 for r in cluster if r.kind == "normal")
            target = "dev" if dev_normal < need else "train"
            if target == "dev":
                dev_normal += normal_count
            for r in cluster:
                split_of[r.id] = target
    return [
        r.model_copy(update={"split": split_of[r.id]}) if r.id in split_of else r for r in records
    ]
