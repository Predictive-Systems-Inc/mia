"""Mechanical dataset checks that work for any role (spec section 4, step 5)."""

import re
import string
from collections import Counter, defaultdict

from pydantic import BaseModel, Field

from mia.agents.dispatcher.classifier import detect_language
from mia.learning.schema import OTHER, Record, RoleSpec

LEAK = 0.85  # character 3-gram Jaccard at or above this is a paraphrase
_PUNCT = str.maketrans("", "", string.punctuation)


class CheckReport(BaseModel):
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().translate(_PUNCT)).strip()


def _grams(text: str) -> set[str]:
    t = f"  {normalize(text)}  "
    return {t[i : i + 3] for i in range(len(t) - 2)}


def similarity(a: str, b: str) -> float:
    ga, gb = _grams(a), _grams(b)
    return len(ga & gb) / len(ga | gb) if ga | gb else 1.0


def check_records(role: RoleSpec, records: list[Record], conversation: list[str]) -> CheckReport:
    """Errors block training; warnings go to review.md for the reviewer to judge."""
    report = CheckReport()
    labels = set(role.label_space(conversation))
    for rid, n in Counter(r.id for r in records).items():
        if n > 1:
            report.errors.append(f"duplicate id {rid}")
    for r in records:
        if r.intent not in labels:
            report.errors.append(f"unknown intent {r.intent} in {r.id}")
        if r.negative_of and r.negative_of not in labels:
            report.errors.append(f"unknown negative_of {r.negative_of} in {r.id}")
        if r.lang in ("fi", "en") and detect_language(r.text, r.lang) not in (r.lang, "?"):
            report.warnings.append(f"{r.id} may not be {r.lang}: {r.text!r}")
    _check_leakage(records, report)
    _check_quotas(role, records, report)
    _check_mix(records, report)
    return report


def _check_leakage(records: list[Record], report: CheckReport) -> None:
    # ponytail: pairwise within (intent, lang) buckets, O(n^2) per bucket of a few hundred.
    buckets: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for r in records:
        buckets[(r.intent, r.lang)].append(r)
    for bucket in buckets.values():
        for i, a in enumerate(bucket):
            for b in bucket[i + 1 :]:
                if a.split != b.split and similarity(a.text, b.text) >= LEAK:
                    report.errors.append(f"leakage {a.id} ({a.split}) ~ {b.id} ({b.split})")


def _check_quotas(role: RoleSpec, records: list[Record], report: CheckReport) -> None:
    counts = Counter((r.intent, r.lang, r.split) for r in records if r.kind == "normal")
    for intent in role.intents:
        for lang in role.languages:
            for split in ("train", "dev", "test"):
                need = role.targets.quota(intent, split)
                have = counts[(intent.id, lang, split)]
                if have < need:
                    report.errors.append(f"{intent.id}/{lang} {split} {have} < {need}")


def _check_mix(records: list[Record], report: CheckReport) -> None:
    total = len(records) or 1
    kinds = Counter(r.kind for r in records)
    if kinds["negative"] / total < 0.15:
        report.warnings.append(f"hard negatives {kinds['negative'] / total:.0%} < 15%")
    share_other = (kinds["other"] + kinds["injection"]) / total
    if not 0.05 <= share_other <= 0.12:
        report.warnings.append(f"other and injection {share_other:.0%} outside 5 to 12%")
    if kinds["injection"] / total < 0.01:
        report.warnings.append("injection attempts under 1%")
    if not any(r.intent == OTHER for r in records):
        report.errors.append("no records labelled other")
