"""Mechanical dataset checks that work for any role (spec section 4, step 5)."""

import re
import string
from collections import Counter, defaultdict
from collections.abc import Iterable

from pydantic import BaseModel, Field

from mia.learning.schema import OTHER, Record, RoleSpec

LEAK = 0.85  # character 3-gram Jaccard at or above this is a paraphrase
_PUNCT = str.maketrans("", "", string.punctuation)

FINNISH_HINT = re.compile(
    r"\w*[äöå]\w*|\b(olen|en|ei|ja|tai|kun|klo|että|mikä|mitä|voin|sinun|huomenna|tänään|kuka|"
    r"voi|näytä|minun|kaikki|vain|aamu|valitse|anna|tuurata|kiitos|moi|hei|parhaat)\b",
    re.IGNORECASE,
)
ENGLISH_HINT = re.compile(
    r"\b(i|i'm|my|me|the|to|at|for|and|is|are|you|your|who|what|show|can|assign|sick|"
    r"tomorrow|today|visits?|all|only|please|hello|hi|hey|thanks|thank|best)\b",
    re.IGNORECASE,
)


def hint_language(text: str, default: str = "en") -> str:
    """The language with more hint words ('fi' or 'en'); the default on a tie. A data check for
    training records and eval replies only: chat replies use person.language (ADR 016).

    Counting, not first match: an English message that names a Finnish place (Töölö) or person
    stays English.
    """
    fi, en = len(FINNISH_HINT.findall(text)), len(ENGLISH_HINT.findall(text))
    if fi == en:
        return default
    return "fi" if fi > en else "en"


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


def check_records(
    role: RoleSpec,
    records: list[Record],
    conversation: list[str],
    conversation_examples: Iterable[str] = (),
) -> CheckReport:
    """Errors block training; warnings go to review.md for the reviewer to judge."""
    report = CheckReport()
    shadows = {c.split(".", 1)[-1].removeprefix("kb_"): c for c in conversation}
    for intent in role.intents:
        if clash := shadows.get(intent.id.split(".", 1)[-1]):
            report.errors.append(f"role intent {intent.id} duplicates {clash}")
    labels = set(role.label_space(conversation))
    for rid, n in Counter(r.id for r in records).items():
        if n > 1:
            report.errors.append(f"duplicate id {rid}")
    for r in records:
        if r.intent not in labels:
            report.errors.append(f"unknown intent {r.intent} in {r.id}")
        if r.negative_of and r.negative_of not in labels:
            report.errors.append(f"unknown negative_of {r.negative_of} in {r.id}")
        if r.lang in ("fi", "en") and hint_language(r.text, r.lang) not in (r.lang, "?"):
            report.warnings.append(f"{r.id} may not be {r.lang}: {r.text!r}")
    _check_one_text_one_intent(records, report)
    _check_conversation_examples(records, conversation_examples, report)
    _check_leakage(records, report)
    _check_quotas(role, records, report)
    _check_mix(records, report)
    return report


def _check_one_text_one_intent(records: list[Record], report: CheckReport) -> None:
    """One message, one label (D30): the same text under two intents is an error."""
    intents: dict[str, set[str]] = defaultdict(set)
    for r in records:
        intents[normalize(r.text)].add(r.intent)
    # punctuation-only texts normalise to "" and say nothing about the label
    clashes = [(t, sorted(i)) for t, i in intents.items() if t and len(i) > 1]
    for text, ids in clashes[:5]:  # ponytail: five examples keep the output readable
        report.errors.append(f"same text with two intents: {text!r} ({', '.join(ids)})")


def _check_conversation_examples(
    records: list[Record], examples: Iterable[str], report: CheckReport
) -> None:
    known = {normalize(e) for e in examples} - {""}
    for r in records:
        if normalize(r.text) in known:
            report.warnings.append(f"{r.id} equals a conversation.yaml example: {r.text!r}")


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
    if not kinds["safety"]:
        report.warnings.append("no safety records")
    if not any(r.intent == OTHER for r in records):
        report.errors.append("no records labelled other")
