# Embedding Review and Embedding Classifiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure intent overlap with sentence embeddings (`mia skills overlap`), and add two embedding-based classifier contenders (nearest examples, contrastive fine-tune) that compete with the fine-tuned encoder in a bake-off under the same gate.

**Architecture:** `mia.learning.overlap` is numpy only (centroids, neighbours, sub-clusters, candidates, recall against a written review). `mia.learning.embed` (learning group) turns text into unit vectors and exports the pooled encoder to ONNX. `mia.learning.contenders` trains the two new contenders through a packaging helper shared with `train_role`; the model card gains `kind` and `prefix`, and the runtime loads `KnnClassifier` or `OnnxClassifier` by kind.

**Tech Stack:** Python 3.12, numpy, torch and transformers (learning group, already approved in D29), onnxruntime and tokenizers on the node. No new dependency.

**Spec:** docs/superpowers/specs/2026-10-06-embedding-review-design.md (extends docs/superpowers/specs/2026-10-06-skill-models-design.md).

## Global Constraints

- CLAUDE.md rules 1 to 14 apply; this plan adds no DB writes, no egress and no tools.
- No new dependency: numpy, torch, transformers (learning group), onnxruntime, tokenizers only. No scikit-learn, HDBSCAN or the SetFit library.
- Training and embedding code imports torch or transformers only inside `mia.learning.embed`, `mia.learning.train` and `mia.learning.contenders`; the default test suite never imports them (learning-marked tests do).
- The node runtime (`mia.skills.*`) uses onnxruntime, tokenizers and numpy only and never imports huggingface_hub (test_architecture).
- Default embedding model: `intfloat/multilingual-e5-small`, with the input prefix "query: " for e5 models.
- Embeddings of harvested real messages stay on the node (D18).
- Ruff line length 100, mypy clean on node/mia (with and without the learning group), no em-dashes in docs or comments, Filipino never Tagalog.
- Every package file the runtime loads is listed in `card.artifacts` with its sha256 and verified before load (D29).

## Review Focus

1. An intent with fewer records than `min_cluster` (or a single record): analysis treats the whole intent as one group and does not crash. Pinned in Task 1.
2. A dataset with one intent or no records: `analyse` returns an empty report; the command prints an error and exits 1 for no records. Pinned in Tasks 1 and 3.
3. A model card written before this plan (no `kind`, no `prefix`) loads as an encoder package exactly as before. Pinned in Task 5.
4. A record whose intent is not in the label space (a stale or removed intent) is scored as `other` by every contender. Pinned in Task 6.
5. Three contenders trained in the same minute do not overwrite each other (version suffix per kind). Pinned in Task 6.

---

### Task 1: Overlap analysis (numpy)

**Files:**
- Create: `node/mia/learning/overlap.py`
- Test: `node/tests/learning/test_overlap.py`

**Interfaces:**
- Consumes: `_UnionFind` from `mia.learning.splits`.
- Produces: `Item(id: str, intent: str, text: str)`, `Thresholds` (fields below), `Pair`, `Suspect`, `Paraphrase`, `SubCluster`, `Candidate`, `OverlapReport`; `analyse(items: list[Item], emb: np.ndarray, th: Thresholds = Thresholds()) -> OverlapReport`; `render(report: OverlapReport) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_overlap.py
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
    its = items("a", "a", "a", "b", "b")
    emb = unit([1, 0, 0], [1, 0.01, 0], [0, 1, 0.01], [0, 1, 0], [0, 1, 0.02])
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/learning/test_overlap.py --no-cov -q`
Expected: FAIL (ModuleNotFoundError: mia.learning.overlap)

- [ ] **Step 3: Implement**

```python
# node/mia/learning/overlap.py
"""Intent overlap from sentence embeddings (numpy only; spec embedding review section 3).

Rows of `emb` are unit vectors, one per Item, in the same order. Nothing here relabels data: the
report lists signals and suggested decisions for the developer (D30 rules)."""

from collections import Counter, defaultdict
from typing import Literal

import numpy as np
from pydantic import BaseModel

from mia.learning.splits import _UnionFind


class Item(BaseModel):
    id: str
    intent: str
    text: str


class Thresholds(BaseModel):
    close_pair: float = 0.85  # centroid cosine between two intents
    paraphrase: float = 0.95  # record cosine across intents
    cluster: float = 0.80  # link two records of one intent into a sub-cluster
    overlap: float = 0.85  # sub-cluster centroid to another intent's centroid
    split: float = 0.60  # sub-cluster centroids below this are far apart
    min_cluster: int = 3  # smaller sub-clusters join the intent's main group
    k: int = 10  # neighbours for suspect labels
    suspect_share: float = 0.6  # share of neighbours with one other label


class Pair(BaseModel):
    a: str
    b: str
    similarity: float


class Suspect(BaseModel):
    id: str
    intent: str
    text: str
    neighbours_label: str
    share: float


class Paraphrase(BaseModel):
    a_id: str
    a_intent: str
    b_id: str
    b_intent: str
    similarity: float


class SubCluster(BaseModel):
    size: int
    examples: list[str]
    nearest: str | None  # another intent this sub-cluster overlaps, if any
    similarity: float


class Candidate(BaseModel):
    intent: str
    kind: Literal["merge", "split", "narrow"]
    others: list[str]
    reason: str


class OverlapReport(BaseModel):
    close_pairs: list[Pair] = []
    suspects: list[Suspect] = []
    paraphrases: list[Paraphrase] = []
    clusters: dict[str, list[SubCluster]] = {}
    candidates: list[Candidate] = []


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.asarray(v / np.where(n == 0, 1, n), dtype=np.float32)


def _groups(idx: list[int], emb: np.ndarray, th: Thresholds) -> list[list[int]]:
    """Sub-clusters of one intent, largest first; small ones join the largest."""
    uf = _UnionFind(len(idx))
    sims = emb[idx] @ emb[idx].T
    for i in range(len(idx)):
        for j in range(i + 1, len(idx)):
            if sims[i, j] >= th.cluster:
                uf.union(i, j)
    by_root: dict[int, list[int]] = defaultdict(list)
    for i, item in enumerate(idx):
        by_root[uf.find(i)].append(item)
    groups = sorted(by_root.values(), key=len, reverse=True)
    big = [g for g in groups if len(g) >= th.min_cluster]
    if not big:
        return [idx]
    for g in groups:
        if len(g) < th.min_cluster:
            big[0] = big[0] + g
    return big


def _spread(rows: np.ndarray) -> float:
    return float(1 - (rows @ _unit(rows.mean(axis=0))).mean())


def analyse(items: list[Item], emb: np.ndarray, th: Thresholds = Thresholds()) -> OverlapReport:
    """Close intent pairs, suspect labels, cross-intent paraphrases and per-intent sub-clusters
    with merge, split and narrow candidates. Empty or single-intent input gives empty lists."""
    if not items:
        return OverlapReport()
    by_intent: dict[str, list[int]] = defaultdict(list)
    for i, it in enumerate(items):
        by_intent[it.intent].append(i)
    names = sorted(by_intent)
    cent = {n: _unit(emb[by_intent[n]].mean(axis=0)) for n in names}
    sims = emb @ emb.T
    rep = OverlapReport()
    for x, a in enumerate(names):
        for b in names[x + 1 :]:
            s = float(cent[a] @ cent[b])
            if s >= th.close_pair:
                rep.close_pairs.append(Pair(a=a, b=b, similarity=round(s, 3)))
    rep.close_pairs.sort(key=lambda p: p.similarity, reverse=True)
    k = min(th.k, len(items) - 1)
    for i, it in enumerate(items):
        if k <= 0:
            break
        row = sims[i].copy()
        row[i] = -np.inf
        near = [items[j].intent for j in np.argsort(row)[::-1][:k]]
        label, count = Counter(near).most_common(1)[0]
        if label != it.intent and count / k >= th.suspect_share:
            rep.suspects.append(
                Suspect(
                    id=it.id,
                    intent=it.intent,
                    text=it.text,
                    neighbours_label=label,
                    share=round(count / k, 3),
                )
            )
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i].intent != items[j].intent and sims[i, j] >= th.paraphrase:
                a, b = sorted([(items[i].intent, items[i].id), (items[j].intent, items[j].id)])
                rep.paraphrases.append(
                    Paraphrase(
                        a_id=a[1],
                        a_intent=a[0],
                        b_id=b[1],
                        b_intent=b[0],
                        similarity=round(float(sims[i, j]), 3),
                    )
                )
    for n in names:
        groups = _groups(by_intent[n], emb, th)
        subs: list[SubCluster] = []
        gcent = [_unit(emb[g].mean(axis=0)) for g in groups]
        for g, gc in zip(groups, gcent, strict=True):
            others = [(float(gc @ cent[o]), o) for o in names if o != n]
            best_sim, best = max(others) if others else (0.0, None)
            subs.append(
                SubCluster(
                    size=len(g),
                    examples=[items[i].text for i in g[:3]],
                    nearest=best if best_sim >= th.overlap else None,
                    similarity=round(best_sim, 3),
                )
            )
        rep.clusters[n] = subs
        hits = [s.nearest for s in subs if s.nearest]
        if len(hits) >= 2:
            rep.candidates.append(
                Candidate(
                    intent=n,
                    kind="merge",
                    others=sorted(set(hits)),
                    reason=f"{len(hits)} sub-clusters overlap other intents",
                )
            )
        elif len(hits) == 1:
            other = hits[0]
            if len(subs) >= 2 and _spread(emb[by_intent[other]]) < _spread(emb[by_intent[n]]):
                rep.candidates.append(
                    Candidate(
                        intent=n,
                        kind="narrow",
                        others=[other],
                        reason=f"one sub-cluster fits the narrower {other}",
                    )
                )
        elif len(groups) >= 2:
            far = min(
                float(gcent[i] @ gcent[j])
                for i in range(len(gcent))
                for j in range(i + 1, len(gcent))
            )
            if far < th.split:
                rep.candidates.append(
                    Candidate(
                        intent=n,
                        kind="split",
                        others=[],
                        reason=f"{len(groups)} distant sub-clusters",
                    )
                )
    return rep


def render(report: OverlapReport) -> str:
    """Markdown with one table per signal, for Gate 1 and the data review."""
    out = [
        "# Overlap review",
        "",
        "## Close intents",
        "",
        "| a | b | similarity |",
        "|---|---|---|",
    ]
    out += [f"| {p.a} | {p.b} | {p.similarity} |" for p in report.close_pairs]
    out += [
        "",
        "## Suspect labels",
        "",
        "| record | labelled | neighbours say | share |",
        "|---|---|---|---|",
    ]
    out += [f"| {s.id} | {s.intent} | {s.neighbours_label} | {s.share} |" for s in report.suspects]
    out += ["", "## Paraphrases across intents", "", "| a | b | similarity |", "|---|---|---|"]
    out += [
        f"| {p.a_id} ({p.a_intent}) | {p.b_id} ({p.b_intent}) | {p.similarity} |"
        for p in report.paraphrases
    ]
    out += ["", "## Candidates", "", "| intent | kind | others | reason |", "|---|---|---|---|"]
    out += [
        f"| {c.intent} | {c.kind} | {', '.join(c.others)} | {c.reason} |" for c in report.candidates
    ]
    return "\n".join(out) + "\n"
```

