"""Intent overlap from sentence embeddings (numpy only; spec embedding review section 3).

Rows of `emb` are unit vectors, one per Item, in the same order. Raw cosines are compressed (most
intent pairs sit near 0.94), so intent-level signals use mean-centred rows and pairs are ranked,
not thresholded: the report is a ranked review aid, not a gate. Nothing here relabels data: the
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
    paraphrase: float = 0.95  # raw record cosine across intents (near-duplicate texts)
    link_percentile: float = 75.0  # of within-intent similarities; links records of one intent
    min_cluster: int = 3  # smaller sub-clusters join the intent's main group
    k: int = 10  # neighbours for suspect labels
    suspect_share: float = 0.6  # share of neighbours with one other label
    top_pairs: int = 50  # intent pairs in the ranked list
    nearest: int = 2  # closest intents listed per intent


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
    nearest: str | None  # another intent this sub-cluster is closer to than its own
    similarity: float


class Candidate(BaseModel):
    intent: str
    kind: Literal["merge", "split", "narrow"]
    others: list[str]
    reason: str


class OverlapReport(BaseModel):
    ranked: list[Pair] = []  # top intent pairs by centroid cosine, most similar first
    nearest: dict[str, list[Pair]] = {}  # per intent (as a), its closest intents (as b)
    close_pairs: list[Pair] = []  # union of ranked and nearest, a < b, most similar first
    suspects: list[Suspect] = []
    paraphrases: list[Paraphrase] = []  # at most MAX_PARAPHRASES, most similar first
    paraphrase_total: int = 0
    paraphrase_intent_pairs: list[list[str]] = []  # every linked intent pair, uncapped
    clusters: dict[str, list[SubCluster]] = {}
    candidates: list[Candidate] = []
    link_threshold: float = 1.0
    link_percentile: float = 75.0


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.asarray(v / np.where(n == 0, 1, n), dtype=np.float32)


def centre(emb: np.ndarray) -> np.ndarray:
    """Rows minus the mean row, re-normalised to unit length (zero rows stay zero). Removes the
    offset all texts share, which compresses raw cosines; empty input comes back empty."""
    if len(emb) == 0:
        return np.asarray(emb, dtype=np.float32)
    return _unit(emb - emb.mean(axis=0))


def _by_intent(items: list[Item]) -> dict[str, list[int]]:
    by: dict[str, list[int]] = defaultdict(list)
    for i, it in enumerate(items):
        by[it.intent].append(i)
    return by


def _pair_sims(items: list[Item], rows: np.ndarray) -> tuple[list[str], np.ndarray]:
    """Sorted intent names and the cosine matrix of their centroids over `rows`."""
    by = _by_intent(items)
    names = sorted(by)
    cent = np.array([_unit(rows[by[n]].mean(axis=0)) for n in names], dtype=np.float32)
    return names, cent @ cent.T


def _ranked(names: list[str], sims: np.ndarray) -> list[Pair]:
    """Every pair of distinct intents (a < b), most similar first, ties by a then b."""
    i, j = np.triu_indices(len(names), 1)
    order = np.lexsort((j, i, -sims[i, j]))
    return [
        Pair(a=names[i[t]], b=names[j[t]], similarity=round(float(sims[i[t], j[t]]), 3))
        for t in order
    ]


def _groups(idx: list[int], rows: np.ndarray, link: float, min_cluster: int) -> list[list[int]]:
    """Sub-clusters of one intent (records linked at similarity >= link), largest first; groups
    under min_cluster join the largest."""
    uf = _UnionFind(len(idx))
    sims = rows[idx] @ rows[idx].T
    for i, j in np.argwhere(np.triu(sims >= link, 1)):
        uf.union(int(i), int(j))
    by_root: dict[int, list[int]] = defaultdict(list)
    for i, item in enumerate(idx):
        by_root[uf.find(i)].append(item)
    groups = sorted(by_root.values(), key=len, reverse=True)
    big = [g for g in groups if len(g) >= min_cluster]
    if not big:
        return [idx]
    for g in groups:
        if len(g) < min_cluster:
            big[0] = big[0] + g
    return big


def _link_threshold(groups: list[list[int]], rows: np.ndarray, percentile: float) -> float:
    """The percentile of every within-intent pairwise similarity (self pairs excluded); 1.0 when
    no intent has two records."""
    vals = [(rows[g] @ rows[g].T)[np.triu_indices(len(g), 1)] for g in groups]
    flat = np.concatenate(vals)
    return float(np.percentile(flat, percentile)) if flat.size else 1.0


def _spread(rows: np.ndarray) -> float:
    return float(1 - (rows @ _unit(rows.mean(axis=0))).mean())


def _suspects(items: list[Item], rows: np.ndarray, th: Thresholds) -> list[Suspect]:
    """Records whose k nearest neighbours mostly carry one other label (strictly more than
    their own and at least suspect_share of k)."""
    sims = rows @ rows.T
    k = min(th.k, len(items) - 1)
    out: list[Suspect] = []
    for i, it in enumerate(items):
        if k <= 0:
            break
        row = sims[i].copy()
        row[i] = -np.inf
        top = np.sort(np.argpartition(row, -k)[-k:])
        counts = Counter(items[j].intent for j in top)
        label, count = counts.most_common(1)[0]
        if count > counts[it.intent] and count / k >= th.suspect_share:
            out.append(
                Suspect(
                    id=it.id,
                    intent=it.intent,
                    text=it.text,
                    neighbours_label=label,
                    share=round(count / k, 3),
                )
            )
    return out


def _paraphrases(items: list[Item], emb: np.ndarray, th: Thresholds, rep: OverlapReport) -> None:
    """Fills the paraphrase fields from raw record cosines >= th.paraphrase across intents."""
    sims = emb @ emb.T
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


def _candidate(
    n: str,
    groups: list[list[int]],
    subs: list[SubCluster],
    rows: np.ndarray,
    by: dict[str, list[int]],
) -> Candidate | None:
    """Merge when two or more sub-clusters sit closer to other intents; narrow when one does and
    that intent is tighter; split when none does and two sub-clusters are far (cosine < 0)."""
    hits = [s.nearest for s in subs if s.nearest]
    if len(hits) >= 2:
        reason = f"{len(hits)} sub-clusters overlap other intents"
        return Candidate(intent=n, kind="merge", others=sorted(set(hits)), reason=reason)
    if len(hits) == 1:
        other = hits[0]
        if len(subs) >= 2 and _spread(rows[by[other]]) < _spread(rows[by[n]]):
            reason = f"one sub-cluster fits the narrower {other}"
            return Candidate(intent=n, kind="narrow", others=[other], reason=reason)
        return None
    gcent = np.array([_unit(rows[g].mean(axis=0)) for g in groups])
    if len(groups) >= 2 and float((gcent @ gcent.T).min()) < 0:
        reason = f"{len(groups)} distant sub-clusters"
        return Candidate(intent=n, kind="split", others=[], reason=reason)
    return None


def analyse(
    items: list[Item], emb: np.ndarray, th: Thresholds = _DEFAULTS, centred: bool = True
) -> OverlapReport:
    """Ranked intent pairs, nearest intents, suspect labels, cross-intent paraphrases and
    per-intent sub-clusters with merge, split and narrow candidates. Intent-level signals use
    centred rows (unless centred=False); paraphrases use the raw rows. Empty input gives an
    empty report."""
    if not items:
        return OverlapReport(link_percentile=th.link_percentile)
    rows = centre(emb) if centred else emb
    by = _by_intent(items)
    names, psims = _pair_sims(items, rows)
    rep = OverlapReport(
        ranked=_ranked(names, psims)[: th.top_pairs],
        link_percentile=th.link_percentile,
        suspects=_suspects(items, rows, th),
    )
    close = {frozenset({p.a, p.b}): p for p in rep.ranked}
    for x, n in enumerate(names):
        near = sorted((-float(psims[x, y]), names[y]) for y in range(len(names)) if y != x)
        rep.nearest[n] = [Pair(a=n, b=b, similarity=round(-s, 3)) for s, b in near[: th.nearest]]
        for p in rep.nearest[n]:
            close.setdefault(
                frozenset({n, p.b}), Pair(a=min(n, p.b), b=max(n, p.b), similarity=p.similarity)
            )
    rep.close_pairs = sorted(close.values(), key=lambda p: (-p.similarity, p.a, p.b))
    _paraphrases(items, emb, th, rep)
    rep.link_threshold = _link_threshold(list(by.values()), rows, th.link_percentile)
    cent = {n: _unit(rows[by[n]].mean(axis=0)) for n in names}
    for n in names:
        groups = _groups(by[n], rows, rep.link_threshold, th.min_cluster)
        subs: list[SubCluster] = []
        for g in groups:
            gc = _unit(rows[g].mean(axis=0))
            others = [(-float(gc @ cent[o]), o) for o in names if o != n]
            neg, best = min(others) if others else (0.0, None)
            subs.append(
                SubCluster(
                    size=len(g),
                    examples=[items[i].text for i in g[:3]],
                    nearest=best if -neg > float(gc @ cent[n]) else None,
                    similarity=round(-neg, 3),
                )
            )
        rep.clusters[n] = subs
        cand = _candidate(n, groups, subs, rows, by)
        if cand:
            rep.candidates.append(cand)
    return rep


def _ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def render(report: OverlapReport) -> str:
    """Markdown with one table per signal, for Gate 1 and the data review."""
    out = [
        "# Overlap review",
        "",
        f"## Ranked pairs (top {len(report.ranked)})",
        "",
        "| a | b | similarity |",
        "|---|---|---|",
    ]
    out += [f"| {p.a} | {p.b} | {p.similarity} |" for p in report.ranked]
    width = max((len(v) for v in report.nearest.values()), default=0)
    out += ["", "## Nearest intents", ""]
    out += ["| intent | " + " | ".join(_ordinal(i + 1) for i in range(width)) + " |"]
    out += ["|---|" + "---|" * width]
    for n, near in report.nearest.items():
        cells = [f"{p.b} ({p.similarity})" for p in near] + [""] * (width - len(near))
        out += [f"| {n} | " + " | ".join(cells) + " |"]
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
    pct = f"p{report.link_percentile:g}"
    out += ["", f"Link threshold: {report.link_threshold:.3f} ({pct} of within-intent similarity)"]
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


def recall_at(
    items: list[Item],
    emb: np.ndarray,
    expected: set[frozenset[str]],
    ks: tuple[int, ...] = (40, 80, 120),
) -> dict[int, float]:
    """For each k, the share of expected pairs among the top k of all intent pairs ranked by
    centred centroid cosine (ties by name); 1.0 for every k when nothing is expected."""
    if not expected:
        return dict.fromkeys(ks, 1.0)
    rank = [frozenset({p.a, p.b}) for p in _ranked(*_pair_sims(items, centre(emb)))]
    return {k: len(expected & set(rank[:k])) / len(expected) for k in ks}
