"""Intent overlap from sentence embeddings (numpy only; spec embedding review section 3).

Rows of `emb` are unit vectors, one per Item, in the same order. Nothing here relabels data: the
report lists signals and suggested decisions for the developer (D30 rules)."""

import re
from collections import Counter, defaultdict
from itertools import combinations, product
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


_DEFAULTS = Thresholds()
MAX_PARAPHRASES = 200


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
    paraphrases: list[Paraphrase] = []  # at most MAX_PARAPHRASES, most similar first
    paraphrase_total: int = 0
    paraphrase_intent_pairs: list[list[str]] = []  # every linked intent pair, uncapped
    clusters: dict[str, list[SubCluster]] = {}
    candidates: list[Candidate] = []


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.asarray(v / np.where(n == 0, 1, n), dtype=np.float32)


def _groups(idx: list[int], emb: np.ndarray, th: Thresholds) -> list[list[int]]:
    """Sub-clusters of one intent, largest first; small ones join the largest."""
    uf = _UnionFind(len(idx))
    sims = emb[idx] @ emb[idx].T
    for i, j in np.argwhere(np.triu(sims >= th.cluster, 1)):
        uf.union(int(i), int(j))
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


def analyse(items: list[Item], emb: np.ndarray, th: Thresholds = _DEFAULTS) -> OverlapReport:
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
        top = np.sort(np.argpartition(row, -k)[-k:])
        counts = Counter(items[j].intent for j in top)
        label, count = counts.most_common(1)[0]
        if count > counts[it.intent] and count / k >= th.suspect_share:
            rep.suspects.append(
                Suspect(
                    id=it.id,
                    intent=it.intent,
                    text=it.text,
                    neighbours_label=label,
                    share=round(count / k, 3),
                )
            )
    lab = np.array([it.intent for it in items])
    found = np.argwhere(np.triu(sims >= th.paraphrase, 1) & (lab[:, None] != lab[None, :]))
    rep.paraphrase_total = len(found)
    if len(found):
        both = np.sort(np.stack([lab[found[:, 0]], lab[found[:, 1]]], axis=1), axis=1)
        rep.paraphrase_intent_pairs = np.unique(both, axis=0).tolist()
    ordered = sorted(found.tolist(), key=lambda ij: -sims[ij[0], ij[1]])[:MAX_PARAPHRASES]
    for i, j in ordered:
        (a_int, a_id), (b_int, b_id) = sorted(
            [(items[i].intent, items[i].id), (items[j].intent, items[j].id)]
        )
        rep.paraphrases.append(
            Paraphrase(
                a_id=a_id,
                a_intent=a_int,
                b_id=b_id,
                b_intent=b_int,
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
    out += ["", "## Paraphrases across intents", ""]
    out += [f"Showing {len(report.paraphrases)} of {report.paraphrase_total}.", ""]
    out += ["| a | b | similarity |", "|---|---|---|"]
    out += [
        f"| {p.a_id} ({p.a_intent}) | {p.b_id} ({p.b_intent}) | {p.similarity} |"
        for p in report.paraphrases
    ]
    out += ["", "## Candidates", "", "| intent | kind | others | reason |", "|---|---|---|---|"]
    out += [
        f"| {c.intent} | {c.kind} | {', '.join(c.others)} | {c.reason} |" for c in report.candidates
    ]
    return "\n".join(out) + "\n"


def _intent_id(token: str) -> str:
    token = token.strip().strip("*`")
    return token if "." in token else f"conversation.{token}"


def review_pairs(markdown: str) -> set[frozenset[str]]:
    """Intent pairs named in the first column of the "## Decisions" table of a review document
    ("a / b, c" means a with b and a with c; "a / b / c" means every pair of a, b and c).
    Parenthesised text and bold markers in the cell are ignored; bare kb_* names are conversation
    intents."""
    pairs: set[frozenset[str]] = set()
    section = markdown.split("## Decisions", 1)[-1].split("\n## ", 1)[0]
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or "/" not in cells[0] or cells[0].startswith("Pair"):
            continue
        first = re.sub(r"\([^)]*\)", "", cells[0]).replace("**", "")
        sides = [[_intent_id(t) for t in part.split(",")] for part in first.split(" / ")]
        if len(sides) == 2:
            pairs |= {frozenset({a, b}) for a, b in product(sides[0], sides[1]) if a != b}
        else:
            flat = [x for side in sides for x in side]
            pairs |= {frozenset({a, b}) for a, b in combinations(flat, 2) if a != b}
    return pairs


def found_pairs(report: OverlapReport) -> set[frozenset[str]]:
    """Every intent pair any signal links: close pairs, paraphrases, suspects and candidates."""
    found = {frozenset({p.a, p.b}) for p in report.close_pairs}
    found |= {frozenset(p) for p in report.paraphrase_intent_pairs}
    found |= {frozenset({s.intent, s.neighbours_label}) for s in report.suspects}
    found |= {frozenset({c.intent, o}) for c in report.candidates for o in c.others}
    return found


def unfindable(expected: set[frozenset[str]], intents: set[str]) -> set[frozenset[str]]:
    """Expected pairs that name an intent with no items, which no signal can ever find."""
    return {pair for pair in expected if not pair <= intents}


def recall(report: OverlapReport, expected: set[frozenset[str]]) -> float:
    """Share of the expected pairs that the report links; 1.0 when nothing is expected."""
    return len(expected & found_pairs(report)) / len(expected) if expected else 1.0


def calibrate(
    items: list[Item], emb: np.ndarray, expected: set[frozenset[str]], budget: float = 3.0
) -> tuple[Thresholds, float]:
    """Grid search for the thresholds with the best recall whose flagged pairs stay within
    budget x len(expected) (flagging everything would score 1.0); ties keep the stricter grid
    point (fewer flags). Returns the default thresholds and 0.0 when no grid point fits."""
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