Adjust the exact float fixtures in Step 1 only if the arithmetic of a fixture does not produce the stated case (keep the asserted outcome; print the similarity and say so in the report).

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest node/tests/learning/test_overlap.py --no-cov -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/overlap.py node/tests/learning/test_overlap.py
git commit -m "learning: intent overlap analysis from embeddings (close pairs, suspects, sub-clusters)"
```

---

### Task 2: Recall against a written review, and calibration

**Files:**
- Modify: `node/mia/learning/overlap.py`
- Test: `node/tests/learning/test_overlap.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `review_pairs(markdown: str) -> set[frozenset[str]]`; `found_pairs(report: OverlapReport) -> set[frozenset[str]]`; `recall(report: OverlapReport, expected: set[frozenset[str]]) -> float`; `calibrate(items, emb, expected, budget: float = 3.0) -> tuple[Thresholds, float]`.

- [ ] **Step 1: Write the failing tests**

```python
# append to node/tests/learning/test_overlap.py
from mia.learning.overlap import calibrate, found_pairs, recall, review_pairs

REVIEW = """# Intent overlap review

## Decisions

| Pair | Decision | Rule | Records moved |
| --- | --- | --- | --- |
| hr.payday / conversation.kb_payday | removed | 1 | 23 |
| sales.price_question / kb_prices | removed | 1 | 20 |
| client_service.update_contact / admin.update_client / bookkeeper.billing_details | one | 3 | 38 |
| client_service.service_faq / kb_services, kb_pets | removed | 1 | 5 |

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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/learning/test_overlap.py --no-cov -q`
Expected: FAIL (ImportError: review_pairs)

- [ ] **Step 3: Implement**

```python
# append to node/mia/learning/overlap.py
from itertools import combinations, product


def _intent_id(token: str) -> str:
    token = token.strip().strip("*`")
    return token if "." in token else f"conversation.{token}"


def review_pairs(markdown: str) -> set[frozenset[str]]:
    """Intent pairs named in the first column of the "## Decisions" table of a review document
    ("a / b, c" means a with b and a with c; "a / b / c" means every pair of a, b and c)."""
    pairs: set[frozenset[str]] = set()
    section = markdown.split("## Decisions", 1)[-1].split("\n## ", 1)[0]
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or "/" not in cells[0] or cells[0].startswith("Pair"):
            continue
        sides = [[_intent_id(t) for t in part.split(",")] for part in cells[0].split(" / ")]
        if len(sides) == 2:
            pairs |= {frozenset({a, b}) for a, b in product(sides[0], sides[1]) if a != b}
        else:
            flat = [x for side in sides for x in side]
            pairs |= {frozenset({a, b}) for a, b in combinations(flat, 2) if a != b}
    return pairs


def found_pairs(report: OverlapReport) -> set[frozenset[str]]:
    """Every intent pair any signal links: close pairs, paraphrases, suspects and candidates."""
    found = {frozenset({p.a, p.b}) for p in report.close_pairs}
    found |= {frozenset({p.a_intent, p.b_intent}) for p in report.paraphrases}
    found |= {frozenset({s.intent, s.neighbours_label}) for s in report.suspects}
    found |= {frozenset({c.intent, o}) for c in report.candidates for o in c.others}
    return found


def recall(report: OverlapReport, expected: set[frozenset[str]]) -> float:
    """Share of the expected pairs that the report links; 1.0 when nothing is expected."""
    return len(expected & found_pairs(report)) / len(expected) if expected else 1.0


def calibrate(
    items: list[Item], emb: np.ndarray, expected: set[frozenset[str]], budget: float = 3.0
) -> tuple[Thresholds, float]:
    """Grid search for the thresholds with the best recall whose flagged pairs stay within
    budget x len(expected) (flagging everything would score 1.0); ties keep the stricter grid
    point (fewer flags)."""
    best: tuple[float, int, Thresholds] | None = None
    limit = max(1, int(budget * len(expected)))
    for close, ovl, clu, para in product(
        (0.75, 0.8, 0.85, 0.9, 0.92), (0.75, 0.8, 0.85, 0.9), (0.75, 0.8, 0.85), (0.92, 0.95, 0.97)
    ):
        th = Thresholds(close_pair=close, overlap=ovl, cluster=clu, paraphrase=para)
        rep = analyse(items, emb, th)
        flagged = len(found_pairs(rep))
        if flagged > limit:
            continue
        key = (recall(rep, expected), -flagged)
        if best is None or key > (best[0], best[1]):
            best = (key[0], key[1], th)
    if best is None:
        return Thresholds(), 0.0
    return best[2], best[0]
```

Move the two new imports to the top of the module with the others.

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest node/tests/learning/test_overlap.py --no-cov -q`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/overlap.py node/tests/learning/test_overlap.py
git commit -m "learning: overlap recall against a written review and threshold calibration"
```

---

### Task 3: Embedder and `mia skills overlap`

**Files:**
- Create: `node/mia/learning/embed.py`
- Modify: `node/mia/learning/schema.py` (`RoleSpec.embedding_model`), `node/mia/learning/commands.py` (`overlap_cmd`, registration)
- Test: `node/tests/learning/test_overlap_command.py` (default suite, fake embedder), `node/tests/learning/test_embed.py` (marker `learning`)

**Interfaces:**
- Consumes: Tasks 1 and 2; `catalogue.conversation_intents()` (`examples` field); `_role_spec`, `skill_dir`, `LEARNING_PKGS`, `LEARNING_HINT` in commands.py.
- Produces: `RoleSpec.embedding_model: str = "intfloat/multilingual-e5-small"`; `embed.prefix_for(name) -> str`; `embed.Pooled(nn.Module)` (forward(input_ids, attention_mask) -> unit vectors); `embed.Embedder(name, max_len=96)` with `.prefix`, `.tok`, `.model` (a Pooled) and `__call__(texts: list[str]) -> np.ndarray`; `embed.export(model: Pooled, tok, out: Path, outputs: str = "embedding") -> None`; CLI `mia skills overlap [role] [--dataset PATH] [--embedding-model M] [--expect REVIEW.md] [--calibrate] [--out PATH]`.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_overlap_command.py
import json
import types
from pathlib import Path

import numpy as np
import pytest

from mia.cli import main
from mia.learning import commands


class FakeEmbedder:
    """Bag of words over a tiny vocabulary: texts sharing words are close."""

    prefix = ""

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, texts: list[str]) -> np.ndarray:
        vocab = ["pay", "day", "price", "clean", "hello"]
        m = np.array([[t.lower().count(w) + 0.01 for w in vocab] for t in texts], dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.SimpleNamespace(Embedder=FakeEmbedder)
    real = commands.import_module
    monkeypatch.setattr(
        commands, "import_module", lambda n: module if n == "mia.learning.embed" else real(n)
    )


def write_dataset(path: Path) -> None:
    rows = [
        ("a/1", "hr.payday", "when is pay day"),
        ("a/2", "hr.payday", "pay day when"),
        ("b/1", "conversation.kb_payday", "what day is pay day"),
        ("b/2", "conversation.kb_payday", "pay day date"),
    ]
    path.write_text(
        "".join(json.dumps({"id": i, "intent": n, "text": t}) + "\n" for i, n, t in rows),
        encoding="utf-8",
    )


def test_overlap_on_a_dataset_writes_the_report_and_recall(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "d.jsonl"
    write_dataset(data)
    review = tmp_path / "review.md"
    review.write_text(
        "## Decisions\n\n| Pair | D |\n| --- | --- |\n| hr.payday / conversation.kb_payday | x |\n",
        encoding="utf-8",
    )
    out = tmp_path / "r.md"
    assert (
        main(
            [
                "skills",
                "overlap",
                "--dataset",
                str(data),
                "--expect",
                str(review),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    text = out.read_text(encoding="utf-8")
    assert "| conversation.kb_payday | hr.payday |" in text
    assert "recall 1.00 (1/1)" in capsys.readouterr().out


def test_overlap_needs_a_role_or_a_dataset(fake: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skills", "overlap"]) == 1
    assert capsys.readouterr().out.strip() == "give a role or --dataset"


def test_overlap_with_no_records_is_an_error(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "e.jsonl"
    empty.write_text("", encoding="utf-8")
    assert main(["skills", "overlap", "--dataset", str(empty), "--no-conversation"]) == 1
    assert capsys.readouterr().out.strip() == "no records to compare"


def test_overlap_without_the_learning_group_prints_the_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def missing(name: str) -> object:
        raise ModuleNotFoundError("no torch", name="torch")

    monkeypatch.setattr(commands, "import_module", missing)
    data = tmp_path / "d.jsonl"
    write_dataset(data)
    assert main(["skills", "overlap", "--dataset", str(data)]) == 2
    assert capsys.readouterr().out.strip() == commands.LEARNING_HINT
```

```python
# node/tests/learning/test_embed.py
import numpy as np
import pytest

pytestmark = pytest.mark.learning
TINY = "optimum-intel-internal-testing/tiny-random-xlm-roberta"


def test_embedder_returns_unit_rows_and_prefix() -> None:
    from mia.learning.embed import Embedder, prefix_for

    assert prefix_for("intfloat/multilingual-e5-small") == "query: "
    assert prefix_for(TINY) == ""
    e = Embedder(TINY)
    m = e(["hello there", "oon kipee", "x"])
    assert m.shape[0] == 3 and m.dtype == np.float32
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0, atol=1e-5)
    assert e([]).shape[0] == 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/learning/test_overlap_command.py --no-cov -q`
Expected: FAIL (argparse error: invalid choice 'overlap')

- [ ] **Step 3: Implement**

In `node/mia/learning/schema.py`, add to `RoleSpec` after `base_model`:

```python
    embedding_model: str = "intfloat/multilingual-e5-small"
```

```python
# node/mia/learning/embed.py
"""Sentence embeddings (learning group): mean-pooled, unit-length rows; ONNX export for the node."""

from pathlib import Path

import numpy as np
import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer, PreTrainedTokenizerBase

MAX_LEN = 96


def prefix_for(model_name: str) -> str:
    """e5 models expect "query: " before symmetric-task inputs; others take the text as is."""
    return "query: " if "e5" in model_name.lower() else ""


class Pooled(nn.Module):  # type: ignore[misc,unused-ignore]  # Any when torch is not installed
    """Encoder plus attention-masked mean pooling and L2 normalisation."""

    def __init__(self, encoder: nn.Module) -> None:
        super().__init__()
        self.encoder = encoder

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
        mean = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return nn.functional.normalize(mean, dim=-1)


class Embedder:
    """Callable text -> float32 unit rows. Adds the model's prefix to every text."""

    def __init__(self, model_name: str, max_len: int = MAX_LEN) -> None:
        self.tok: PreTrainedTokenizerBase = AutoTokenizer.from_pretrained(model_name)
        self.model = Pooled(AutoModel.from_pretrained(model_name)).eval()
        self.prefix = prefix_for(model_name)
        self.max_len = max_len

    def encode(self, texts: list[str]) -> dict[str, torch.Tensor]:
        enc = self.tok(
            [self.prefix + t for t in texts],
            truncation=True,
            max_length=self.max_len,
            padding=True,
            return_tensors="pt",
        )
        return {"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"]}

    def __call__(self, texts: list[str], batch: int = 64) -> np.ndarray:
        dim = int(self.model.encoder.config.hidden_size)
        if not texts:
            return np.zeros((0, dim), dtype=np.float32)
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), batch):
                out.append(self.model(**self.encode(texts[i : i + batch])).numpy())
        return np.concatenate(out).astype(np.float32)


def export(
    model: nn.Module,
    tok: PreTrainedTokenizerBase,
    out: Path,
    output: str = "embedding",
    max_len: int = MAX_LEN,
) -> None:
    """Writes model.onnx (inputs input_ids, attention_mask; one output) and tokenizer.json with
    truncation pinned at max_len, so the runtime needs neither torch nor transformers."""
    out.mkdir(parents=True, exist_ok=True)
    model.eval()
    sample = tok(["hello"], return_tensors="pt")
    torch.onnx.export(
        model,
        (sample["input_ids"], sample["attention_mask"]),
        out / "model.onnx",
        input_names=["input_ids", "attention_mask"],
        output_names=[output],
        dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}},
        opset_version=17,
        dynamo=False,
    )
    backend = getattr(tok, "backend_tokenizer", None)
    if backend is None:
        raise ValueError("embedding model has no fast tokenizer; tokenizer.json cannot be exported")
    backend.enable_truncation(max_length=max_len)
    backend.save(str(out / "tokenizer.json"))
```

In `node/mia/learning/commands.py` add (import `json` and `numpy` lazily inside the function is fine; numpy is a node dependency):

```python
def _learning_module(name: str) -> object | None:
    """The learning-group module, or None after printing the install hint."""
    try:
        return import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name and (exc.name or "").split(".")[0] not in LEARNING_PKGS:
            raise
        print(LEARNING_HINT)
        return None


def overlap_cmd(args: argparse.Namespace) -> int:
    """Embedding overlap report for a role's records or an eval-format dataset (id, intent,
    text per line), plus the shared conversation examples unless --no-conversation."""
    import json

    from mia.learning.overlap import Item, analyse, calibrate, recall, render, review_pairs

    if not args.role and not args.dataset:
        print("give a role or --dataset")
        return 1
    embed = _learning_module("mia.learning.embed")
    if embed is None:
        return 2
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M")
    if args.dataset:
        lines = Path(args.dataset).read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
        items = [Item(id=r["id"], intent=r["intent"], text=r["text"]) for r in rows]
        model = args.embedding_model or RoleSpec.model_fields["embedding_model"].default
        out = Path(args.out) if args.out else Path(f"overlap-{stamp}.md")
    else:
        role = _role_spec(args.role)
        if role is None:
            return 1
        data = skill_dir(args.role) / "data"
        items = [
            Item(id=r.id, intent=r.intent, text=r.text)
            for s in ("train", "dev", "test", "reviewed")
            if (data / f"{s}.jsonl").exists()
            for r in load_records(data / f"{s}.jsonl")
        ]
        model = args.embedding_model or role.embedding_model
        out = (
            Path(args.out) if args.out else skill_dir(args.role) / "reports" / f"overlap-{stamp}.md"
        )
    if not args.no_conversation:
        items += [
            Item(id=f"{c.id}/example/{n}", intent=c.id, text=e)
            for c in catalogue.conversation_intents()
            for n, e in enumerate(c.examples)
        ]
    if not items:
        print("no records to compare")
        return 1
    emb = embed.Embedder(model)([i.text for i in items])  # type: ignore[attr-defined]
    expected = review_pairs(Path(args.expect).read_text(encoding="utf-8")) if args.expect else set()
    th = None
    if args.calibrate and expected:
        th, _ = calibrate(items, emb, expected)
    report = analyse(items, emb, th) if th else analyse(items, emb)
    text = render(report)
    if th:
        text += f"\nCalibrated thresholds: {th.model_dump_json()}\n"
    if expected:
        r = recall(report, expected)
        found = round(r * len(expected))
        line = f"recall {r:.2f} ({found}/{len(expected)})"
        text += f"\nAgainst {args.expect}: {line}\n"
        print(line)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(out)
    return 0
```

Refactor `train` in commands.py to use `_learning_module("mia.learning.train")` (same behaviour, the existing tests must still pass). In `register` add:

```python
    p = skills.add_parser("overlap", help="embedding overlap review of intents")
    p.add_argument("role", nargs="?", default=None)
    p.add_argument("--dataset", default=None, help="eval-format jsonl: id, intent, text")
    p.add_argument("--embedding-model", default=None)
    p.add_argument("--expect", default=None, help="review markdown whose pairs must be found")
    p.add_argument("--calibrate", action="store_true", help="tune thresholds against --expect")
    p.add_argument("--no-conversation", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=overlap_cmd)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest node/tests/learning/test_overlap_command.py node/tests/learning/test_commands.py --no-cov -q`
Expected: PASS
Run: `HF_HUB_DISABLE_IMPLICIT_TOKEN=1 uv run pytest node/tests/learning/test_embed.py -m learning --no-cov -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/embed.py node/mia/learning/schema.py node/mia/learning/commands.py node/tests/learning/test_overlap_command.py node/tests/learning/test_embed.py
git commit -m "learning: sentence embedder and mia skills overlap"
```

---

### Task 4: Calibrate on the pre-review dataset (operational)

**Files:**
- Modify: `node/mia/learning/overlap.py` (`Thresholds` defaults)
- Create: `docs/research/overlap-calibration-2026-10-06.md`
- Modify: `.claude/skills/mia-train-role/guidelines.md` (calibrated thresholds and the recall)
- Test: `node/tests/learning/test_overlap.py` (pin the new defaults)

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces: calibrated `Thresholds()` defaults.

- [ ] **Step 1: Run the calibration with the real embedding model** (downloads about 470 MB once)

```bash
git show 8fee0ac:node/tests/evals/intents.jsonl > /tmp/pre-d30-intents.jsonl
HF_HUB_DISABLE_IMPLICIT_TOKEN=1 uv run mia skills overlap --dataset /tmp/pre-d30-intents.jsonl \
  --expect docs/research/intent-overlap-review-2026-10-06.md --calibrate \
  --out docs/research/overlap-calibration-2026-10-06.md
```

Expected: a printed line `recall R (F/N)` and a report ending with "Calibrated thresholds".
Acceptance: R >= 0.80. If R < 0.80, also try `--embedding-model BAAI/bge-m3`; record both results in the research note; if neither reaches 0.80, stop and report BLOCKED with the numbers (the controller rules).

- [ ] **Step 2: Write the research note**

At the top of docs/research/overlap-calibration-2026-10-06.md (above the generated report): date, dataset (8fee0ac, record count), embedding model, the calibrated thresholds, recall, the expected pairs that were not found and why (look at their records), and the five strongest flagged pairs that the D30 review did not list, each with a one-line judgement (real overlap or noise).

- [ ] **Step 3: Pin the defaults**

Set the `Thresholds` field defaults in overlap.py to the calibrated values (round to two decimals) with a comment `# calibrated 2026-10-06 on the pre-D30 dataset, recall R (docs/research/overlap-calibration-2026-10-06.md)`, and add a test that asserts the exact defaults:

```python
def test_default_thresholds_are_the_calibrated_ones() -> None:
    assert Thresholds().model_dump() == {...}  # the calibrated values, written out
```

Add one line to guidelines.md under "How many intents one model can hold": "`mia skills overlap` thresholds were calibrated on the pre-D30 dataset (recall R); see docs/research/overlap-calibration-2026-10-06.md."

- [ ] **Step 4: Run the tests**

Run: `uv run pytest node/tests/learning/test_overlap.py --no-cov -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/overlap.py node/tests/learning/test_overlap.py docs/research/overlap-calibration-2026-10-06.md .claude/skills/mia-train-role/guidelines.md
git commit -m "learning: overlap thresholds calibrated on the pre-review dataset"
```

---

### Task 5: Package kinds and runtime dispatch

**Files:**
- Modify: `node/mia/learning/package.py` (`ModelCard.kind`, `ModelCard.prefix`, per-kind artifacts), `node/mia/skills/runtime.py` (`embed_text`, `_load` dispatch), `node/mia/skills/onnx.py` (kind-aware encoding, optional lang output)
- Test: `node/tests/learning/test_package.py`, `node/tests/skills/test_runtime.py`, `node/tests/skills/test_onnx.py`

**Interfaces:**
- Consumes: existing `ModelCard`, `verify_artifacts`, `OnnxClassifier`.
- Produces: `ModelCard.kind: Literal["encoder", "knn", "contrastive"] = "encoder"`; `ModelCard.prefix: str = ""`; `package.ARTIFACTS: dict[str, tuple[str, ...]]` (encoder and contrastive: model.onnx, tokenizer.json; knn: also examples.npy, examples.json); `verify_artifacts(card)` checks the files for `card.kind`; `runtime.embed_text(prefix: str, text: str, context: str) -> str`; `_load` returns `KnnClassifier` for kind knn (module `mia.skills.knn`, Task 6), `OnnxClassifier` otherwise.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_package.py (append)
from mia.learning.package import ARTIFACTS


def test_cards_without_kind_load_as_encoder_packages() -> None:
    raw = card().model_dump()
    raw.pop("kind")
    raw.pop("prefix")
    loaded = ModelCard.model_validate(raw)
    assert loaded.kind == "encoder" and loaded.prefix == ""


def test_knn_packages_need_their_example_files(session: Session, people: dict[str, Person]) -> None:
    assert ARTIFACTS["knn"] == ("model.onnx", "tokenizer.json", "examples.npy", "examples.json")
    c = card(version="v1").model_copy(update={"kind": "knn"})
    write_package(c)  # writes only model.onnx and tokenizer.json with digests
    with pytest.raises(PromotionRefused) as err:
        promote(session, Actor.person(people["Helena"]), "r", "v1", signed_by="Allan")
    assert str(err.value) == "r@v1 cannot be loaded: examples.npy: no sha256 in card artifacts"
```

```python
# node/tests/skills/test_runtime.py (append)
from mia.skills.runtime import embed_text


def test_embed_text_joins_prefix_text_and_context() -> None:
    assert embed_text("query: ", "hi", "") == "query: hi"
    assert embed_text("", "yes", "Did you mean X?") == "yes\nDid you mean X?"


def test_knn_cards_load_the_knn_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    import mia.skills.runtime as rt

    made: list[str] = []

    class FakeKnn:
        def __init__(self, card: ModelCard, safety: set[str]) -> None:
            made.append(card.kind)

    monkeypatch.setitem(
        __import__("sys").modules, "mia.skills.knn", type(__import__("sys"))("mia.skills.knn")
    )
    __import__("sys").modules["mia.skills.knn"].KnnClassifier = FakeKnn  # type: ignore[attr-defined]
    write_card(card().model_copy(update={"kind": "knn"}))
    (get_settings().MIA_MODELS_DIR / "r" / "ACTIVE").write_text("v1", encoding="utf-8")
    rt.reset_classifiers()
    assert isinstance(rt.get_classifier("r"), FakeKnn) and made == ["knn"]
```

(Use the test file's existing `card()` helper and imports; adapt names to what is there.)

```python
# node/tests/skills/test_onnx.py (append, default suite)
def test_contrastive_cards_encode_one_joined_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from mia.skills.onnx import OnnxClassifier

    seen: list[tuple[str, ...]] = []

    class Tok:
        def encode(self, *texts: str) -> object:
            seen.append(texts)
            return type("E", (), {"ids": [0, 1], "attention_mask": [1, 1]})()

    class Session:
        def run(self, names: list[str], feeds: dict[str, object]) -> list[object]:
            import numpy as np

            return [np.array([[2.0, 0.0, 0.0]])]

    clf = object.__new__(OnnxClassifier)
    clf.card = card().model_copy(
        update={
            "kind": "contrastive",
            "prefix": "query: ",
            "labels": ["r.a", "conversation.greeting", "other"],
            "thresholds": {"r.a": 0.5},
        }
    )
    clf.safety = set()
    clf.tokenizer = Tok()
    clf.session = Session()
    clf.outputs = ["intent_logits"]
    c = clf.classify("hi", "ctx")
    assert seen == [("query: hi\nctx",)]
    assert c.intent == "r.a" and c.lang is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/learning/test_package.py node/tests/skills --no-cov -q`
Expected: FAIL (kind field missing, embed_text missing)

- [ ] **Step 3: Implement**

package.py:

```python
Kind = Literal["encoder", "knn", "contrastive"]
ARTIFACTS: dict[str, tuple[str, ...]] = {
    "encoder": ("model.onnx", "tokenizer.json"),
    "contrastive": ("model.onnx", "tokenizer.json"),
    "knn": ("model.onnx", "tokenizer.json", "examples.npy", "examples.json"),
}
```

Add to `ModelCard`: `kind: Kind = "encoder"` and `prefix: str = ""  # embedding input prefix (e5: "query: ")`. In `verify_artifacts` iterate `ARTIFACTS[card.kind]`.

runtime.py:

```python
def embed_text(prefix: str, text: str, context: str) -> str:
    """The single input string of the embedding contenders: prefix, text, then context."""
    return f"{prefix}{text}\n{context}" if context else f"{prefix}{text}"
```

In `_load`, after `read_card`:

```python
        if card.kind == "knn":
            from mia.skills.knn import KnnClassifier

            return KnnClassifier(card, safety=catalogue.safety_ids())
        from mia.skills.onnx import OnnxClassifier
```

onnx.py `classify`:

```python
        if self.card.kind == "contrastive":
            enc = self.tokenizer.encode(embed_text(self.card.prefix, text, context))
        else:
            enc = self.tokenizer.encode(text, context)
        ...
        lang = values.get("lang_logits")
        return self.from_logits(
            values["intent_logits"][0].tolist(), lang[0].tolist() if lang is not None else [], slots
        )
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest node/tests/learning node/tests/skills --no-cov -q`
Expected: PASS
Run: `HF_HUB_DISABLE_IMPLICIT_TOKEN=1 uv run pytest -m learning --no-cov -q`
Expected: PASS (existing encoder packages unchanged)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/package.py node/mia/skills/runtime.py node/mia/skills/onnx.py node/tests/learning/test_package.py node/tests/skills/test_runtime.py node/tests/skills/test_onnx.py
git commit -m "skills: package kinds (encoder, knn, contrastive) with per-kind artifacts"
```

---

### Task 6: Shared packaging and the nearest-examples contender

**Files:**
- Modify: `node/mia/learning/train.py` (extract `load_splits`, `new_version`, `new_package_dir`, `package` from `train_role`; `train_role` behaviour unchanged)
- Create: `node/mia/learning/contenders.py` (`train_knn`), `node/mia/skills/knn.py` (`SCALE`, `knn_logits`, `KnnClassifier`)
- Test: `node/tests/skills/test_knn.py` (default suite), `node/tests/learning/test_contenders.py` (marker `learning`)

**Interfaces:**
- Consumes: Tasks 3 and 5; metrics `Prediction`, `fit_temperature`, `choose_thresholds`, `evaluate`; `check_gate`.
- Produces:
  - `train.load_splits(folder: Path, with_real: bool = False) -> tuple[RoleSpec, list[Record], list[Record], list[Record]]`
  - `train.new_version(kind: str = "encoder") -> str` (`v<UTC YYYYMMDDHHMM>` for encoder, `v<...>-<kind>` otherwise)
  - `train.new_package_dir(role_id: str, version: str) -> Path` (raises FileExistsError if it exists)
  - `train.package(*, folder, role, kind, base, prefix, labels, slots, train, dev, test, dev_preds, test_preds, curve, out, version) -> ModelCard` (temperature, thresholds, evaluate, gate, artifacts for `ARTIFACTS[kind]`, card, report)
  - `skills.knn.SCALE = 20.0`; `knn_logits(sims: np.ndarray, example_labels: np.ndarray, n_labels: int, k: int) -> list[float]`; `KnnClassifier(card, safety)`
  - `contenders.train_knn(folder: Path, embedding_model: str | None = None, k: int = 3, with_real: bool = False) -> ModelCard`

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/skills/test_knn.py
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
```

```python
# node/tests/learning/test_contenders.py
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.learning
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "role_tiny" / "skill"
TINY = "optimum-intel-internal-testing/tiny-random-xlm-roberta"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "skill")
    return tmp_path / "skill"


def test_knn_contender_packages_and_classifies(folder: Path) -> None:
    from mia.learning.contenders import train_knn
    from mia.learning.package import package_dir, verify_artifacts
    from mia.skills.knn import KnnClassifier

    card = train_knn(folder, embedding_model=TINY)
    assert card.kind == "knn" and card.version.endswith("-knn") and card.slots == {}
    verify_artifacts(card)
    assert sorted(p.name for p in package_dir("tiny", card.version).iterdir()) == [
        "card.json",
        "examples.json",
        "examples.npy",
        "model.onnx",
        "tokenizer.json",
    ]
    c = KnnClassifier(card, safety=set()).classify("sick today, cant come")
    assert c.intent in card.labels and c.version == card.version
    assert (folder / "reports" / f"{card.version}.md").exists()


def test_stale_intents_score_as_other(folder: Path) -> None:
    from mia.learning.contenders import train_knn

    test = folder / "data" / "test.jsonl"
    lines = test.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"tiny.absence"', '"tiny.removed_intent"', 1)
    test.write_text("\n".join(lines) + "\n", encoding="utf-8")
    card = train_knn(folder, embedding_model=TINY)
    assert "tiny.removed_intent" not in card.report.per_intent


def test_versions_differ_per_kind() -> None:
    from mia.learning.train import new_version

    assert new_version("knn").endswith("-knn")
    assert "-" not in new_version()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/skills/test_knn.py --no-cov -q`
Expected: FAIL (ModuleNotFoundError: mia.skills.knn)

- [ ] **Step 3: Implement**

`node/mia/skills/knn.py`:

```python
"""Nearest-examples classifier on the node: embed the message, compare with the package's
example matrix, score each label by its k most similar examples (spec embedding review 4B)."""

import json

import numpy as np
import onnxruntime
from tokenizers import Tokenizer

from mia.learning.package import ModelCard, package_dir, verify_artifacts
from mia.skills.runtime import Classification, ScoredClassifier, embed_text

SCALE = 20.0  # cosine to logit scale, so the card's temperature grid (0.5 to 5) fits


def knn_logits(sims: np.ndarray, example_labels: np.ndarray, n_labels: int, k: int) -> list[float]:
    """Per label: SCALE x mean of its k most similar examples; -SCALE for labels without one."""
    out = np.full(n_labels, -SCALE, dtype=np.float64)
    for label in np.unique(example_labels):
        top = np.sort(sims[example_labels == label])[::-1][:k]
        out[int(label)] = SCALE * float(top.mean())
    return [float(x) for x in out]


class KnnClassifier(ScoredClassifier):
    """Embedding model plus example matrix whose files match the card's digests."""

    def __init__(self, card: ModelCard, safety: set[str]) -> None:
        super().__init__(card, safety)
        verify_artifacts(card)
        folder = package_dir(card.role, card.version)
        self.session = onnxruntime.InferenceSession(
            str(folder / "model.onnx"), providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.examples = np.load(folder / "examples.npy")
        meta = json.loads((folder / "examples.json").read_text(encoding="utf-8"))
        self.example_labels = np.array(meta["labels"])
        self.k = int(meta["k"])

    def embed(self, text: str) -> np.ndarray:
        enc = self.tokenizer.encode(text)
        feeds = {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }
        return np.asarray(self.session.run(["embedding"], feeds)[0][0], dtype=np.float32)

    def classify(self, text: str, context: str = "") -> Classification:
        v = self.embed(embed_text(self.card.prefix, text, context))
        logits = knn_logits(self.examples @ v, self.example_labels, len(self.card.labels), self.k)
        return self.from_logits(logits, [], {})
```

In train.py, extract from `train_role` without changing its behaviour:

```python
def load_splits(
    folder: Path, with_real: bool = False
) -> tuple[RoleSpec, list[Record], list[Record], list[Record]]:
    """role.yaml and the three splits; with_real adds kept or fixed local candidates (D18)."""
    # body: the first lines of train_role up to and including the with_real block


def new_version(kind: str = "encoder") -> str:
    stamp = "v" + dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M")
    return stamp if kind == "encoder" else f"{stamp}-{kind}"


def new_package_dir(role_id: str, version: str) -> Path:
    out = get_settings().MIA_MODELS_DIR / role_id / version
    if out.exists():
        raise FileExistsError(f"{role_id}@{version} already exists; refusing to overwrite")
    return out


def package(
    *,
    folder: Path,
    role: RoleSpec,
    kind: str,
    base: str,
    prefix: str,
    labels: list[str],
    slots: dict[str, list[str]],
    train: list[Record],
    dev: list[Record],
    test: list[Record],
    dev_preds: list[Prediction],
    test_preds: list[Prediction],
    curve: dict[int, float],
    out: Path,
    version: str,
) -> ModelCard:
    """Calibrates on dev, evaluates on test, gates, hashes ARTIFACTS[kind] in out, writes the
    card and the report. The exported files must already be in out."""
    # body: temperature, thresholds, evaluate, gate, digest and card from train_role,
    # with kind=kind, prefix=prefix and artifacts over ARTIFACTS[kind]
```

`train_role` then calls `load_splits`, trains as today, computes its learning curve, takes `version = new_version()` and `out = new_package_dir(role.id, version)`, exports, and returns `package(...)`. `_report` prints the learning curve only when `curve` is not empty, and prints the kind.

`node/mia/learning/contenders.py`:

```python
"""Embedding contenders for the bake-off (spec embedding review section 4); learning group."""

import json
from pathlib import Path

import numpy as np

from mia.learning import catalogue
from mia.learning.embed import Embedder, export
from mia.learning.metrics import Prediction
from mia.learning.package import ModelCard
from mia.learning.schema import OTHER, Record
from mia.learning.train import load_splits, new_package_dir, new_version, package
from mia.skills.knn import knn_logits
from mia.skills.runtime import embed_text


def _label(r: Record, labels: list[str]) -> str:
    return r.intent if r.intent in labels else OTHER


def train_knn(
    folder: Path, embedding_model: str | None = None, k: int = 3, with_real: bool = False
) -> ModelCard:
    """Frozen embeddings of the train records as the example matrix; no slots, no language."""
    role, train, dev, test = load_splits(folder, with_real)
    labels = role.label_space([c.id for c in catalogue.conversation_intents()])
    name = embedding_model or role.embedding_model
    emb = Embedder(name)

    def vectors(rs: list[Record]) -> np.ndarray:
        return emb([embed_text("", r.text, r.context) for r in rs])  # Embedder adds the prefix

    x = vectors(train)
    index = {label: i for i, label in enumerate(labels)}
    ex_labels = np.array([index[_label(r, labels)] for r in train])

    def preds(rs: list[Record]) -> list[Prediction]:
        return [
            Prediction(
                record_id=r.id,
                intent=_label(r, labels),
                lang=r.lang,
                kind=r.kind,
                style=r.style,
                labels=labels,
                logits=knn_logits(x @ v, ex_labels, len(labels), k),
            )
            for r, v in zip(rs, vectors(rs), strict=True)
        ]

    version = new_version("knn")
    out = new_package_dir(role.id, version)
    export(emb.model, emb.tok, out)
    np.save(out / "examples.npy", x.astype(np.float32))
    (out / "examples.json").write_text(
        json.dumps({"labels": ex_labels.tolist(), "k": k}), encoding="utf-8"
    )
    return package(
        folder=folder,
        role=role,
        kind="knn",
        base=name,
        prefix=emb.prefix,
        labels=labels,
        slots={},
        train=train,
        dev=dev,
        test=test,
        dev_preds=preds(dev),
        test_preds=preds(test),
        curve={},
        out=out,
        version=version,
    )
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest node/tests/skills/test_knn.py --no-cov -q`
Expected: PASS
Run: `HF_HUB_DISABLE_IMPLICIT_TOKEN=1 uv run pytest -m learning --no-cov -q`
Expected: PASS (test_train unchanged, test_contenders new)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/train.py node/mia/learning/contenders.py node/mia/skills/knn.py node/tests/skills/test_knn.py node/tests/learning/test_contenders.py
git commit -m "learning: shared packaging; nearest-examples contender and its node classifier"
```

---

### Task 7: Contrastive contender

**Files:**
- Modify: `node/mia/learning/contenders.py` (`train_contrastive`)
- Test: `node/tests/learning/test_contenders.py` (marker `learning`), `node/tests/learning/test_contrastive_pairs.py` (default suite)

**Interfaces:**
- Consumes: Tasks 3, 5 and 6.
- Produces: `contenders.triplets(by_label: dict[str, list[str]], n: int, rng: random.Random) -> list[tuple[str, str, str]]` (pure, default suite); `contenders.train_contrastive(folder: Path, embedding_model: str | None = None, steps: int = 200, head_epochs: int = 50, seed: int = 0, with_real: bool = False) -> ModelCard`.

Put `triplets` in a module the default suite can import without torch: `node/mia/learning/pairs.py`, re-exported by contenders.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_contrastive_pairs.py
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
```

```python
# node/tests/learning/test_contenders.py (append)
def test_contrastive_contender_packages_and_runs_on_onnx(folder: Path) -> None:
    from mia.learning.contenders import train_contrastive
    from mia.skills.onnx import OnnxClassifier

    card = train_contrastive(folder, embedding_model=TINY, steps=4, head_epochs=2)
    assert card.kind == "contrastive" and card.version.endswith("-contrastive")
    c = OnnxClassifier(card, safety=set()).classify("sick today, cant come")
    assert c.intent in card.labels and c.lang is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/learning/test_contrastive_pairs.py --no-cov -q`
Expected: FAIL (ModuleNotFoundError: mia.learning.pairs)

- [ ] **Step 3: Implement**

```python
# node/mia/learning/pairs.py
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
```

Append to contenders.py:

```python
import random

import torch
from torch import nn

from mia.learning.pairs import triplets


class _Classify(nn.Module):  # type: ignore[misc,unused-ignore]
    def __init__(self, pooled: nn.Module, head: nn.Module) -> None:
        super().__init__()
        self.pooled = pooled
        self.head = head

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        return self.head(self.pooled(input_ids, attention_mask))


def train_contrastive(
    folder: Path,
    embedding_model: str | None = None,
    steps: int = 200,
    head_epochs: int = 50,
    seed: int = 0,
    with_real: bool = False,
) -> ModelCard:
    """SetFit method without the library: triplet fine-tune of the embedding model on train,
    then a linear head on the frozen tuned embeddings. One output, intent_logits."""
    role, train, dev, test = load_splits(folder, with_real)
    labels = role.label_space([c.id for c in catalogue.conversation_intents()])
    name = embedding_model or role.embedding_model
    emb = Embedder(name)
    rng = random.Random(seed)
    torch.manual_seed(seed)
    by_label: dict[str, list[str]] = {}
    for r in train:
        by_label.setdefault(_label(r, labels), []).append(embed_text("", r.text, r.context))
    opt = torch.optim.AdamW(emb.model.parameters(), lr=2e-5)
    loss_fn = nn.TripletMarginWithDistanceLoss(
        distance_function=lambda a, b: 1 - nn.functional.cosine_similarity(a, b), margin=0.3
    )
    emb.model.train()
    for _ in range(steps):
        batch = triplets(by_label, 16, rng)
        if not batch:
            break
        a, p, n = (emb.model(**emb.encode(list(col))) for col in zip(*batch, strict=True))
        loss = loss_fn(a, p, n)
        opt.zero_grad()
        loss.backward()
        opt.step()
    emb.model.eval()
    index = {label: i for i, label in enumerate(labels)}

    def vectors(rs: list[Record]) -> torch.Tensor:
        return torch.from_numpy(emb([embed_text("", r.text, r.context) for r in rs]))

    x = vectors(train)
    y = torch.tensor([index[_label(r, labels)] for r in train])
    head = nn.Linear(x.shape[1], len(labels))
    hopt = torch.optim.Adam(head.parameters(), lr=1e-2)
    for _ in range(head_epochs):
        hl = nn.functional.cross_entropy(head(x), y)
        hopt.zero_grad()
        hl.backward()
        hopt.step()
    head.eval()

    def preds(rs: list[Record]) -> list[Prediction]:
        with torch.no_grad():
            logits = head(vectors(rs))
        return [
            Prediction(
                record_id=r.id,
                intent=_label(r, labels),
                lang=r.lang,
                kind=r.kind,
                style=r.style,
                labels=labels,
                logits=row.tolist(),
            )
            for r, row in zip(rs, logits, strict=True)
        ]

    version = new_version("contrastive")
    out = new_package_dir(role.id, version)
    export(_Classify(emb.model, head), emb.tok, out, output="intent_logits")
    return package(
        folder=folder,
        role=role,
        kind="contrastive",
        base=name,
        prefix=emb.prefix,
        labels=labels,
        slots={},
        train=train,
        dev=dev,
        test=test,
        dev_preds=preds(dev),
        test_preds=preds(test),
        curve={},
        out=out,
        version=version,
    )
```

Note: `Embedder.encode` adds the prefix; the ONNX runtime path adds it through `embed_text(card.prefix, ...)` (Task 5), so training and serving see the same string.

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest node/tests/learning/test_contrastive_pairs.py --no-cov -q`
Expected: PASS
Run: `HF_HUB_DISABLE_IMPLICIT_TOKEN=1 uv run pytest -m learning --no-cov -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/pairs.py node/mia/learning/contenders.py node/tests/learning/test_contrastive_pairs.py node/tests/learning/test_contenders.py
git commit -m "learning: contrastive contender (triplet fine-tune plus linear head)"
```

---

### Task 8: `--kind` on train and `mia skills bakeoff`

**Files:**
- Modify: `node/mia/learning/contenders.py` (`bakeoff`, `choose_winner`, `render_bakeoff`), `node/mia/learning/commands.py` (`train --kind`, `--embedding-model`; `bakeoff_cmd`)
- Create: `node/mia/learning/bakeoff.py` (pure `choose_winner` and `render_bakeoff`, default suite)
- Test: `node/tests/learning/test_bakeoff.py` (default suite), `node/tests/learning/test_commands.py` (append), `node/tests/learning/test_contenders.py` (append, learning)

**Interfaces:**
- Consumes: Tasks 6 and 7, `train_role`.
- Produces: `bakeoff.choose_winner(cards: list[ModelCard], role_has_slots: bool) -> ModelCard | None` (gate passed; encoder only when the role has slot intents; highest macro F1, then coverage); `bakeoff.render_bakeoff(cards, winner, latency_ms: dict[str, float]) -> str`; `contenders.bakeoff(folder: Path) -> tuple[list[ModelCard], ModelCard | None]` (writes `reports/bakeoff-<UTC>.md`, promotes nothing); CLI `mia skills train <role> [--kind encoder|knn|contrastive] [--embedding-model M]`, `mia skills bakeoff <role>`.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_bakeoff.py
from mia.learning.bakeoff import choose_winner, render_bakeoff
from tests.learning.helpers import card


def scored(kind: str, f1: float, cov: float, passed: bool = True):  # type: ignore[no-untyped-def]
    c = card(version=f"v1-{kind}")
    return c.model_copy(
        update={
            "kind": kind,
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


def test_failed_gate_never_wins_and_slots_keep_the_encoder() -> None:
    a, b = scored("encoder", 0.8, 0.8), scored("knn", 0.99, 0.99)
    assert choose_winner([a, b], role_has_slots=True) is a
    assert choose_winner([scored("knn", 0.99, 0.99, passed=False)], role_has_slots=False) is None


def test_render_has_one_row_per_contender_and_names_the_winner() -> None:
    a, b = scored("encoder", 0.9, 0.8), scored("knn", 0.85, 0.9)
    text = render_bakeoff([a, b], a, {a.version: 21.0, b.version: 9.5})
    assert "| encoder | v1-encoder | 0.900 | 0.800 |" in text
    assert "| knn | v1-knn | 0.850 | 0.900 |" in text
    assert "Winner: encoder v1-encoder" in text
    assert "No contender is promoted by the bake-off" in text
```

(Adapt the row format in the assertion to the exact columns you render: kind, version, macro F1, coverage, accuracy, ECE, safety recall, gate, ms per message.)

```python
# node/tests/learning/test_commands.py (append)
def test_train_kind_dispatches_to_the_contender(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import types

    from mia.learning import commands
    from tests.learning.helpers import card

    calls: list[tuple[str, str | None]] = []

    def knn(folder: Path, embedding_model: str | None = None, with_real: bool = False):  # type: ignore[no-untyped-def]
        calls.append(("knn", embedding_model))
        return card()

    fake = types.SimpleNamespace(train_knn=knn, train_contrastive=knn)
    real = commands.import_module
    monkeypatch.setattr(
        commands, "import_module", lambda n: fake if n == "mia.learning.contenders" else real(n)
    )
    assert main(["skills", "train", "dispatcher", "--kind", "knn", "--embedding-model", "m"]) == 0
    assert calls == [("knn", "m")]
    assert capsys.readouterr().out.splitlines()[0] == "r@v1: gate passed"
```

(Adjust the expected gate line to what the shared `card()` helper produces: role, version and gate state.)

```python
# node/tests/learning/test_contenders.py (append)
def test_bakeoff_trains_three_and_writes_the_report(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia.learning import contenders

    monkeypatch.setattr(contenders, "EMBEDDING_OVERRIDE", TINY)  # tiny model in tests
    cards, winner = contenders.bakeoff(folder, encoder_epochs=1, contrastive_steps=4)
    assert [c.kind for c in cards] == ["encoder", "knn", "contrastive"]
    reports = list((folder / "reports").glob("bakeoff-*.md"))
    assert len(reports) == 1
```

Implement `bakeoff(folder, encoder_epochs=20, contrastive_steps=200)` with a module-level `EMBEDDING_OVERRIDE: str | None = None` used as the embedding model when set (tests only); document it.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/learning/test_bakeoff.py --no-cov -q`
Expected: FAIL (ModuleNotFoundError: mia.learning.bakeoff)

- [ ] **Step 3: Implement**

```python
# node/mia/learning/bakeoff.py
"""Bake-off decision and report (pure; spec embedding review section 4)."""

from mia.learning.package import ModelCard


def choose_winner(cards: list[ModelCard], role_has_slots: bool) -> ModelCard | None:
    """Best macro F1, then coverage, among cards that passed the gate. A role with slot intents
    keeps the encoder (the only kind with slot heads)."""
    ok = [c for c in cards if c.gate.passed and (c.kind == "encoder" or not role_has_slots)]
    return max(ok, key=lambda c: (c.report.macro_f1, c.report.coverage), default=None)


def render_bakeoff(
    cards: list[ModelCard], winner: ModelCard | None, latency_ms: dict[str, float]
) -> str:
    rows = [
        "| kind | version | macro F1 | coverage | accuracy | ECE | safety recall | gate | ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cards:
        r = c.report
        rows.append(
            f"| {c.kind} | {c.version} | {r.macro_f1:.3f} | {r.coverage:.3f} | {r.accuracy:.3f} "
            f"| {r.ece:.3f} | {r.safety_recall:.3f} | {'passed' if c.gate.passed else 'failed'} "
            f"| {latency_ms.get(c.version, float('nan')):.1f} |"
        )
    head = f"Winner: {winner.kind} {winner.version}" if winner else "Winner: none passed the gate"
    return "\n".join(
        [
            "# Bake-off",
            "",
            head,
            "",
            *rows,
            "",
            "No contender is promoted by the bake-off; promote the winner with "
            "`mia skills promote <role> <version> --signed-by NAME` after Gate 2.",
            "",
        ]
    )
```

In contenders.py:

```python
import datetime as dt
import statistics
import time

from mia.learning.bakeoff import choose_winner, render_bakeoff
from mia.learning.schema import load_role
from mia.learning.train import train_role

EMBEDDING_OVERRIDE: str | None = None  # tests set a tiny model; production uses role.yaml


def _latency_ms(card: ModelCard, texts: list[str]) -> float:
    from mia.skills.knn import KnnClassifier
    from mia.skills.onnx import OnnxClassifier

    clf = KnnClassifier(card, set()) if card.kind == "knn" else OnnxClassifier(card, set())
    times = []
    for t in texts[:20]:
        start = time.perf_counter()
        clf.classify(t)
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times) if times else float("nan")


def bakeoff(
    folder: Path, encoder_epochs: int = 20, contrastive_steps: int = 200
) -> tuple[list[ModelCard], ModelCard | None]:
    """Trains the encoder, nearest-examples and contrastive contenders on the same splits and
    writes reports/bakeoff-<UTC>.md. Promotes nothing."""
    role = load_role(folder / "role.yaml")
    model = EMBEDDING_OVERRIDE or role.embedding_model
    cards = [
        train_role(
            folder,
            base_model=EMBEDDING_OVERRIDE,
            epochs=encoder_epochs,
            seeds=(0,) if EMBEDDING_OVERRIDE else (0, 1, 2),
        ),
        train_knn(folder, embedding_model=model),
        train_contrastive(folder, embedding_model=model, steps=contrastive_steps),
    ]
    winner = choose_winner(cards, role_has_slots=any(i.slots for i in role.intents))
    _, _, _, test = load_splits(folder)
    latency = {c.version: _latency_ms(c, [r.text for r in test]) for c in cards}
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M")
    (folder / "reports").mkdir(exist_ok=True)
    (folder / "reports" / f"bakeoff-{stamp}.md").write_text(
        render_bakeoff(cards, winner, latency), encoding="utf-8"
    )
    return cards, winner
```

In commands.py: `train` gains `--kind` (choices encoder, knn, contrastive; default encoder) and `--embedding-model`; encoder uses `mia.learning.train.train_role` as today; knn and contrastive call `mia.learning.contenders.train_knn` / `train_contrastive` (through `_learning_module`, with `with_real`). Add:

```python
def bakeoff_cmd(args: argparse.Namespace) -> int:
    """Trains every contender for the role and writes the comparison; promotes nothing."""
    module = _learning_module("mia.learning.contenders")
    if module is None:
        return 2
    cards, winner = module.bakeoff(skill_dir(args.role))  # type: ignore[attr-defined]
    for c in cards:
        print(
            f"{c.kind} {c.version}: macro F1 {c.report.macro_f1:.3f}, gate "
            f"{'passed' if c.gate.passed else 'failed'}"
        )
    print(f"winner: {winner.kind} {winner.version}" if winner else "winner: none")
    return 0
```

and register `bakeoff` with a positional `role`.

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest node/tests/learning --no-cov -q`
Expected: PASS
Run: `HF_HUB_DISABLE_IMPLICIT_TOKEN=1 uv run pytest -m learning --no-cov -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/bakeoff.py node/mia/learning/contenders.py node/mia/learning/commands.py node/tests/learning/test_bakeoff.py node/tests/learning/test_commands.py node/tests/learning/test_contenders.py
git commit -m "learning: train --kind and mia skills bakeoff"
```

---

### Task 9: Skill, spec and docs

**Files:**
- Modify: `.claude/skills/mia-train-role/SKILL.md`, `.claude/skills/mia-train-role/guidelines.md`, `.claude/skills/mia-train-role/prompts/reviewer.md`
- Modify: `docs/superpowers/specs/2026-10-06-embedding-review-design.md` (status accepted, calibrated values), `docs/decisions.md` (next D number), `README.md` (commands)
- Test: `node/tests/learning/test_skill_files.py`

- [ ] **Step 1: Write the failing test**

```python
# node/tests/learning/test_skill_files.py (append)
def test_skill_runs_overlap_and_bakeoff() -> None:
    text = (SKILL / "SKILL.md").read_text()
    for marker in (
        "mia skills overlap",
        "mia skills bakeoff",
        "merge candidate",
        "split candidate",
        "narrow candidate",
    ):
        assert marker in text
```

The existing flag test checks every `mia skills <cmd> --flag` in SKILL.md against the parser, so the new commands must be written with real flags.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/learning/test_skill_files.py --no-cov -q`
Expected: FAIL

- [ ] **Step 3: Edit the docs**

- SKILL.md, "Overlap review": run `uv run mia skills overlap <role>` and show its candidates table at Gate 1 next to the D30 table: a merge candidate (an intent whose sub-clusters overlap other intents) is a merge or sharpen decision, a split candidate is a split decision, a narrow candidate moves that sub-cluster's records to the narrower intent after review. Repeat after the data review. Nothing is relabelled automatically.
- SKILL.md, training step: `uv run mia skills bakeoff <role>` trains the encoder, nearest-examples and contrastive contenders and writes reports/bakeoff-<UTC>.md; Gate 2 reviews the winner; `uv run mia skills train <role> --kind knn` builds a starting classifier for a new role from reviewed synthetic data (it then replaces the regex hint for that role once promoted, D28 A).
- guidelines.md: one paragraph on the three contenders and when each wins (encoder for slots and fine-grained look-alikes; nearest-examples for new roles and fast iteration; contrastive for few examples per intent).
- reviewer.md: suspect labels and paraphrases from the overlap report are listed for the developer, never relabelled.
- Spec addition: Status "accepted"; the calibrated thresholds and recall from Task 4.
- decisions.md: next D number: embedding overlap review and the three-contender bake-off; default embedding model; no new dependency.
- README.md: add `mia skills overlap <role>` and `mia skills bakeoff <role>` to the Role skill models commands.

- [ ] **Step 4: Run the checks**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy node/mia && uv run pytest -q`
Expected: PASS
Run: `HF_HUB_DISABLE_IMPLICIT_TOKEN=1 uv run pytest -m learning --no-cov -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/mia-train-role docs README.md node/tests/learning/test_skill_files.py
git commit -m "skill and docs: overlap review and bake-off"
```

---

## Self-review notes

- Spec coverage: section 2 (Task 3 embedder, Task 6/7 runtime on onnxruntime), section 3 items 1 to 4 (Task 1), item 5 (Task 1 render, Task 9 skill), calibration (Tasks 2 and 4), section 4 A/B/C (existing, Tasks 6, 7), runtime through ScoredClassifier (Tasks 5, 6), starting classifier (Tasks 8 and 9: `train --kind knn`), section 5 out of scope respected (no SetFit, sklearn, HDBSCAN, no automatic relabelling), section 6 open items resolved in Task 4 (thresholds) and left to the Task 19 bake-off (model choice).
- Types used across tasks: `Item`, `Thresholds`, `OverlapReport`, `ModelCard.kind`/`prefix`, `ARTIFACTS`, `embed_text`, `knn_logits`, `SCALE`, `load_splits`, `new_version`, `new_package_dir`, `package`, `train_knn`, `train_contrastive`, `triplets`, `choose_winner`, `render_bakeoff`, `bakeoff`.
- Context: knn and contrastive embed `text\ncontext` as one string; the encoder keeps its pair encoding.
- Language: knn and contrastive have no language head; `Classification.lang` is None for them (chat uses detect_language for replies).

## Amendments (2026-10-06, after Task 4)

Task 4 found that raw centroid cosines are compressed (e5-small: median intent pair 0.94, the
reviewed pairs 0.96 to 0.98), so no fixed threshold separates them, and that the reference review
was not exhaustive (the owner confirmed 6 of the top 10 unreviewed pairs as real). Rulings are in
the research note docs/research/overlap-calibration-2026-10-06.md.

### A1: Task 1 becomes a ranked, centred review aid (fix round 2 of Task 1)

- `centre(emb: np.ndarray) -> np.ndarray`: subtract the mean row, re-normalise rows (zero rows
  stay zero). `analyse(items, emb, th, centred: bool = True)` centres first; every intent-level
  signal (centroids, sub-clusters, suspects) uses centred rows. Record-level paraphrases keep the
  raw rows and the 0.95 threshold (near-duplicate texts are a raw-scale property).
- Pairs are ranked, not thresholded. `Thresholds` loses `close_pair`, `overlap` and `split` and
  gains `top_pairs: int = 50`, `nearest: int = 2`, `link_percentile: float = 75.0`.
  `OverlapReport.ranked: list[Pair]` is the top `top_pairs` intent pairs by centred centroid
  cosine, descending. `OverlapReport.nearest: dict[str, list[Pair]]` is each intent's `nearest`
  closest intents. `close_pairs` stays as the union of both (so found_pairs and recall work).
- Sub-cluster rules are relative to the data: the link threshold for `_groups` is the
  `link_percentile` of all within-intent pairwise centred similarities in the dataset (computed
  once per analyse, exposed as `OverlapReport.link_threshold`); a sub-cluster "overlaps" another
  intent when its centroid is closer to that intent's centroid than to its own intent's; two
  sub-clusters are "far" when their centroids' centred cosine is below 0. Merge, narrow and split
  keep their definitions over these relations (narrow still requires the other intent to be
  tighter by `_spread`).
- `calibrate` is removed. `recall_at(items, emb, expected, ks: tuple[int, ...] = (40, 80, 120))
  -> dict[int, float]` ranks all intent pairs by centred centroid cosine and returns recall of
  `expected` within the top k for each k. `found_pairs`, `recall`, `unfindable` and
  `review_pairs` stay.
- `render` sections: "Ranked pairs (top N)", "Nearest intents" (intent | 1st (sim) | 2nd (sim)),
  "Suspect labels", "Paraphrases across intents" (showing N of M), "Candidates", then
  "Link threshold: x (p75 of within-intent similarity)".
- Tests to change or add (exact values): centring on rows that share a common offset separates
  them (an uncentred pair above 0.9 falls below 0.5 after centring); ranked order and length;
  nearest per intent with ties broken by name; link threshold equals the numpy percentile of the
  within-intent pairs of a 3-intent fixture; merge, narrow and split under the relative rules
  (including "closer to its own intent" giving no candidate); recall_at exact values for a
  fixture with 3 expected pairs at ranks 1, 3 and 50.

### A2: Task 3 command

`--calibrate` is removed. With `--expect`, the command prints the unfindable line, then
`recall@40 x.xx, recall@80 x.xx, recall@120 x.xx (N findable pairs)`, and appends the same to the
report. Tests adapt (the fake embedder fixtures give deterministic ranks).

### A3: Task 4 rerun (operational)

- Reference file: create `docs/research/intent-overlap-reference.md` with a "## Decisions"
  table (parsed by `review_pairs`) holding the 40 review pairs plus the 6 owner-confirmed pairs
  (listed in the calibration note), and a "## Not overlaps" table of the 4 owner-rejected pairs
  (not parsed; kept so they are not re-asked).
- Run `mia skills overlap --dataset <pre-review 8fee0ac dataset> --expect
  docs/research/intent-overlap-reference.md` with e5-small (and bge-m3 if cached); record
  recall@40/80/120 in the calibration note (reference numbers, not a bar) and the top 10 pairs
  with their rank.
- Acceptance is the owner-judged precision at top 10 already recorded (6/10). Nothing is pinned.
- Then a targeted run on the conversation intents only (dataset records labelled conversation.*
  plus conversation.yaml examples, `--no-conversation` off) and a list of the top 15
  conversation pairs for the owner, each with two example texts; merges there are the owner's
  decision (conversation.emergency / hazard_report is sharpened, not merged).

### A4: Task 9

The skill shows the ranked list and the nearest-intents table at Gate 1 and, after the bake-off,
the winner's confusion list next to it (the classifier's confusions are the authoritative
overlap signal). guidelines.md adds the "same action?" test: a flagged pair that shares a topic
but names a different action (add vs update, book vs change) is not an overlap.
