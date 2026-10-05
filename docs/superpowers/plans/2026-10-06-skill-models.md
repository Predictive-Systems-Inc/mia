# Role Skill Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Mia agent role a multilingual intent classifier that is planned, generated, reviewed, trained, gated and promoted the same way each time, used on every chat turn, and improved from real clarifications.

**Architecture:** A deterministic `mia.learning` package (schema, checks, splits, metrics, gate, package, harvest, trainer, generator) plus a node runtime `mia.skills` (classifier registry and per-turn routing) wired into `chat.service.run_turn`. Creative work (role planning, dataset research, generation, review) is the Claude Code skill `/mia-train-role`, which calls the package's commands. Training libraries live in an optional dependency group; the node needs only the ONNX runtime.

**Tech Stack:** Python 3.12, Pydantic v2, SQLModel, Pydantic AI 2.52 (generator), Hugging Face Transformers + PyTorch (training, optional group), ONNX + onnxruntime + tokenizers (inference), pytest.

**Spec:** docs/superpowers/specs/2026-10-06-skill-models-design.md

## Global Constraints

- CLAUDE.md rules 1 to 14 apply: writes through service functions that emit events; events append-only; agents act only through registered tools; `rbac.require` before every tool call; actor plus on_behalf_of; nothing leaves the node except through `core/egress.py` or `channels/transport.py`; LLMs classify, code calculates; user text is data; IDs are ULIDs; short write transactions; no blocking I/O on the event loop; sessions through Depends in routes; schema changes need an Alembic migration.
- No new dependency without approval (Task 13 is the approval gate; Tasks 1 to 12 add none).
- Ruff line length 100, rules I, B, UP; mypy strict on mia/core, mia/chat, mia/agents; also run mypy on mia/learning and mia/skills.
- No em-dashes in docs or comments. User-facing strings go through mia/i18n (fi and en keys; fil added when the language is enabled).
- Run before every commit: `uv run ruff check . && uv run ruff format . && uv run mypy node/mia && uv run pytest`.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Synthetic data only leaves the node; real messages stay on the node unless the owner chose cloud learning (D27).
- Promotion defaults from the spec: write/money/external intents precision >= 0.99 at threshold; read intents >= 0.95; coverage >= 0.70; each language within 0.03 of the best; safety recall >= 0.99; injection and `other` never routed to a tool or template action; ECE <= 0.05; no intent or language worse than the active version.
- Sizing defaults per intent per language: train 30 minimum / 60 target / 100 high-volume or write / 60 follow-up; dev 10 / 15 high / 15 follow-up; test 20 / 30 high / 30 follow-up.

## Review Focus

1. A role with no trained package yet: every turn must behave exactly as today (band `low`, agent runs). Test in Task 10.
2. A high-confidence classification for an intent the person may not perform (a cleaner "assign cover"): it must still be denied by `rbac.require` inside the tool. Test in Task 10.
3. A "Did you mean" answer typed as free text instead of tapping a button ("the first one", or a new message): it must not be forced into an option; anything that is not an exact option label is a new message. Test in Task 10.
4. An injection or out-of-scope message classified with high confidence as a template or tool intent: the gate must fail; at runtime `other` and injection never trigger a template action. Tests in Tasks 5 and 9.
5. A corrupt or partially written model package (missing thresholds, interrupted training): the runtime falls back to the null classifier and health shows it; promotion refuses a package without a passing gate and a sign-off. Tests in Tasks 7 and 8.

---

## File Structure

```
node/mia/learning/                 offline pipeline (no node-only imports)
  __init__.py
  schema.py        Record, IntentSpec, RoleSpec, Targets, loaders and writers
  catalogue.py     shared conversation intents (loads node/mia/learning/catalogue/conversation.yaml)
  catalogue/conversation.yaml      copied from node/tests/evals/conversation_intents.yaml
  checks.py        dataset checks -> CheckReport
  splits.py        train/dev assignment with paraphrase grouping
  metrics.py       softmax, temperature fit, ECE, thresholds, evaluation report (pure Python)
  gate.py          promotion gate
  public.py        public.yaml schema and licence rules
  package.py       model package files, ACTIVE marker, promote service
  harvest.py       clarification events -> candidate records (node data dir)
  generate.py      teacher generation through the gateway (synthetic only)
  train.py         trainer (imports torch/transformers lazily; learning group)
  commands.py      `mia skills ...` implementations
node/mia/skills/                   node runtime
  __init__.py
  runtime.py       Classification, Classifier protocol, NullClassifier, OnnxClassifier, registry
  routing.py       Route types and route(...)
node/mia/chat/service.py           per-turn integration (modify)
node/mia/agents/dispatcher/agent.py   replace regex intent_hint with classifier context (modify)
node/mia/agents/dispatcher/skill/role.yaml   the dispatcher's role plan (written by the skill, seeded in Task 18)
node/mia/i18n/strings.py           new keys (modify)
node/mia/settings.py               MIA_MODELS_DIR, MIA_LEARNING_DIR (modify)
node/mia/cli.py                    `skills` subcommands (modify)
.claude/skills/mia-train-role/     SKILL.md, guidelines.md, prompts/*.md
node/tests/learning/               unit tests for mia.learning
node/tests/skills/                 unit tests for mia.skills
node/tests/fixtures/role_tiny/     3-intent fixture role for trainer and runtime tests
docs/adr/013-skill-models.md       new folders, dependency group, runtime dependency
```

---

### Task 1: Schema and loaders

**Files:**
- Create: `node/mia/learning/__init__.py`, `node/mia/learning/schema.py`
- Create: `node/mia/learning/catalogue.py`, `node/mia/learning/catalogue/conversation.yaml` (copy of `node/tests/evals/conversation_intents.yaml`)
- Test: `node/tests/learning/__init__.py`, `node/tests/learning/test_schema.py`

**Interfaces:**
- Produces:
  - `Lang = Literal["en", "fi", "fil", "mixed"]`, `Style`, `Kind`, `Split`, `Risk`, `Handler`
  - `class Record(BaseModel)` with fields `id, role, intent, lang, text, context, counterpart, style, channel, country, slots, negative_of, kind, split, source, review`
  - `class IntentSpec(BaseModel)`, `class Targets(BaseModel)` with `quota(intent: IntentSpec, split: Split) -> int`, `class RoleSpec(BaseModel)` with `label_space(conversation: list[str]) -> list[str]` and `intent(id) -> IntentSpec | None`
  - `load_role(path: Path) -> RoleSpec`, `load_records(path: Path) -> list[Record]`, `write_records(path: Path, records: Iterable[Record]) -> None`
  - `catalogue.conversation_intents() -> list[ConversationIntent]` with `id, category, handling, examples`; `catalogue.safety_ids() -> set[str]` (handling `emergency`)

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_schema.py
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mia.learning import catalogue
from mia.learning.schema import (
    IntentSpec,
    Record,
    RoleSpec,
    Targets,
    load_records,
    load_role,
    write_records,
)

ROLE_YAML = """
id: dispatcher
job_summary: Keeps every visit staffed.
responsibilities: [record absences, find cover]
counterparts:
  - {role: cleaner, share: 0.8, channel: whatsapp}
  - {role: supervisor, share: 0.2, channel: web}
languages: [en, fi, fil]
countries: [FI]
styles: {informal: 0.3, terse: 0.15, typo: 0.15, indirect: 0.15, formal: 0.1, mixed: 0.1, context: 0.05}
intents:
  - id: dispatcher.report_absence
    description: Cannot work (sick, late, leaving early)
    counterparts: [cleaner]
    risk: write
    label_en: Report I'm sick
    slots: [reason, partial_day]
    handler: agent
    volume: high
  - id: dispatcher.my_visits
    description: Asks about own visits
    counterparts: [cleaner]
    risk: read
    label_en: Show my shifts
    handler: agent
"""


def test_role_loads_and_label_space(tmp_path: Path) -> None:
    path = tmp_path / "role.yaml"
    path.write_text(ROLE_YAML)
    role = load_role(path)
    assert role.intent("dispatcher.report_absence") is not None
    labels = role.label_space(["conversation.greeting"])
    assert labels == ["dispatcher.report_absence", "dispatcher.my_visits", "conversation.greeting", "other"]


def test_quota_follows_volume_and_follow_up() -> None:
    t = Targets()
    high = IntentSpec(id="a.b", description="d", counterparts=["cleaner"], risk="write", label_en="x", volume="high")
    normal = IntentSpec(id="a.c", description="d", counterparts=["cleaner"], risk="read", label_en="y")
    follow = IntentSpec(id="a.d", description="d", counterparts=["cleaner"], risk="write", label_en="z", follow_up=True)
    assert (t.quota(high, "train"), t.quota(high, "dev"), t.quota(high, "test")) == (100, 15, 30)
    assert (t.quota(normal, "train"), t.quota(normal, "dev"), t.quota(normal, "test")) == (30, 10, 20)
    assert (t.quota(follow, "train"), t.quota(follow, "test")) == (60, 30)


def test_label_en_is_short() -> None:
    with pytest.raises(ValidationError):
        IntentSpec(id="a.b", description="d", counterparts=["c"], risk="read", label_en="x" * 21)


def test_tool_handler_needs_a_tool() -> None:
    with pytest.raises(ValidationError):
        IntentSpec(id="a.b", description="d", counterparts=["c"], risk="write", label_en="x", handler="tool")


def test_records_round_trip_and_reject_unknown_fields(tmp_path: Path) -> None:
    rec = Record(
        id="dispatcher.report_absence/en/001", role="dispatcher", intent="dispatcher.report_absence",
        lang="en", text="sick today", counterpart="cleaner", style="terse", split="train",
        source="teacher:sonnet-5.5",
    )
    path = tmp_path / "train.jsonl"
    write_records(path, [rec])
    assert load_records(path) == [rec]
    bad = json.loads(path.read_text())
    bad["surprise"] = 1
    path.write_text(json.dumps(bad) + "\n")
    with pytest.raises(ValidationError):
        load_records(path)


def test_conversation_catalogue_has_safety_intents() -> None:
    ids = {c.id for c in catalogue.conversation_intents()}
    assert "conversation.greeting" in ids
    assert catalogue.safety_ids() and catalogue.safety_ids() <= ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/learning/test_schema.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/learning/__init__.py
"""Offline pipeline for role skill models (docs/superpowers/specs/2026-10-06-skill-models-design.md)."""
```

```python
# node/mia/learning/schema.py
"""Role plans and training records. Pydantic at every boundary; files are YAML and JSONL."""

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Lang = Literal["en", "fi", "fil", "mixed"]
Style = Literal["informal", "terse", "typo", "indirect", "formal", "mixed", "context"]
Kind = Literal["normal", "negative", "other", "injection", "safety"]
Split = Literal["train", "dev", "test"]
Risk = Literal["read", "write", "money", "external", "delete"]
Handler = Literal["tool", "template", "agent"]
OTHER = "other"


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "kept", "fixed", "dropped"] = "pending"
    note: str = ""


class Record(BaseModel):
    """One labelled message. The same shape for synthetic, public and real records."""

    model_config = ConfigDict(extra="forbid")
    id: str
    role: str
    intent: str
    lang: Lang
    text: str = Field(min_length=1)
    context: str = ""
    counterpart: str
    style: Style
    channel: Literal["whatsapp", "web"] = "whatsapp"
    country: Literal["FI", "PH", "any"] = "any"
    slots: dict[str, str] = Field(default_factory=dict)
    negative_of: str | None = None
    kind: Kind = "normal"
    split: Split
    source: str
    review: Review = Field(default_factory=Review)


class IntentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str
    counterparts: list[str]
    risk: Risk
    label_en: str = Field(max_length=20)
    slots: list[str] = Field(default_factory=list)
    handler: Handler = "agent"
    tool: str | None = None
    volume: Literal["normal", "high"] = "normal"
    follow_up: bool = False
    look_alikes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def tool_handler_names_a_tool(self) -> "IntentSpec":
        if self.handler == "tool" and not self.tool:
            raise ValueError(f"{self.id}: handler 'tool' needs a tool id")
        return self

    @property
    def acts(self) -> bool:
        """True when a high-band classification leads straight to an action."""
        return self.handler in ("tool", "template")


class Targets(BaseModel):
    """Sizing and gate defaults (spec section 6); role.yaml may override any field."""

    model_config = ConfigDict(extra="forbid")
    train_min: int = 30
    train_target: int = 60
    train_high: int = 100
    train_follow_up: int = 60
    dev: int = 10
    dev_high: int = 15
    test: int = 20
    test_high: int = 30
    precision_write: float = 0.99
    precision_read: float = 0.95
    coverage: float = 0.70
    language_gap: float = 0.03
    safety_recall: float = 0.99
    ece: float = 0.05
    medium_floor: float = 0.35
    safety_floor: float = 0.20

    def quota(self, intent: IntentSpec, split: Split) -> int:
        """Minimum records per language for this intent and split."""
        heavy = intent.volume == "high" or intent.risk != "read"
        if split == "train":
            if intent.follow_up:
                return self.train_follow_up
            return self.train_high if heavy else self.train_min
        if split == "dev":
            return self.dev_high if heavy or intent.follow_up else self.dev
        return self.test_high if heavy or intent.follow_up else self.test

    def precision_for(self, intent: IntentSpec) -> float:
        return self.precision_read if intent.risk == "read" else self.precision_write


class Counterpart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    share: float
    channel: Literal["whatsapp", "web"] = "whatsapp"


class RoleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    job_summary: str
    responsibilities: list[str]
    counterparts: list[Counterpart]
    languages: list[Lang]
    countries: list[Literal["FI", "PH"]]
    styles: dict[Style, float]
    intents: list[IntentSpec]
    targets: Targets = Field(default_factory=Targets)
    base_model: str = "jhu-clsp/mmBERT-base"

    def intent(self, intent_id: str) -> IntentSpec | None:
        return next((i for i in self.intents if i.id == intent_id), None)

    def label_space(self, conversation: list[str]) -> list[str]:
        """Role intents, then shared conversation intents, then `other`, in a stable order."""
        return [i.id for i in self.intents] + list(conversation) + [OTHER]


def load_role(path: Path) -> RoleSpec:
    return RoleSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_records(path: Path) -> list[Record]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Record.model_validate_json(line) for line in lines if line.strip()]


def write_records(path: Path, records: Iterable[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(r.model_dump_json() + "\n" for r in records)
    path.write_text(body, encoding="utf-8")
```

```python
# node/mia/learning/catalogue.py
"""Conversation intents shared by every role (greetings, help, safety, privacy, out of scope)."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

PATH = Path(__file__).parent / "catalogue" / "conversation.yaml"


class ConversationIntent(BaseModel):
    id: str
    category: str
    handling: str
    description: str = ""
    examples: list[str] = []


@lru_cache
def conversation_intents() -> list[ConversationIntent]:
    data = yaml.safe_load(PATH.read_text(encoding="utf-8"))
    return [ConversationIntent.model_validate(i) for i in data["intents"]]


def safety_ids() -> set[str]:
    """Intents with the emergency script (spec section 7, step 1)."""
    return {c.id for c in conversation_intents() if c.handling == "emergency"}
```

Then copy the shared catalogue:

```bash
mkdir -p node/mia/learning/catalogue && cp node/tests/evals/conversation_intents.yaml node/mia/learning/catalogue/conversation.yaml
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_schema.py --no-cov -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning node/tests/learning
git commit -m "learning: role plan and record schema, shared conversation catalogue"
```

---

### Task 2: Dataset checks

**Files:**
- Create: `node/mia/learning/checks.py`
- Test: `node/tests/learning/test_checks.py`

**Interfaces:**
- Consumes: `RoleSpec`, `Record`, `OTHER` from Task 1; `mia.agents.dispatcher.classifier.detect_language` (existing, fi/en only).
- Produces: `normalize(text: str) -> str`, `similarity(a: str, b: str) -> float` (character 3-gram Jaccard), `class CheckReport(BaseModel)` with `errors: list[str]`, `warnings: list[str]`, property `ok`, and `check_records(role: RoleSpec, records: list[Record], conversation: list[str]) -> CheckReport`.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_checks.py
from mia.learning.checks import check_records, normalize, similarity
from mia.learning.schema import IntentSpec, Record, RoleSpec, Targets


def role(train: int = 2, dev: int = 1, test: int = 1) -> RoleSpec:
    return RoleSpec(
        id="r", job_summary="j", responsibilities=["x"], counterparts=[], languages=["en"],
        countries=["FI"], styles={"informal": 1.0},
        intents=[IntentSpec(id="r.a", description="d", counterparts=["cleaner"], risk="read", label_en="A")],
        targets=Targets(train_min=train, dev=dev, test=test),
    )


def rec(i: int, text: str, split: str, intent: str = "r.a", kind: str = "normal") -> Record:
    return Record(id=f"r/{i}", role="r", intent=intent, lang="en", text=text, counterpart="cleaner",
                  style="informal", split=split, source="teacher:t", kind=kind)  # type: ignore[arg-type]


def test_normalize_and_similarity() -> None:
    assert normalize("  Hi!!  I'm SICK ") == "hi im sick"
    assert similarity("im sick today", "im sick today!") > 0.85
    assert similarity("im sick today", "show my shifts") < 0.3


def test_clean_dataset_passes() -> None:
    recs = [rec(1, "im sick today", "train"), rec(2, "cant come in tomorrow", "train"),
            rec(3, "running a fever, staying home", "dev"), rec(4, "not feeling well, off today", "test"),
            rec(5, "what time does the store open", "train", intent="other", kind="other")]
    report = check_records(role(), recs, conversation=[])
    assert report.ok, report.errors


def test_unknown_label_is_an_error() -> None:
    report = check_records(role(), [rec(1, "hello", "train", intent="r.zzz")], conversation=[])
    assert any("unknown intent r.zzz" in e for e in report.errors)


def test_paraphrase_across_splits_is_leakage() -> None:
    recs = [rec(1, "im sick today", "train"), rec(2, "im sick today!", "test")]
    report = check_records(role(train=1, dev=0, test=1), recs, conversation=[])
    assert any("leakage" in e for e in report.errors)


def test_missing_quota_is_an_error() -> None:
    report = check_records(role(train=5), [rec(1, "im sick", "train")], conversation=[])
    assert any("r.a/en train 1 < 5" in e for e in report.errors)


def test_duplicate_ids_are_an_error() -> None:
    recs = [rec(1, "im sick today", "train"), rec(1, "cant come", "train")]
    report = check_records(role(train=1, dev=0, test=0), recs, conversation=[])
    assert any("duplicate id r/1" in e for e in report.errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/learning/test_checks.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning.checks'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/learning/checks.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_checks.py --no-cov -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/checks.py node/tests/learning/test_checks.py
git commit -m "learning: dataset checks (labels, leakage, quotas, mix)"
```

---

### Task 3: Train and dev assignment

**Files:**
- Create: `node/mia/learning/splits.py`
- Test: `node/tests/learning/test_splits.py`

**Interfaces:**
- Consumes: `Record`, `RoleSpec`, `similarity`, `LEAK`.
- Produces: `assign_train_dev(role: RoleSpec, records: list[Record], seed: int = 0) -> list[Record]` (test records untouched; paraphrase clusters never split; dev gets `targets.quota(intent, "dev")` per intent and language first).

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_splits.py
from mia.learning.checks import similarity
from mia.learning.schema import IntentSpec, Record, RoleSpec, Targets
from mia.learning.splits import assign_train_dev

ROLE = RoleSpec(
    id="r", job_summary="j", responsibilities=["x"], counterparts=[], languages=["en"], countries=["FI"],
    styles={"informal": 1.0},
    intents=[IntentSpec(id="r.a", description="d", counterparts=["c"], risk="read", label_en="A")],
    targets=Targets(dev=2),
)


def rec(i: int, text: str, split: str = "train") -> Record:
    return Record(id=f"r/{i}", role="r", intent="r.a", lang="en", text=text, counterpart="c",
                  style="informal", split=split, source="t")  # type: ignore[arg-type]


TEXTS = ["im sick today", "im sick today!", "cant come tomorrow", "fever, staying home",
         "off work today, unwell", "not coming in, flu", "home sick", "feeling awful, no work"]


def test_dev_quota_and_test_untouched() -> None:
    recs = [rec(i, t) for i, t in enumerate(TEXTS)] + [rec(99, "sick, sorry", split="test")]
    out = assign_train_dev(ROLE, recs, seed=1)
    assert sum(r.split == "dev" for r in out) >= 2
    assert next(r for r in out if r.id == "r/99").split == "test"


def test_paraphrases_stay_together_and_result_is_stable() -> None:
    recs = [rec(i, t) for i, t in enumerate(TEXTS)]
    a = assign_train_dev(ROLE, recs, seed=1)
    b = assign_train_dev(ROLE, recs, seed=1)
    assert [r.split for r in a] == [r.split for r in b]
    s = {r.text: r.split for r in a}
    assert similarity("im sick today", "im sick today!") >= 0.85
    assert s["im sick today"] == s["im sick today!"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/learning/test_splits.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning.splits'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/learning/splits.py
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
    return [r.model_copy(update={"split": split_of[r.id]}) if r.id in split_of else r for r in records]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_splits.py --no-cov -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/splits.py node/tests/learning/test_splits.py
git commit -m "learning: train/dev assignment with paraphrase clusters"
```

---

### Task 4: Metrics, calibration and thresholds

**Files:**
- Create: `node/mia/learning/metrics.py`
- Test: `node/tests/learning/test_metrics.py`

**Interfaces:**
- Consumes: `RoleSpec`, `Targets`, `OTHER`.
- Produces:
  - `class Prediction(BaseModel)`: `record_id, intent, lang, kind, style, labels: list[str], logits: list[float]`
  - `softmax(logits: list[float], temperature: float = 1.0) -> list[float]`
  - `fit_temperature(preds: list[Prediction]) -> float` (grid 0.5 to 5.0, minimises NLL)
  - `expected_calibration_error(preds, temperature, bins=10) -> float`
  - `choose_thresholds(preds, role, temperature) -> dict[str, float]` (per intent; 1.01 when the target is unreachable)
  - `class EvalReport(BaseModel)`: `accuracy, macro_f1, coverage, ece, per_intent: dict[str, IntentScore], per_lang: dict[str, float], safety_recall: float, actions_from_other: int, confusions: list[tuple[str, str, int]]`
  - `class IntentScore(BaseModel)`: `support, precision_at_threshold, recall, f1, auto_share`
  - `evaluate(preds, role, thresholds, temperature, safety: set[str]) -> EvalReport`

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_metrics.py
import math

from mia.learning.metrics import (
    Prediction,
    choose_thresholds,
    evaluate,
    expected_calibration_error,
    fit_temperature,
    softmax,
)
from mia.learning.schema import IntentSpec, RoleSpec

LABELS = ["r.write", "r.read", "conversation.emergency", "other"]
ROLE = RoleSpec(
    id="r", job_summary="j", responsibilities=["x"], counterparts=[], languages=["en", "fi"],
    countries=["FI"], styles={"informal": 1.0},
    intents=[
        IntentSpec(id="r.write", description="d", counterparts=["c"], risk="write", label_en="W", handler="template"),
        IntentSpec(id="r.read", description="d", counterparts=["c"], risk="read", label_en="R"),
    ],
)


def p(i: int, intent: str, logits: list[float], lang: str = "en", kind: str = "normal") -> Prediction:
    return Prediction(record_id=str(i), intent=intent, lang=lang, kind=kind, style="informal",
                      labels=LABELS, logits=logits)  # type: ignore[arg-type]


def test_softmax_sums_to_one_and_temperature_flattens() -> None:
    s = softmax([2.0, 0.0])
    assert math.isclose(sum(s), 1.0)
    assert softmax([2.0, 0.0], temperature=2.0)[0] < s[0]


def test_thresholds_meet_precision_or_disable() -> None:
    preds = [p(i, "r.write", [5, 0, 0, 0]) for i in range(20)] + [p(30, "r.read", [3, 0, 0, 0])]
    thr = choose_thresholds(preds, ROLE, temperature=1.0)
    above = [x for x in preds if softmax(x.logits)[0] >= thr["r.write"]]
    assert all(x.intent == "r.write" for x in above)
    only_wrong = [p(i, "r.read", [5, 0, 0, 0]) for i in range(5)]
    assert choose_thresholds(only_wrong, ROLE, 1.0)["r.write"] > 1.0


def test_evaluate_counts_actions_from_other_and_safety_recall() -> None:
    preds = [
        p(1, "r.write", [6, 0, 0, 0]),
        p(2, "other", [6, 0, 0, 0], kind="injection"),      # routed to a template action: bad
        p(3, "conversation.emergency", [0, 0, 6, 0], kind="safety"),
        p(4, "r.read", [0, 6, 0, 0], lang="fi"),
    ]
    report = evaluate(preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety={"conversation.emergency"})
    assert report.actions_from_other == 1
    assert report.safety_recall == 1.0
    assert set(report.per_lang) == {"en", "fi"}


def test_calibration_helpers_run() -> None:
    preds = [p(i, "r.write", [2, 0, 0, 0]) for i in range(10)]
    t = fit_temperature(preds)
    assert 0.5 <= t <= 5.0
    assert 0.0 <= expected_calibration_error(preds, t) <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/learning/test_metrics.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning.metrics'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/learning/metrics.py
"""Calibration, thresholds and evaluation in pure Python (spec section 5, steps 3 and 4)."""

import math
from collections import Counter, defaultdict

from pydantic import BaseModel

from mia.learning.schema import OTHER, RoleSpec


class Prediction(BaseModel):
    record_id: str
    intent: str  # the true label
    lang: str
    kind: str
    style: str
    labels: list[str]
    logits: list[float]


class IntentScore(BaseModel):
    support: int
    precision_at_threshold: float
    recall: float
    f1: float
    auto_share: float


class EvalReport(BaseModel):
    accuracy: float
    macro_f1: float
    coverage: float
    ece: float
    per_intent: dict[str, IntentScore]
    per_lang: dict[str, float]
    safety_recall: float
    actions_from_other: int
    confusions: list[tuple[str, str, int]]


def softmax(logits: list[float], temperature: float = 1.0) -> list[float]:
    scaled = [x / temperature for x in logits]
    top = max(scaled)
    exps = [math.exp(x - top) for x in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def _top(pred: Prediction, temperature: float) -> tuple[str, float]:
    probs = softmax(pred.logits, temperature)
    i = max(range(len(probs)), key=probs.__getitem__)
    return pred.labels[i], probs[i]


def fit_temperature(preds: list[Prediction]) -> float:
    """Grid search on dev; NLL of the true label."""
    def nll(t: float) -> float:
        return -sum(
            math.log(max(softmax(p.logits, t)[p.labels.index(p.intent)], 1e-12)) for p in preds
        )

    grid = [0.5 + 0.05 * i for i in range(91)]
    return min(grid, key=nll)


def expected_calibration_error(preds: list[Prediction], temperature: float, bins: int = 10) -> float:
    buckets: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for p in preds:
        label, conf = _top(p, temperature)
        buckets[min(int(conf * bins), bins - 1)].append((conf, label == p.intent))
    n = len(preds) or 1
    return sum(
        len(b) / n * abs(sum(c for c, _ in b) / len(b) - sum(ok for _, ok in b) / len(b))
        for b in buckets.values()
    )


def choose_thresholds(preds: list[Prediction], role: RoleSpec, temperature: float) -> dict[str, float]:
    """Lowest confidence per intent at which precision meets the intent's risk target on dev."""
    out: dict[str, float] = {}
    tops = [(_top(p, temperature), p.intent) for p in preds]
    for intent in role.intents:
        target = role.targets.precision_for(intent)
        mine = sorted(((conf, truth) for (label, conf), truth in tops if label == intent.id), reverse=True)
        best = 1.01  # unreachable: never automatic
        correct = 0
        for k, (conf, truth) in enumerate(mine, start=1):
            correct += truth == intent.id
            if correct / k >= target:
                best = conf
        out[intent.id] = best
    return out


def evaluate(
    preds: list[Prediction],
    role: RoleSpec,
    thresholds: dict[str, float],
    temperature: float,
    safety: set[str],
) -> EvalReport:
    """Score the test split once (gate metrics plus confusions)."""
    acting = {i.id for i in role.intents if i.acts}
    rows = [(p, *_top(p, temperature)) for p in preds]
    auto = [(p, label) for p, label, conf in rows if conf >= thresholds.get(label, 1.01)]
    per_intent: dict[str, IntentScore] = {}
    f1s = []
    for intent in role.intents:
        tp = sum(1 for p, label, _ in rows if label == intent.id and p.intent == intent.id)
        pred_n = sum(1 for _, label, _ in rows if label == intent.id)
        support = sum(1 for p in preds if p.intent == intent.id)
        auto_mine = [p for p, label in auto if label == intent.id]
        precision = (sum(p.intent == intent.id for p in auto_mine) / len(auto_mine)) if auto_mine else 1.0
        recall = tp / support if support else 0.0
        prec_all = tp / pred_n if pred_n else 0.0
        f1 = 2 * prec_all * recall / (prec_all + recall) if prec_all + recall else 0.0
        f1s.append(f1)
        per_intent[intent.id] = IntentScore(
            support=support, precision_at_threshold=precision, recall=recall, f1=f1,
            auto_share=len(auto_mine) / support if support else 0.0,
        )
    by_lang: dict[str, list[bool]] = defaultdict(list)
    for p, label, _ in rows:
        by_lang[p.lang].append(label == p.intent)
    safety_rows = [(p, label) for p, label, _ in rows if p.intent in safety]
    confusions = Counter((p.intent, label) for p, label, _ in rows if label != p.intent)
    return EvalReport(
        accuracy=sum(label == p.intent for p, label, _ in rows) / (len(rows) or 1),
        macro_f1=sum(f1s) / (len(f1s) or 1),
        coverage=len(auto) / (len(rows) or 1),
        ece=expected_calibration_error(preds, temperature),
        per_intent=per_intent,
        per_lang={k: sum(v) / len(v) for k, v in by_lang.items()},
        safety_recall=(
            sum(label in safety for _, label in safety_rows) / len(safety_rows) if safety_rows else 1.0
        ),
        actions_from_other=sum(
            1 for p, label in auto
            if (p.intent == OTHER or p.kind in ("injection", "other")) and label in acting
        ),
        confusions=[(a, b, n) for (a, b), n in confusions.most_common(20)],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_metrics.py --no-cov -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/metrics.py node/tests/learning/test_metrics.py
git commit -m "learning: calibration, per-intent thresholds and evaluation report"
```

---

### Task 5: Promotion gate

**Files:**
- Create: `node/mia/learning/gate.py`
- Test: `node/tests/learning/test_gate.py`

**Interfaces:**
- Consumes: `EvalReport`, `RoleSpec`.
- Produces: `class GateResult(BaseModel)`: `passed: bool`, `failures: list[str]`; `check_gate(report: EvalReport, role: RoleSpec, previous: EvalReport | None) -> GateResult`.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_gate.py
from mia.learning.gate import check_gate
from mia.learning.metrics import EvalReport, IntentScore
from mia.learning.schema import IntentSpec, RoleSpec

ROLE = RoleSpec(
    id="r", job_summary="j", responsibilities=["x"], counterparts=[], languages=["en", "fi"],
    countries=["FI"], styles={"informal": 1.0},
    intents=[IntentSpec(id="r.write", description="d", counterparts=["c"], risk="write", label_en="W")],
)


def report(**over: object) -> EvalReport:
    base: dict[str, object] = dict(
        accuracy=0.95, macro_f1=0.93, coverage=0.8, ece=0.03,
        per_intent={"r.write": IntentScore(support=30, precision_at_threshold=0.995, recall=0.9, f1=0.9, auto_share=0.8)},
        per_lang={"en": 0.95, "fi": 0.94}, safety_recall=1.0, actions_from_other=0, confusions=[],
    )
    base.update(over)
    return EvalReport.model_validate(base)


def test_good_report_passes() -> None:
    assert check_gate(report(), ROLE, previous=None).passed


def test_each_rule_fails_with_a_reason() -> None:
    cases = {
        "precision": report(per_intent={"r.write": IntentScore(support=30, precision_at_threshold=0.97, recall=0.9, f1=0.9, auto_share=0.8)}),
        "coverage": report(coverage=0.5),
        "language": report(per_lang={"en": 0.95, "fi": 0.85}),
        "safety": report(safety_recall=0.9),
        "other": report(actions_from_other=1),
        "calibration": report(ece=0.2),
    }
    for word, rep in cases.items():
        result = check_gate(rep, ROLE, previous=None)
        assert not result.passed and any(word in f for f in result.failures), word


def test_regression_against_the_active_version_fails() -> None:
    result = check_gate(report(per_lang={"en": 0.95, "fi": 0.93}), ROLE, previous=report())
    assert not result.passed and any("worse than active" in f for f in result.failures)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/learning/test_gate.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning.gate'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/learning/gate.py
"""Promotion gate (spec section 6). A failure is a normal result with reasons, not an exception."""

from pydantic import BaseModel, Field

from mia.learning.metrics import EvalReport
from mia.learning.schema import RoleSpec

TOLERANCE = 0.005  # regression noise allowed against the active version


class GateResult(BaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)


def check_gate(report: EvalReport, role: RoleSpec, previous: EvalReport | None) -> GateResult:
    t = role.targets
    fails: list[str] = []
    for intent in role.intents:
        score = report.per_intent.get(intent.id)
        if score is None or score.support == 0:
            fails.append(f"precision: {intent.id} has no test records")
            continue
        need = t.precision_for(intent)
        if score.precision_at_threshold < need:
            fails.append(f"precision: {intent.id} {score.precision_at_threshold:.3f} < {need}")
    if report.coverage < t.coverage:
        fails.append(f"coverage: {report.coverage:.2f} < {t.coverage}")
    if report.per_lang:
        best = max(report.per_lang.values())
        for lang, acc in report.per_lang.items():
            if best - acc > t.language_gap:
                fails.append(f"language: {lang} {acc:.3f} more than {t.language_gap} below best {best:.3f}")
    if report.safety_recall < t.safety_recall:
        fails.append(f"safety: recall {report.safety_recall:.3f} < {t.safety_recall}")
    if report.actions_from_other:
        fails.append(f"other: {report.actions_from_other} out-of-scope or injection messages would act")
    if report.ece > t.ece:
        fails.append(f"calibration: ECE {report.ece:.3f} > {t.ece}")
    if previous is not None:
        for lang, acc in previous.per_lang.items():
            if report.per_lang.get(lang, 0.0) < acc - TOLERANCE:
                fails.append(f"language {lang} worse than active ({report.per_lang.get(lang, 0.0):.3f} < {acc:.3f})")
        for iid, old in previous.per_intent.items():
            new = report.per_intent.get(iid)
            if new is not None and new.f1 < old.f1 - TOLERANCE:
                fails.append(f"intent {iid} worse than active (F1 {new.f1:.3f} < {old.f1:.3f})")
    return GateResult(passed=not fails, failures=fails)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_gate.py --no-cov -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/gate.py node/tests/learning/test_gate.py
git commit -m "learning: promotion gate with reasons"
```

---

### Task 6: Public dataset spec and licence rules

**Files:**
- Create: `node/mia/learning/public.py`
- Test: `node/tests/learning/test_public.py`

**Interfaces:**
- Produces: `class PublicDataset(BaseModel)`: `name, source, version, licence, use (Literal["intermediate", "train", "other", "style", "safety"]), mapping: dict[str, str], approved_by: str | None`; `class PublicSpec(BaseModel)`: `datasets: list[PublicDataset]`, `rejected: list[dict[str, str]]`; `licence_verdict(licence: str) -> Literal["allowed", "needs_approval", "never"]`; `load_public(path: Path) -> PublicSpec` (raises `ValueError` for a `never` licence or a `needs_approval` licence without `approved_by`).

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_public.py
from pathlib import Path

import pytest

from mia.learning.public import licence_verdict, load_public


@pytest.mark.parametrize(
    ("licence", "verdict"),
    [("CC-BY-4.0", "allowed"), ("MIT", "allowed"), ("Apache-2.0", "allowed"), ("CC0-1.0", "allowed"),
     ("CC-BY-SA-4.0", "needs_approval"), ("custom", "needs_approval"),
     ("CC-BY-NC-4.0", "never"), ("CC-BY-NC-SA-4.0", "never"), ("unknown", "never")],
)
def test_licence_rules(licence: str, verdict: str) -> None:
    assert licence_verdict(licence) == verdict


def test_load_refuses_non_commercial_and_unapproved_share_alike(tmp_path: Path) -> None:
    path = tmp_path / "public.yaml"
    path.write_text("datasets:\n- {name: nllb, source: hf, version: '1', licence: CC-BY-NC-4.0, use: train}\n")
    with pytest.raises(ValueError, match="never"):
        load_public(path)
    path.write_text("datasets:\n- {name: sgd, source: hf, version: '1', licence: CC-BY-SA-4.0, use: other}\n")
    with pytest.raises(ValueError, match="approval"):
        load_public(path)
    path.write_text(
        "datasets:\n- {name: sgd, source: hf, version: '1', licence: CC-BY-SA-4.0, use: other, approved_by: Allan}\n"
    )
    assert load_public(path).datasets[0].name == "sgd"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/learning/test_public.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning.public'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/learning/public.py
"""Public datasets chosen per role (spec section 6, public data rules)."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Verdict = Literal["allowed", "needs_approval", "never"]
ALLOWED = {"cc-by-4.0", "cc-by-3.0", "mit", "apache-2.0", "cc0-1.0", "bsd-3-clause", "mpl-2.0"}


class PublicDataset(BaseModel):
    name: str
    source: str
    version: str
    licence: str
    use: Literal["intermediate", "train", "other", "style", "safety"]
    mapping: dict[str, str] = Field(default_factory=dict)  # public label -> role intent or `other`
    approved_by: str | None = None
    notes: str = ""


class PublicSpec(BaseModel):
    datasets: list[PublicDataset] = Field(default_factory=list)
    rejected: list[dict[str, str]] = Field(default_factory=list)


def licence_verdict(licence: str) -> Verdict:
    key = licence.strip().lower()
    if "nc" in key.replace("-", " ").split() or key == "unknown":
        return "never"
    if key in ALLOWED:
        return "allowed"
    return "needs_approval"  # share-alike, custom terms, training restrictions


def load_public(path: Path) -> PublicSpec:
    spec = PublicSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    for d in spec.datasets:
        verdict = licence_verdict(d.licence)
        if verdict == "never":
            raise ValueError(f"{d.name}: licence {d.licence} is never allowed")
        if verdict == "needs_approval" and not d.approved_by:
            raise ValueError(f"{d.name}: licence {d.licence} needs approval (approved_by)")
    return spec
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_public.py --no-cov -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/public.py node/tests/learning/test_public.py
git commit -m "learning: public dataset spec and licence rules"
```

---

### Task 7: Model package and promotion

**Files:**
- Create: `node/mia/learning/package.py`
- Modify: `node/mia/settings.py` (add `MIA_MODELS_DIR: Path = Path("data/models")`, `MIA_LEARNING_DIR: Path = Path("data/learning")` after `MIA_LOCAL_THINKING`)
- Modify: `.env.example` (document both)
- Test: `node/tests/learning/test_package.py`

**Interfaces:**
- Consumes: `EvalReport`, `GateResult`, `events.emit`, `Actor`.
- Produces:
  - `class ModelCard(BaseModel)`: `role, version, base_model, data_hash, temperature, medium_floor, safety_floor, labels: list[str], langs: list[str], slots: dict[str, list[str]], thresholds: dict[str, float], report: EvalReport, gate: GateResult, signed_by: str | None, signed_at: str | None`
  - `package_dir(role: str, version: str) -> Path`; `write_card(card: ModelCard) -> Path`; `read_card(role, version) -> ModelCard`
  - `active_version(role: str) -> str | None`; `promote(session, actor, role, version, signed_by) -> ModelCard` (raises `PromotionRefused`)
  - `class PromotionRefused(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_package.py
from pathlib import Path

import pytest
from sqlmodel import Session, select

from mia.core.models import Actor, Event, Person
from mia.learning.gate import GateResult
from mia.learning.metrics import EvalReport
from mia.learning.package import (
    ModelCard,
    PromotionRefused,
    active_version,
    promote,
    read_card,
    write_card,
)
from mia.settings import get_settings


def card(passed: bool = True, version: str = "v1") -> ModelCard:
    rep = EvalReport(accuracy=1, macro_f1=1, coverage=1, ece=0, per_intent={}, per_lang={},
                     safety_recall=1, actions_from_other=0, confusions=[])
    return ModelCard(role="r", version=version, base_model="m", data_hash="h", temperature=1.0,
                     medium_floor=0.35, safety_floor=0.2, labels=["r.a", "other"], langs=["en"], slots={},
                     thresholds={"r.a": 0.9}, report=rep,
                     gate=GateResult(passed=passed, failures=[] if passed else ["coverage"]))


@pytest.fixture(autouse=True)
def models_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIA_MODELS_DIR", str(tmp_path / "models"))
    get_settings.cache_clear()


def test_card_round_trip() -> None:
    write_card(card())
    assert read_card("r", "v1").thresholds == {"r.a": 0.9}


def test_promote_refuses_failed_gate_and_missing_signature(session: Session, people: dict[str, Person]) -> None:
    actor = Actor.person(people["Helena"])
    write_card(card(passed=False))
    with pytest.raises(PromotionRefused, match="gate"):
        promote(session, actor, "r", "v1", signed_by="Allan")
    write_card(card(passed=True))
    with pytest.raises(PromotionRefused, match="sign"):
        promote(session, actor, "r", "v1", signed_by="")
    assert active_version("r") is None


def test_promote_marks_active_keeps_previous_and_emits_event(session: Session, people: dict[str, Person]) -> None:
    actor = Actor.person(people["Helena"])
    write_card(card(version="v1"))
    write_card(card(version="v2"))
    promote(session, actor, "r", "v1", signed_by="Allan")
    promote(session, actor, "r", "v2", signed_by="Allan")
    assert active_version("r") == "v2"
    assert read_card("r", "v1").signed_by == "Allan"  # kept for rollback
    events = session.exec(select(Event).where(Event.action == "skill_model.promoted")).all()
    assert [e.entity_id for e in events] == ["r@v1", "r@v2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/learning/test_package.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning.package'`

- [ ] **Step 3: Write the implementation**

Add to `node/mia/settings.py` inside `Settings`, after `MIA_LOCAL_THINKING`:

```python
    # Role skill models (docs/superpowers/specs/2026-10-06-skill-models-design.md): built
    # packages, and harvested learning candidates. Both stay on the node, never in git.
    MIA_MODELS_DIR: Path = Field(default=Path("data/models"))
    MIA_LEARNING_DIR: Path = Field(default=Path("data/learning"))
```

Add to `.env.example` after the local model block:

```
# Role skill models: built model packages and harvested learning data (stay on the node).
MIA_MODELS_DIR=data/models
MIA_LEARNING_DIR=data/learning
```

```python
# node/mia/learning/package.py
"""Model packages on disk and their promotion (spec section 5)."""

import datetime as dt
from pathlib import Path

from pydantic import BaseModel
from sqlmodel import Session

from mia.core import events
from mia.core.models import Actor
from mia.learning.gate import GateResult
from mia.learning.metrics import EvalReport
from mia.settings import get_settings


class PromotionRefused(Exception):
    """The version cannot become active (gate failed, no sign-off, or missing)."""


class ModelCard(BaseModel):
    role: str
    version: str
    base_model: str
    data_hash: str
    temperature: float
    medium_floor: float
    safety_floor: float
    labels: list[str]
    langs: list[str]
    slots: dict[str, list[str]]
    thresholds: dict[str, float]
    report: EvalReport
    gate: GateResult
    signed_by: str | None = None
    signed_at: str | None = None


def package_dir(role: str, version: str) -> Path:
    return get_settings().MIA_MODELS_DIR / role / version


def write_card(card: ModelCard) -> Path:
    path = package_dir(card.role, card.version) / "card.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_card(role: str, version: str) -> ModelCard:
    return ModelCard.model_validate_json((package_dir(role, version) / "card.json").read_text("utf-8"))


def active_version(role: str) -> str | None:
    marker = get_settings().MIA_MODELS_DIR / role / "ACTIVE"
    return marker.read_text("utf-8").strip() or None if marker.exists() else None


def promote(session: Session, actor: Actor, role: str, version: str, signed_by: str) -> ModelCard:
    """Mark a signed, gate-passing version active; the previous one stays on disk for rollback."""
    try:
        card = read_card(role, version)
    except FileNotFoundError as exc:
        raise PromotionRefused(f"{role}@{version} not found") from exc
    if not card.gate.passed:
        raise PromotionRefused(f"{role}@{version} failed the gate: {card.gate.failures}")
    if not signed_by.strip():
        raise PromotionRefused("a sign-off name is required")
    previous = active_version(role)
    card = card.model_copy(update={"signed_by": signed_by, "signed_at": dt.datetime.now(dt.UTC).isoformat()})
    write_card(card)
    (get_settings().MIA_MODELS_DIR / role / "ACTIVE").write_text(version, encoding="utf-8")
    events.emit(
        session, "skill_model.promoted", ("skill_model", f"{role}@{version}"),
        {"active": previous}, {"active": version, "signed_by": signed_by}, actor,
    )
    return card
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_package.py --no-cov -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/package.py node/mia/settings.py .env.example node/tests/learning/test_package.py
git commit -m "learning: model card, active marker and signed promotion with event"
```

---

### Task 8: Runtime classifier registry

**Files:**
- Create: `node/mia/skills/__init__.py`, `node/mia/skills/runtime.py`
- Test: `node/tests/skills/__init__.py`, `node/tests/skills/test_runtime.py`

**Interfaces:**
- Consumes: `active_version`, `read_card`, `ModelCard`, `softmax`.
- Produces:
  - `Band = Literal["high", "medium", "low"]`
  - `class Alternative(BaseModel)`: `intent: str`, `confidence: float`
  - `class Classification(BaseModel)`: `intent, confidence, band, alternatives: list[Alternative], lang: str | None, slots: dict[str, str], safety: float, version: str | None`
  - `class Classifier(Protocol)`: `def classify(self, text: str, context: str = "") -> Classification`
  - `class NullClassifier`: always `intent="other", band="low", version=None`
  - `class ScoredClassifier`: base that turns `(card, logits_intent, logits_lang, slot_logits)` into a `Classification` with bands from the card (shared by the ONNX classifier in Task 15)
  - `get_classifier(role: str) -> Classifier` (cached; falls back to `NullClassifier` when no active version or a corrupt package, logging a warning); `reset_classifiers() -> None`; `health() -> dict[str, dict[str, object]]`

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/skills/test_runtime.py
from pathlib import Path

import pytest

from mia.learning.gate import GateResult
from mia.learning.metrics import EvalReport
from mia.learning.package import ModelCard, write_card
from mia.settings import get_settings
from mia.skills.runtime import NullClassifier, ScoredClassifier, get_classifier, health, reset_classifiers


@pytest.fixture(autouse=True)
def models_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIA_MODELS_DIR", str(tmp_path / "models"))
    get_settings.cache_clear()
    reset_classifiers()


def card() -> ModelCard:
    rep = EvalReport(accuracy=1, macro_f1=1, coverage=1, ece=0, per_intent={}, per_lang={},
                     safety_recall=1, actions_from_other=0, confusions=[])
    return ModelCard(role="r", version="v1", base_model="m", data_hash="h", temperature=1.0, medium_floor=0.35,
                     safety_floor=0.2, labels=["r.a", "r.b", "conversation.emergency", "other"],
                     langs=["en", "fi"], slots={}, thresholds={"r.a": 0.8, "r.b": 0.8},
                     report=rep, gate=GateResult(passed=True))


def test_no_package_means_null_classifier() -> None:
    c = get_classifier("dispatcher").classify("im sick")
    assert (c.intent, c.band, c.version) == ("other", "low", None)
    assert isinstance(get_classifier("dispatcher"), NullClassifier)


def test_corrupt_package_falls_back_and_health_says_so() -> None:
    root = get_settings().MIA_MODELS_DIR / "r"
    root.mkdir(parents=True)
    (root / "ACTIVE").write_text("v9")
    assert isinstance(get_classifier("r"), NullClassifier)
    assert health()["r"]["status"] == "fallback"


def test_bands_from_card() -> None:
    sc = ScoredClassifier(card(), safety={"conversation.emergency"})
    high = sc.from_logits([6, 0, 0, 0], [3, 0], {})
    medium = sc.from_logits([1.2, 1.0, 0, 0], [3, 0], {})
    low = sc.from_logits([0.1, 0.1, 0.1, 0.1], [3, 0], {})
    assert (high.band, medium.band, low.band) == ("high", "medium", "low")
    assert [a.intent for a in medium.alternatives][:2] == ["r.a", "r.b"]
    assert high.lang == "en"
    alarm = sc.from_logits([2, 0, 1.5, 0], [3, 0], {})
    assert alarm.safety >= 0.2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/skills/test_runtime.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.skills'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/skills/__init__.py
"""Node runtime for role skill models: classification and per-turn routing."""
```

```python
# node/mia/skills/runtime.py
"""Load each role's active model and classify messages (spec section 5, runtime)."""

import logging
from functools import lru_cache
from typing import Literal, Protocol

from pydantic import BaseModel

from mia.learning import catalogue
from mia.learning.metrics import softmax
from mia.learning.package import ModelCard, active_version, read_card

log = logging.getLogger(__name__)
Band = Literal["high", "medium", "low"]


class Alternative(BaseModel):
    intent: str
    confidence: float


class Classification(BaseModel):
    intent: str
    confidence: float
    band: Band
    alternatives: list[Alternative]
    lang: str | None
    slots: dict[str, str]
    safety: float
    version: str | None


class Classifier(Protocol):
    def classify(self, text: str, context: str = "") -> Classification: ...


class NullClassifier:
    """No active package: every message is low band, so the agent runs as it does today."""

    def classify(self, text: str, context: str = "") -> Classification:
        return Classification(intent="other", confidence=0.0, band="low", alternatives=[], lang=None,
                              slots={}, safety=0.0, version=None)


class ScoredClassifier:
    """Turns model scores into a Classification using the card's calibration and thresholds."""

    def __init__(self, card: ModelCard, safety: set[str]) -> None:
        self.card = card
        self.safety = safety

    def from_logits(
        self, intent_logits: list[float], lang_logits: list[float], slot_logits: dict[str, list[float]]
    ) -> Classification:
        c = self.card
        probs = softmax(intent_logits, c.temperature)
        ranked = sorted(zip(c.labels, probs, strict=True), key=lambda x: x[1], reverse=True)
        intent, conf = ranked[0]
        if conf >= c.thresholds.get(intent, 1.01):
            band: Band = "high"
        elif conf >= c.medium_floor and intent != "other":
            band = "medium"
        else:
            band = "low"
        lang_probs = softmax(lang_logits) if lang_logits else []
        lang = c.langs[max(range(len(lang_probs)), key=lang_probs.__getitem__)] if lang_probs else None
        slots = {
            name: c.slots[name][max(range(len(v)), key=v.__getitem__)]
            for name, v in slot_logits.items()
            if name in c.slots and v
        }
        return Classification(
            intent=intent, confidence=conf, band=band,
            alternatives=[Alternative(intent=i, confidence=p) for i, p in ranked[:3] if i != "other"],
            lang=lang, slots=slots, safety=sum(p for i, p in ranked if i in self.safety),
            version=c.version,
        )


_status: dict[str, dict[str, object]] = {}


@lru_cache
def get_classifier(role: str) -> Classifier:
    version = active_version(role)
    if version is None:
        _status[role] = {"status": "none", "version": None}
        return NullClassifier()
    try:
        card = read_card(role, version)
        from mia.skills.onnx import OnnxClassifier  # Task 15; needs onnxruntime (Task 13)

        classifier: Classifier = OnnxClassifier(card, safety=catalogue.safety_ids())
    except Exception as exc:  # noqa: BLE001 - any broken package falls back, never breaks chat
        log.warning("role %s model %s unusable, falling back: %s", role, version, exc)
        _status[role] = {"status": "fallback", "version": version, "error": str(exc)[:200]}
        return NullClassifier()
    _status[role] = {"status": "active", "version": version}
    return classifier


def reset_classifiers() -> None:
    get_classifier.cache_clear()
    _status.clear()


def health() -> dict[str, dict[str, object]]:
    return dict(_status)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/skills/test_runtime.py --no-cov -q`
Expected: PASS (3 passed). `test_corrupt_package_falls_back_and_health_says_so` passes because `read_card` raises before the ONNX import.

- [ ] **Step 5: Commit**

```bash
git add node/mia/skills node/tests/skills
git commit -m "skills: classification, bands from the model card, null fallback and health"
```

---

### Task 9: Per-turn routing

**Files:**
- Create: `node/mia/skills/routing.py`
- Test: `node/tests/skills/test_routing.py`

**Interfaces:**
- Consumes: `Classification`, `RoleSpec`, `catalogue.conversation_intents()`.
- Produces:
  - `class Route(BaseModel)`: `kind: Literal["emergency", "template", "agent", "clarify"]`, `intent: str | None`, `options: list[str]` (intent ids for clarify)
  - `route(c: Classification, role: RoleSpec | None, safety_floor: float = 0.2) -> Route`
- Rules (spec section 7): emergency first when `c.safety >= safety_floor`; `other` never `template`; high band: role intent with handler `template` or conversation intent with handling `template` -> `template`; every other high band (handlers `agent` and `tool`, see Task 18 note) -> `agent` with the intent; medium -> `clarify` with up to 3 non-`other` alternatives; low -> `agent` with no intent.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/skills/test_routing.py
from mia.learning.schema import IntentSpec, RoleSpec
from mia.skills.routing import route
from mia.skills.runtime import Alternative, Classification

ROLE = RoleSpec(
    id="dispatcher", job_summary="j", responsibilities=["x"], counterparts=[], languages=["en"],
    countries=["FI"], styles={"informal": 1.0},
    intents=[
        IntentSpec(id="dispatcher.report_absence", description="d", counterparts=["c"], risk="write", label_en="Report I'm sick"),
        IntentSpec(id="dispatcher.thanks_reply", description="d", counterparts=["c"], risk="read", label_en="Thanks", handler="template"),
    ],
)


def c(intent: str, band: str, safety: float = 0.0, alts: list[str] | None = None) -> Classification:
    return Classification(intent=intent, confidence=0.9, band=band, lang="en", slots={}, safety=safety, version="v1",
                          alternatives=[Alternative(intent=a, confidence=0.4) for a in (alts or [])])  # type: ignore[arg-type]


def test_safety_wins_over_everything() -> None:
    assert route(c("dispatcher.report_absence", "high", safety=0.3), ROLE).kind == "emergency"


def test_high_band_template_and_agent() -> None:
    assert route(c("dispatcher.thanks_reply", "high"), ROLE).kind == "template"
    assert route(c("conversation.greeting", "high"), ROLE).kind == "template"
    r = route(c("dispatcher.report_absence", "high"), ROLE)
    assert (r.kind, r.intent) == ("agent", "dispatcher.report_absence")


def test_other_and_injection_never_act() -> None:
    assert route(c("other", "high"), ROLE).kind == "agent"
    assert route(c("other", "high"), ROLE).intent is None


def test_medium_clarifies_with_alternatives_and_low_runs_agent() -> None:
    r = route(c("dispatcher.report_absence", "medium", alts=["dispatcher.report_absence", "conversation.venting"]), ROLE)
    assert (r.kind, r.options) == ("clarify", ["dispatcher.report_absence", "conversation.venting"])
    assert route(c("dispatcher.report_absence", "low"), ROLE).kind == "agent"


def test_no_role_plan_means_agent() -> None:
    assert route(c("dispatcher.report_absence", "high"), None).kind == "agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/skills/test_routing.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.skills.routing'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/skills/routing.py
"""Decide what one turn does from its classification (spec section 7)."""

from typing import Literal

from pydantic import BaseModel, Field

from mia.learning import catalogue
from mia.learning.schema import RoleSpec
from mia.skills.runtime import Classification


class Route(BaseModel):
    kind: Literal["emergency", "template", "agent", "clarify"]
    intent: str | None = None
    options: list[str] = Field(default_factory=list)


def _conversation_handling() -> dict[str, str]:
    return {ci.id: ci.handling for ci in catalogue.conversation_intents()}


def route(c: Classification, role: RoleSpec | None, safety_floor: float = 0.2) -> Route:
    if c.safety >= safety_floor:
        return Route(kind="emergency", intent=c.intent)
    if role is None or c.intent == "other":
        return Route(kind="agent")
    if c.band == "medium":
        options = [a.intent for a in c.alternatives if a.intent != "other"][:3]
        return Route(kind="clarify", options=options) if options else Route(kind="agent")
    if c.band == "low":
        return Route(kind="agent")
    spec = role.intent(c.intent)
    template = (spec is not None and spec.handler == "template") or (
        spec is None and _conversation_handling().get(c.intent) == "template"
    )
    return Route(kind="template" if template else "agent", intent=c.intent)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/skills/test_routing.py --no-cov -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/skills/routing.py node/tests/skills/test_routing.py
git commit -m "skills: per-turn routing (safety, template, agent, clarify)"
```

---

### Task 10: Chat integration

**Files:**
- Modify: `node/mia/chat/service.py` (`run_turn`, new helpers `_classify_turn`, `_reply_template`, `_reply_clarify`, `_reply_emergency`, `_resolve_clarification`)
- Modify: `node/mia/agents/base.py` (`AgentDeps`: add `intent: str | None = None`)
- Modify: `node/mia/agents/dispatcher/agent.py` (replace `intent_hint` with `classified_intent`)
- Modify: `node/mia/i18n/strings.py` (keys below, en and fi)
- Create: `node/mia/skills/roles.py` (`load_role_plan(role_id) -> RoleSpec | None` from `node/mia/agents/<role>/skill/role.yaml`, cached)
- Create: `node/mia/agents/dispatcher/skill/role.yaml` (seed: the six built dispatcher intents `dispatcher.report_absence`, `dispatcher.absence_scope`, `dispatcher.my_visits`, `dispatcher.find_cover`, `dispatcher.assign`, `dispatcher.cover_reply` with descriptions and `label_en` from docs/capabilities.md, `handler: agent`, languages `[en, fi]`, country `FI`, counterparts cleaner 0.8 and supervisor 0.2; routing needs a plan before the first model exists)
- Test: `node/tests/skills/test_chat_routing.py`

**Interfaces:**
- Consumes: `get_classifier`, `route`, `Route`, `RoleSpec.intent`, `notify` from `mia.chat.channels`, `t` from `mia.i18n`, `events.emit`.
- Produces: `AgentDeps.intent`; events `intent.classified` (after: role, version, intent, band, latency_ms; no text), `intent.clarify_asked` (after: options mapping label -> intent, message_id), `intent.clarified` (after: chosen intent, asked_event_id, original_message_id); i18n keys `clarify.question`, `clarify.something_else`, `clarify.rephrase`, `safety.emergency_FI`, `safety.emergency_PH`, `conversation.<id>` for every `template` conversation intent, `intent.<role intent id>` labels (en from `label_en`, fi written by a person).

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/skills/test_chat_routing.py
import asyncio

import pytest
from sqlmodel import Session, select

from mia.agents.dispatcher.agent import create_agent
from mia.chat.service import run_turn
from mia.core.models import Event, Person
from mia.skills import runtime
from mia.skills.runtime import Alternative, Classification


class Fixed:
    def __init__(self, c: Classification) -> None:
        self.c = c

    def classify(self, text: str, context: str = "") -> Classification:
        return self.c


def cls(intent: str, band: str, alts: list[str] | None = None, safety: float = 0.0) -> Classification:
    return Classification(intent=intent, confidence=0.9, band=band, lang="en", slots={}, safety=safety, version="v1",
                          alternatives=[Alternative(intent=a, confidence=0.4) for a in (alts or [])])  # type: ignore[arg-type]


@pytest.fixture
def use(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def _use(c: Classification) -> None:
        monkeypatch.setattr(runtime, "get_classifier", lambda role: Fixed(c))
    return _use


def test_no_model_behaves_as_today(session: Session, people: dict[str, Person]) -> None:
    reply = asyncio.run(run_turn(session, create_agent("test"), people["Juha"], "Olen kipeä huomenna."))
    assert "Kirjasin" in reply.text()


def test_medium_band_asks_with_buttons_and_records(session: Session, people: dict[str, Person], use) -> None:  # type: ignore[no-untyped-def]
    use(cls("dispatcher.report_absence", "medium", alts=["dispatcher.report_absence", "dispatcher.my_visits"]))
    reply = asyncio.run(run_turn(session, create_agent("test"), people["Juha"], "huomenna ei"))
    quick = [b for b in reply.blocks if b.type == "quick_replies"]
    assert quick and len(quick[0].options) == 3  # two intents plus "Something else"
    assert session.exec(select(Event).where(Event.action == "intent.clarify_asked")).first()


def test_tapping_an_option_resolves_and_free_text_does_not(session: Session, people: dict[str, Person], use) -> None:  # type: ignore[no-untyped-def]
    use(cls("dispatcher.report_absence", "medium", alts=["dispatcher.report_absence", "dispatcher.my_visits"]))
    first = asyncio.run(run_turn(session, create_agent("test"), people["Juha"], "huomenna ei"))
    session.commit()
    label = next(b for b in first.blocks if b.type == "quick_replies").options[0]
    asyncio.run(run_turn(session, create_agent("test"), people["Juha"], label, first.thread_id))
    clarified = session.exec(select(Event).where(Event.action == "intent.clarified")).all()
    assert len(clarified) == 1 and clarified[0].after["intent"] == "dispatcher.report_absence"  # type: ignore[index]
    asyncio.run(run_turn(session, create_agent("test"), people["Juha"], "the first one", first.thread_id))
    assert len(session.exec(select(Event).where(Event.action == "intent.clarified")).all()) == 1


def test_emergency_script_first(session: Session, people: dict[str, Person], use) -> None:  # type: ignore[no-untyped-def]
    use(cls("conversation.emergency", "high", safety=0.9))
    reply = asyncio.run(run_turn(session, create_agent("test"), people["Juha"], "someone collapsed"))
    assert "112" in reply.text()


def test_high_band_still_checks_permissions(session: Session, people: dict[str, Person], use) -> None:  # type: ignore[no-untyped-def]
    use(cls("dispatcher.assign", "high"))
    reply = asyncio.run(run_turn(session, create_agent("test"), people["Juha"], "Assign Mikael."))
    tool_events = session.exec(select(Event).where(Event.action == "tool.called")).all()
    assert all(e.after.get("output", {}).get("status") != "ok" or "assign_cover" not in e.entity_id  # type: ignore[union-attr]
               for e in tool_events)
    assert reply.text()


def test_classification_event_has_no_text(session: Session, people: dict[str, Person], use) -> None:  # type: ignore[no-untyped-def]
    use(cls("conversation.greeting", "high"))
    asyncio.run(run_turn(session, create_agent("test"), people["Juha"], "moi moi secret text"))
    ev = session.exec(select(Event).where(Event.action == "intent.classified")).first()
    assert ev is not None and "secret" not in str(ev.after)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/skills/test_chat_routing.py --no-cov -q`
Expected: FAIL (no clarify blocks, no `intent.*` events)

- [ ] **Step 3: Write the implementation**

`node/mia/skills/roles.py`:

```python
"""Find a role's approved plan next to its agent (node/mia/agents/<role>/skill/role.yaml)."""

from functools import lru_cache
from pathlib import Path

from mia.learning.schema import RoleSpec, load_role

AGENTS = Path(__file__).resolve().parent.parent / "agents"


@lru_cache
def load_role_plan(role_id: str) -> RoleSpec | None:
    path = AGENTS / role_id / "skill" / "role.yaml"
    return load_role(path) if path.exists() else None
```

In `node/mia/agents/base.py`, `AgentDeps`, add after `manifest: Manifest`:

```python
    intent: str | None = None  # set when the role's classifier is confident (skills.routing)
```

In `node/mia/agents/dispatcher/agent.py`, replace the `HINTS` table and `intent_hint` with:

```python
def classified_intent(ctx: RunContext[AgentDeps]) -> str:
    """Task context: the role classifier's reading of the latest message, if confident."""
    if ctx.deps.intent is None:
        return ""
    return f"Classifier: the message is {ctx.deps.intent}; act on that unless the message says otherwise."
```

and change `context=[open_cover_request, intent_hint]` to `context=[open_cover_request, classified_intent]`. Remove the now unused `import html` and `classify` import. Update `node/tests/test_egress.py::test_classifier_hint_reaches_the_model` to set `deps.intent` through a fixed classifier (as in Step 1's `use`) and assert `"Classifier: the message is dispatcher.report_absence"` is in the request body.

In `node/mia/i18n/strings.py` add to `"en"`:

```python
        "clarify.question": "Did you mean:",
        "clarify.something_else": "Something else",
        "clarify.rephrase": "Sorry, I did not get that. Could you say it in other words?",
        "safety.emergency_FI": "If anyone is in danger, call 112 now. Poison information: 0800 147 111. I have told your supervisor.",
        "safety.emergency_PH": "If anyone is in danger, call 911 now. Crisis line: 1553. I have told your supervisor.",
        "safety.supervisor_notice": "{name} may need urgent help: \"{text}\"",
        "conversation.greeting": "Hi! How can I help with your work today?",
        "conversation.thanks": "You're welcome!",
```

and the same keys to `"fi"`:

```python
        "clarify.question": "Tarkoititko:",
        "clarify.something_else": "Jotain muuta",
        "clarify.rephrase": "Anteeksi, en ymmärtänyt. Voisitko sanoa sen toisin?",
        "safety.emergency_FI": "Jos joku on vaarassa, soita heti 112. Myrkytystietokeskus: 0800 147 111. Kerroin esihenkilöllesi.",
        "safety.emergency_PH": "Jos joku on vaarassa, soita heti 911. Kriisilinja: 1553. Kerroin esihenkilöllesi.",
        "safety.supervisor_notice": "{name} voi tarvita kiireellistä apua: \"{text}\"",
        "conversation.greeting": "Hei! Miten voin auttaa työasioissa tänään?",
        "conversation.thanks": "Ole hyvä!",
```

Add one `conversation.<id>` key per `template` conversation intent in `node/mia/learning/catalogue/conversation.yaml` in both languages (the i18n parity test fails until every key exists in both). For role intent labels add `intent.<id>` keys for the six dispatcher intents in the seed role.yaml (en from `label_en`, fi written by a person, for example `"intent.dispatcher.report_absence": "Ilmoita poissaolo"`), and a `reply.<id>` key for every role intent whose handler is `template` (none in the seed).

In `node/mia/chat/service.py`, add helpers and use them in `run_turn`:

```python
import time

from mia.chat.blocks import QuickRepliesBlock, TextBlock
from mia.chat.channels import notify
from mia.core import events
from mia.i18n import t
from mia.skills import runtime
from mia.skills.roles import load_role_plan
from mia.skills.routing import Route, route

ROLE = "dispatcher"  # ponytail: one agent per chat today; read it from the thread when there are more


def _last_question(session: Session, thread: Thread) -> str:
    row = session.exec(
        select(Message).where(Message.thread_id == thread.id).where(Message.role == "assistant")
        .order_by(col(Message.id).desc())
    ).first()
    return row.text if row else ""


def _pending_clarification(session: Session, thread: Thread) -> Event | None:
    """The clarify question asked as the last assistant message of this thread, if any."""
    asked = session.exec(
        select(Event).where(Event.action == "intent.clarify_asked").where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = session.exec(
        select(Message).where(Message.thread_id == thread.id).where(Message.role == "assistant")
        .order_by(col(Message.id).desc())
    ).first()
    if asked is None or last is None or asked.after is None or asked.after.get("message_id") != last.id:
        return None
    return asked


def _classify_turn(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Route:
    """Exact option labels resolve a pending question; everything else is classified."""
    pending = _pending_clarification(session, thread)
    if pending is not None and pending.after is not None:
        chosen = pending.after["options"].get(text.strip())
        if chosen is not None:
            events.emit(session, "intent.clarified", ("thread", thread.id), None,
                        {"intent": chosen, "asked_event_id": pending.id,
                         "original_message_id": pending.after["original_message_id"]}, deps.actor)
            return Route(kind="agent", intent=chosen)
    role = load_role_plan(ROLE)
    start = time.perf_counter()
    c = runtime.get_classifier(ROLE).classify(text, _last_question(session, thread))
    events.emit(session, "intent.classified", ("thread", thread.id), None,
                {"role": ROLE, "version": c.version, "intent": c.intent, "band": c.band,
                 "latency_ms": round((time.perf_counter() - start) * 1000)}, deps.actor)
    floor = role.targets.safety_floor if role else 0.2
    return route(c, role, safety_floor=floor)
```

Replace the body of `run_turn` with:

```python
    thread, past, deps, ctx = await asyncio.to_thread(_prepare, session, person, text, thread_id)
    decided = await asyncio.to_thread(_classify_turn, session, deps, thread, text)
    if decided.kind == "emergency":
        return await asyncio.to_thread(_reply_emergency, session, deps, thread, text)
    if decided.kind == "template" and decided.intent:
        key = (
            f"conversation.{decided.intent.split('.', 1)[1]}"
            if decided.intent.startswith("conversation.")
            else f"reply.{decided.intent}"
        )
        return await asyncio.to_thread(_reply_text, session, deps, thread, t(key, deps.lang))
    if decided.kind == "clarify":
        return await asyncio.to_thread(_reply_clarify, session, deps, thread, decided.options)
    deps.intent = decided.intent
    with egress_context(ctx):
        result = await agent.run(wrap_user_text(text, person), deps=deps, message_history=past)
    return await asyncio.to_thread(_finish, session, deps, thread, result)
```

with the three reply helpers (they store the assistant message like `_finish`, so history stays complete):

```python
def _store_reply(session: Session, deps: AgentDeps, thread: Thread, blocks: list[Block]) -> ChatReply:
    text = "\n".join(b.text for b in blocks if b.type == "text")
    message = store.insert(
        session,
        Message(branch_id=deps.branch.id, thread_id=thread.id, role="assistant",
                sender_id=MANIFEST.roles.agent_role, agent_id=MANIFEST.id, text=text,
                blocks=[b.model_dump(mode="json") for b in blocks], model_messages=[]),
        deps.actor,
    )
    return ChatReply(thread_id=thread.id, message_id=message.id, agent_id=MANIFEST.id, blocks=blocks)


def _reply_text(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply:
    return _store_reply(session, deps, thread, [TextBlock(text=text)])


def _reply_clarify(session: Session, deps: AgentDeps, thread: Thread, options: list[str]) -> ChatReply:
    labels = {t(f"intent.{i}", deps.lang) if not i.startswith("conversation.") else t(f"conversation.label.{i.split('.', 1)[1]}", deps.lang): i for i in options}
    other = t("clarify.something_else", deps.lang)
    reply = _store_reply(session, deps, thread, [
        TextBlock(text=t("clarify.question", deps.lang)),
        QuickRepliesBlock(options=[*labels, other]),
    ])
    user = session.exec(select(Message).where(Message.thread_id == thread.id).where(Message.role == "user")
                        .order_by(col(Message.id).desc())).first()
    events.emit(session, "intent.clarify_asked", ("thread", thread.id), None,
                {"options": {**labels, other: "other"}, "message_id": reply.message_id,
                 "original_message_id": user.id if user else None}, deps.actor)
    return reply


def _reply_emergency(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply:
    country = "PH" if deps.branch.timezone.startswith("Asia/Manila") else "FI"
    supervisors = [p for p in session.exec(select(Person).where(Person.branch_id == deps.branch.id))
                   if "supervisor" in p.roles]
    for sup in supervisors:
        notify(session, sup, [TextBlock(text=t("safety.supervisor_notice", sup.language, name=deps.person.name, text=text[:200]))],
               deps.actor, MANIFEST.id, urgent=True)
    return _reply_text(session, deps, thread, t(f"safety.emergency_{country}", deps.lang))
```

Notes for the implementer: keep imports sorted (ruff I); `Block`, `Event`, `Person`, `col`, `select`, `store`, `MANIFEST` already exist in the module or must be imported from `mia.chat.blocks`, `mia.core.models`, `sqlmodel`, `mia.core` and `mia.agents.dispatcher.agent`; `notify` has the signature in `node/mia/chat/channels.py:23` (check its parameters and adapt the call); `conversation.label.<id>` keys are short option labels for conversation intents and need en and fi entries for every conversation intent that can appear as an option. A label that is not unique within one question (two intents with the same label) must get a numeric suffix so the mapping stays one-to-one.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/skills/test_chat_routing.py --no-cov -q && uv run pytest -q`
Expected: PASS for the new file, and the whole suite stays green (the rules-model evals too: `uv run pytest node/tests/evals -m evals --no-cov -q`).

- [ ] **Step 5: Commit**

```bash
git add node/mia/chat/service.py node/mia/agents/base.py node/mia/agents/dispatcher/agent.py node/mia/agents/dispatcher/skill/role.yaml node/mia/i18n/strings.py node/mia/skills/roles.py node/tests/skills/test_chat_routing.py node/tests/test_egress.py
git commit -m "chat: classify every turn; emergency script, templates, Did you mean, agent with intent"
```

---

### Task 11: Harvest learning candidates

**Files:**
- Create: `node/mia/learning/harvest.py`
- Test: `node/tests/learning/test_harvest.py`

**Interfaces:**
- Consumes: events `intent.clarified`, `intent.clarify_asked`, `tool.called`, `Message`, `Pseudonymiser.for_branch(session, branch_id).apply(text)`, `Record`, `write_records`, `load_records`, `MIA_LEARNING_DIR`.
- Produces: `harvest(session: Session, role: str, branch_id: str) -> list[Record]` writing `MIA_LEARNING_DIR/<role>/candidates.jsonl` (append, de-duplicated by id). Records: `source="real-clarification"`, `review.status="pending"`, `split="train"`, `kind="normal"`, `id=f"{role}/real/{message_id}"`, text pseudonymised, `context` the previous assistant message text. Kept only when the chosen intent is not `other` and the thread has no later `intent.clarified` correction for the same original message and no later undo event (`absence.cancelled`, `cover.cancelled`) in that thread within one hour. Special category text (matches the shared catalogue's privacy and health handling, here: the record is dropped if the chosen intent is a `conversation.privacy_*` or `conversation.health_*` intent) is never written.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_harvest.py
import asyncio
from pathlib import Path

import pytest
from sqlmodel import Session

from mia.agents.dispatcher.agent import create_agent
from mia.chat.service import run_turn
from mia.core.models import Person
from mia.learning.harvest import harvest
from mia.learning.schema import load_records
from mia.settings import get_settings
from mia.skills import runtime
from mia.skills.runtime import Alternative, Classification


class Fixed:
    def classify(self, text: str, context: str = "") -> Classification:
        return Classification(intent="dispatcher.report_absence", confidence=0.5, band="medium", lang="fi",
                              slots={}, safety=0.0, version="v1",
                              alternatives=[Alternative(intent="dispatcher.report_absence", confidence=0.5),
                                            Alternative(intent="dispatcher.my_visits", confidence=0.3)])


@pytest.fixture(autouse=True)
def learning_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIA_LEARNING_DIR", str(tmp_path / "learning"))
    get_settings.cache_clear()
    monkeypatch.setattr(runtime, "get_classifier", lambda role: Fixed())


def test_clarified_choice_becomes_a_pending_pseudonymised_candidate(session: Session, people: dict[str, Person]) -> None:
    juha = people["Juha"]
    first = asyncio.run(run_turn(session, create_agent("test"), juha, "Juha Laine ei pääse huomenna"))
    session.commit()
    label = next(b for b in first.blocks if b.type == "quick_replies").options[0]
    asyncio.run(run_turn(session, create_agent("test"), juha, label, first.thread_id))
    session.commit()
    out = harvest(session, "dispatcher", juha.branch_id)
    assert len(out) == 1
    rec = out[0]
    assert rec.intent == "dispatcher.report_absence" and rec.review.status == "pending"
    assert "Juha" not in rec.text and "Person_" in rec.text
    path = get_settings().MIA_LEARNING_DIR / "dispatcher" / "candidates.jsonl"
    assert load_records(path) == out
    assert harvest(session, "dispatcher", juha.branch_id) == []  # idempotent
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/learning/test_harvest.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning.harvest'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/learning/harvest.py
"""Turn clarification choices into pending candidate records on the node (spec section 8)."""

import datetime as dt

from sqlmodel import Session, col, select

from mia.core.egress import Pseudonymiser
from mia.core.models import Event, Message
from mia.learning.schema import Record, Review, load_records, write_records
from mia.settings import get_settings

UNDO = {"absence.cancelled", "cover.cancelled"}
SENSITIVE_PREFIXES = ("conversation.privacy", "conversation.health")


def _later(session: Session, thread_id: str, after_id: str, actions: set[str]) -> bool:
    rows = session.exec(
        select(Event).where(Event.entity_id == thread_id).where(col(Event.id) > after_id)
        .where(col(Event.action).in_(actions))
    ).all()
    return bool(rows)


def harvest(session: Session, role: str, branch_id: str) -> list[Record]:
    """New candidates only; existing ones in candidates.jsonl are not duplicated."""
    path = get_settings().MIA_LEARNING_DIR / role / "candidates.jsonl"
    existing = {r.id for r in load_records(path)} if path.exists() else set()
    pseudo = Pseudonymiser.for_branch(session, branch_id)
    found: list[Record] = []
    for ev in session.exec(
        select(Event).where(Event.action == "intent.clarified").where(Event.branch_id == branch_id)
        .order_by(col(Event.id))
    ):
        after = ev.after or {}
        intent, original_id = after.get("intent"), after.get("original_message_id")
        if not intent or intent == "other" or not original_id or intent.startswith(SENSITIVE_PREFIXES):
            continue
        rid = f"{role}/real/{original_id}"
        if rid in existing or _later(session, ev.entity_id, ev.id, {"intent.clarified", *UNDO}):
            continue
        message = session.get(Message, original_id)
        if message is None:
            continue
        previous = session.exec(
            select(Message).where(Message.thread_id == message.thread_id).where(Message.role == "assistant")
            .where(col(Message.id) < message.id).order_by(col(Message.id).desc())
        ).first()
        found.append(Record(
            id=rid, role=role, intent=intent, lang="mixed", text=pseudo.apply(message.text),
            context=pseudo.apply(previous.text) if previous else "", counterpart="unknown",
            style="informal", split="train", source="real-clarification",
            review=Review(status="pending", note=f"harvested {dt.datetime.now(dt.UTC).date()}"),
        ))
    if found:
        write_records(path, [*(load_records(path) if path.exists() else []), *found])
    return found
```

Note: `lang="mixed"` is a placeholder label until the reviewer step sets the real language; the reviewer must set it before approval (Task 17's SKILL.md says so).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_harvest.py --no-cov -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/harvest.py node/tests/learning/test_harvest.py
git commit -m "learning: harvest clarification choices into pending, pseudonymised candidates"
```

---

### Task 12: `mia skills` commands (no ML dependencies)

**Files:**
- Create: `node/mia/learning/commands.py`
- Modify: `node/mia/cli.py` (add the `skills` subparser before `def main`)
- Modify: `node/mia/api/main.py` (`/health` includes `skills: runtime.health()`)
- Test: `node/tests/learning/test_commands.py`

**Interfaces:**
- Consumes: Tasks 1 to 11.
- Produces CLI:
  - `mia skills validate <role>`: loads role.yaml, public.yaml (if present) and the three splits from `node/mia/agents/<role>/skill/data/`, runs `check_records`, prints errors and warnings, exits 1 on errors.
  - `mia skills split <role> [--seed N]`: runs `assign_train_dev` on `reviewed.jsonl` and writes `train.jsonl` and `dev.jsonl` (test comes from the generator).
  - `mia skills train <role> [--base-model M] [--with-real]`: imports `mia.learning.train` lazily and prints "install the learning group: uv sync --group learning" if it is missing (exit 2).
  - `mia skills promote <role> <version> --signed-by NAME`: calls `promote` as the system actor of the only branch; exit 1 with the reason on `PromotionRefused`.
  - `mia skills harvest <role>`: calls `harvest` for the only branch; prints the count.

- [ ] **Step 1: Write the failing tests**

```python
# node/tests/learning/test_commands.py
from pathlib import Path

import pytest

from mia.cli import main


def test_validate_reports_missing_role(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skills", "validate", "nobody"]) == 1
    assert "role.yaml not found" in capsys.readouterr().out


def test_train_without_learning_group_explains(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import builtins

    real_import = builtins.__import__

    def no_torch(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "mia.learning.train":
            raise ImportError("torch missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_torch)
    assert main(["skills", "train", "dispatcher"]) == 2
    assert "uv sync --group learning" in capsys.readouterr().out


def test_promote_refusal_is_exit_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("MIA_MODELS_DIR", str(tmp_path))
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    assert main(["skills", "promote", "dispatcher", "v1", "--signed-by", "Allan"]) == 1
    assert "not found" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest node/tests/learning/test_commands.py --no-cov -q`
Expected: FAIL with `argument command: invalid choice: 'skills'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/learning/commands.py
"""`mia skills ...` command implementations; the CLI only parses arguments."""

import argparse
from pathlib import Path

from sqlmodel import select

from mia.core.db import session_scope
from mia.core.models import Actor, Branch
from mia.learning import catalogue
from mia.learning.checks import check_records
from mia.learning.harvest import harvest
from mia.learning.package import PromotionRefused, promote
from mia.learning.schema import load_records, load_role, write_records
from mia.learning.splits import assign_train_dev

AGENTS = Path(__file__).resolve().parent.parent / "agents"


def skill_dir(role: str) -> Path:
    return AGENTS / role / "skill"


def _conversation() -> list[str]:
    return [c.id for c in catalogue.conversation_intents()]


def validate(args: argparse.Namespace) -> int:
    folder = skill_dir(args.role)
    if not (folder / "role.yaml").exists():
        print(f"role.yaml not found in {folder}")
        return 1
    role = load_role(folder / "role.yaml")
    records = [r for s in ("train", "dev", "test") if (folder / "data" / f"{s}.jsonl").exists()
               for r in load_records(folder / "data" / f"{s}.jsonl")]
    report = check_records(role, records, _conversation())
    for line in report.errors:
        print(f"error: {line}")
    for line in report.warnings:
        print(f"warning: {line}")
    print(f"{len(records)} records, {len(report.errors)} errors, {len(report.warnings)} warnings")
    return 0 if report.ok else 1


def split(args: argparse.Namespace) -> int:
    folder = skill_dir(args.role)
    role = load_role(folder / "role.yaml")
    reviewed = [r for r in load_records(folder / "data" / "reviewed.jsonl") if r.review.status != "dropped"]
    out = assign_train_dev(role, reviewed, seed=args.seed)
    for name in ("train", "dev", "test"):
        write_records(folder / "data" / f"{name}.jsonl", [r for r in out if r.split == name])
    print(" ".join(f"{n}={sum(r.split == n for r in out)}" for n in ("train", "dev", "test")))
    return 0


def train(args: argparse.Namespace) -> int:
    try:
        from mia.learning.train import train_role
    except ImportError as exc:
        print(f"training needs the learning dependency group ({exc}): uv sync --group learning")
        return 2
    card = train_role(skill_dir(args.role), base_model=args.base_model, with_real=args.with_real)
    print(f"{card.role}@{card.version}: gate {'passed' if card.gate.passed else 'failed'}")
    for f in card.gate.failures:
        print(f"  {f}")
    return 0


def _only_branch() -> Branch:
    with session_scope() as session:
        branch = session.exec(select(Branch)).one()
        session.expunge(branch)
        return branch


def promote_cmd(args: argparse.Namespace) -> int:
    branch = _only_branch()
    with session_scope() as session:
        try:
            card = promote(session, Actor.system(branch.id), args.role, args.version, args.signed_by)
        except PromotionRefused as exc:
            print(str(exc))
            return 1
    print(f"{card.role}@{card.version} is active (signed by {card.signed_by})")
    return 0


def harvest_cmd(args: argparse.Namespace) -> int:
    branch = _only_branch()
    with session_scope() as session:
        found = harvest(session, args.role, branch.id)
    print(f"{len(found)} new candidates")
    return 0


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    skills = sub.add_parser("skills", help="role skill models").add_subparsers(dest="skills_command", required=True)
    p = skills.add_parser("validate", help="check a role's data")
    p.add_argument("role")
    p.set_defaults(func=validate)
    p = skills.add_parser("split", help="assign train and dev from reviewed.jsonl")
    p.add_argument("role")
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=split)
    p = skills.add_parser("train", help="train, calibrate, evaluate and package")
    p.add_argument("role")
    p.add_argument("--base-model", default=None)
    p.add_argument("--with-real", action="store_true")
    p.set_defaults(func=train)
    p = skills.add_parser("promote", help="make a signed, gate-passing version active")
    p.add_argument("role")
    p.add_argument("version")
    p.add_argument("--signed-by", required=True)
    p.set_defaults(func=promote_cmd)
    p = skills.add_parser("harvest", help="collect clarification choices as candidates")
    p.add_argument("role")
    p.set_defaults(func=harvest_cmd)
```

In `node/mia/cli.py`, before `def main`, at the end of the parser builder after the `person` subparser:

```python
    from mia.learning.commands import register as register_skills

    register_skills(sub)
```

In `node/mia/api/main.py`, in `health`, add `"skills": runtime.health()` to the returned dict (import `from mia.skills import runtime`).

Check `session_scope` and `Actor.system` exist in `mia.core.db` and `mia.core.models` (they are used by `node/mia/cli.py`); match their exact usage there.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_commands.py --no-cov -q && uv run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/commands.py node/mia/cli.py node/mia/api/main.py node/tests/learning/test_commands.py
git commit -m "cli: mia skills validate, split, train, promote, harvest; skills on /health"
```

---

### Task 13: Approval gate and dependencies

This task needs Allan's explicit approval before any step runs (CLAUDE.md: no dependency without approval). Ask with the one-line reasons below; record the answer as a decision.

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/decisions.md` (new decision), `docs/adr/013-skill-models.md` (create), `docs/layout.md`
- Test: `node/tests/learning/test_dependencies.py`

**Interfaces:**
- Produces: dependency group `learning` (`torch`, `transformers`, `onnx`, `accelerate`); node dependencies `onnxruntime`, `tokenizers`; pytest marker `learning`.

- [ ] **Step 1: Ask for approval** with these reasons:
  - `onnxruntime` (MIT): runs the role classifier on the node's CPU in about 20 ms.
  - `tokenizers` (Apache 2.0): the encoder's tokenizer at inference, without PyTorch on the node.
  - group `learning`: `torch` (BSD), `transformers` (Apache 2.0), `onnx` (Apache 2.0), `accelerate` (Apache 2.0): training and ONNX export, installed only where training runs.

- [ ] **Step 2: Write the failing test**

```python
# node/tests/learning/test_dependencies.py
import importlib.util
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_runtime_dependencies_are_installed_and_training_is_optional() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = " ".join(project["project"]["dependencies"])
    assert "onnxruntime" in deps and "tokenizers" in deps
    assert "torch" not in deps
    assert any("torch" in d for d in project["dependency-groups"]["learning"])
    assert importlib.util.find_spec("onnxruntime") is not None
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest node/tests/learning/test_dependencies.py --no-cov -q`
Expected: FAIL (`onnxruntime` not in dependencies)

- [ ] **Step 4: Edit pyproject.toml**

Add to `dependencies`:

```toml
    "onnxruntime>=1.20",
    "tokenizers>=0.20",
```

Add to `[dependency-groups]`:

```toml
learning = [
    "torch>=2.4",
    "transformers>=4.45",
    "onnx>=1.17",
    "accelerate>=1.0",
]
```

Add to pytest `markers`: `"learning: trains a tiny model (needs uv sync --group learning)"`, and change `addopts` to `-m 'not evals and not learning'`.

Run: `uv sync && uv run pytest node/tests/learning/test_dependencies.py --no-cov -q`
Expected: PASS

- [ ] **Step 5: Write ADR 013 and the decision, update the layout**

`docs/adr/013-skill-models.md`:

```markdown
# 013: Role skill models

## Status
Accepted (decision D28).

## Context
docs/superpowers/specs/2026-10-06-skill-models-design.md: every agent role gets a multilingual
intent classifier built by the /mia-train-role Claude Code skill and the `mia skills` commands.

## Decision
- New packages node/mia/learning (offline pipeline) and node/mia/skills (node runtime), and
  node/mia/agents/<role>/skill/ for each role's plan and data.
- onnxruntime and tokenizers are node dependencies; training libraries are the optional
  `learning` group, installed only where training runs (development machines, cloud jobs, and
  nodes whose owner chose local retraining under D27).
- Built packages and harvested candidates live under MIA_MODELS_DIR and MIA_LEARNING_DIR on the
  node, never in git.

## Consequences
- A role without a promoted package behaves as before (null classifier).
- High-band tool intents run the agent with the intent as context in this version; direct slot
  to tool argument mapping is a later improvement (spec section 7 updated).
```

Append to `docs/decisions.md`:

```markdown

## D28: Role skill models
- Decision: build docs/superpowers/specs/2026-10-06-skill-models-design.md; onnxruntime and
  tokenizers become node dependencies and training libraries an optional `learning` group
  (ADR 013).
```

In `docs/layout.md`, add under `node/mia/`: `learning/   offline pipeline for role skill models (ADR 013)` and `skills/   classifier runtime and per-turn routing (ADR 013)`, and under `agents/`: `<role>/skill/   role.yaml, public.yaml, data/, reports/ (ADR 013)`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock docs/decisions.md docs/adr/013-skill-models.md docs/layout.md node/tests/learning/test_dependencies.py
git commit -m "Role skill model dependencies (D28, ADR 013)"
```

---

### Task 14: Trainer

**Files:**
- Create: `node/mia/learning/train.py`
- Create: `node/tests/fixtures/role_tiny/skill/role.yaml`, `node/tests/fixtures/role_tiny/skill/data/{train,dev,test}.jsonl` (3 intents, en and fi, about 60 records)
- Test: `node/tests/learning/test_train.py` (marker `learning`)

**Interfaces:**
- Consumes: schema, metrics, gate, package, public (Tasks 1 to 7).
- Produces: `train_role(folder: Path, base_model: str | None = None, with_real: bool = False, seeds: tuple[int, ...] = (0, 1, 2), epochs: int = 20) -> ModelCard`. Writes `MIA_MODELS_DIR/<role>/<version>/{model.onnx, tokenizer.json, card.json}` and `<folder>/reports/<version>.md`. Version: `v` + UTC timestamp `YYYYMMDDHHMM`.
- ONNX graph inputs `input_ids`, `attention_mask`; outputs `intent_logits`, `lang_logits`, and `slot_<name>_logits` per slot in `card.slots`.

- [ ] **Step 1: Create the fixture role**

`node/tests/fixtures/role_tiny/skill/role.yaml`:

```yaml
id: tiny
job_summary: Test role.
responsibilities: [absences, visits]
counterparts: [{role: cleaner, share: 1.0}]
languages: [en, fi]
countries: [FI]
styles: {informal: 1.0}
targets: {train_min: 8, train_high: 8, dev: 2, dev_high: 2, test: 3, test_high: 3, coverage: 0.0, language_gap: 1.0, ece: 1.0, precision_write: 0.0, precision_read: 0.0, safety_recall: 0.0}
intents:
  - {id: tiny.absence, description: sick or late, counterparts: [cleaner], risk: write, label_en: Report I'm sick, slots: [partial_day]}
  - {id: tiny.visits, description: own visits, counterparts: [cleaner], risk: read, label_en: Show my shifts}
base_model: hf-internal-testing/tiny-random-XLMRobertaModel
```

Write `train.jsonl` (8 per intent per language plus 4 `other`), `dev.jsonl` (2 per intent per language), `test.jsonl` (3 per intent per language) by hand, in the Record format, with realistic messages, for example `{"id": "tiny/en/1", "role": "tiny", "intent": "tiny.absence", "lang": "en", "text": "sick today, cant come", "counterpart": "cleaner", "style": "terse", "split": "train", "source": "fixture", "slots": {"partial_day": "none"}}` and `{"id": "tiny/fi/1", "role": "tiny", "intent": "tiny.absence", "lang": "fi", "text": "oon kipee tänään", ...}`.

- [ ] **Step 2: Write the failing test**

```python
# node/tests/learning/test_train.py
from pathlib import Path

import pytest

from mia.settings import get_settings

pytestmark = pytest.mark.learning
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "role_tiny" / "skill"


def test_tiny_role_trains_packages_and_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIA_MODELS_DIR", str(tmp_path / "models"))
    get_settings.cache_clear()
    from mia.learning.train import train_role

    folder = tmp_path / "skill"
    import shutil

    shutil.copytree(FIXTURE, folder)
    card = train_role(folder, seeds=(0,), epochs=1)
    out = tmp_path / "models" / "tiny" / card.version
    assert (out / "model.onnx").exists() and (out / "tokenizer.json").exists() and (out / "card.json").exists()
    assert card.labels[-1] == "other" and set(card.thresholds) == {"tiny.absence", "tiny.visits"}
    assert (folder / "reports" / f"{card.version}.md").exists()
    assert card.slots == {"partial_day": ["none"]}
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv sync --group learning && uv run pytest node/tests/learning/test_train.py -m learning --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning.train'`

- [ ] **Step 4: Write the implementation**

```python
# node/mia/learning/train.py
"""Train, calibrate, evaluate and package one role (spec section 5). Needs the learning group."""

import datetime as dt
import hashlib
import random
from pathlib import Path

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer

from mia.learning import catalogue
from mia.learning.gate import check_gate
from mia.learning.metrics import Prediction, choose_thresholds, evaluate, fit_temperature
from mia.learning.package import ModelCard, active_version, read_card, write_card
from mia.learning.schema import Record, RoleSpec, load_records, load_role
from mia.settings import get_settings

LANGS = ["en", "fi", "fil", "mixed"]
MAX_LEN = 96


class Heads(nn.Module):
    """Shared encoder, intent head, language head, one head per slot."""

    def __init__(self, base: str, n_intents: int, slots: dict[str, list[str]]) -> None:
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base)
        size = self.encoder.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.intent = nn.Linear(size, n_intents)
        self.lang = nn.Linear(size, len(LANGS))
        self.slots = nn.ModuleDict({name: nn.Linear(size, len(values)) for name, values in slots.items()})

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> tuple[torch.Tensor, ...]:
        h = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0]
        h = self.drop(h)
        return (self.intent(h), self.lang(h), *(head(h) for head in self.slots.values()))


def _slot_values(role: RoleSpec, records: list[Record]) -> dict[str, list[str]]:
    names = sorted({s for i in role.intents for s in i.slots})
    return {n: sorted({r.slots[n] for r in records if n in r.slots}) or ["none"] for n in names}


def _batches(records: list[Record], size: int, rng: random.Random) -> list[list[Record]]:
    order = records[:]
    rng.shuffle(order)
    return [order[i : i + size] for i in range(0, len(order), size)]


def _encode(tok: AutoTokenizer, batch: list[Record]) -> dict[str, torch.Tensor]:
    return tok([r.text for r in batch], [r.context or "" for r in batch], truncation=True,
               max_length=MAX_LEN, padding=True, return_tensors="pt")


def _predict(model: Heads, tok: AutoTokenizer, records: list[Record], labels: list[str]) -> list[Prediction]:
    model.eval()
    out: list[Prediction] = []
    with torch.no_grad():
        for i in range(0, len(records), 64):
            batch = records[i : i + 64]
            logits = model(**_encode(tok, batch))[0]
            out += [Prediction(record_id=r.id, intent=r.intent if r.intent in labels else "other", lang=r.lang,
                               kind=r.kind, style=r.style, labels=labels, logits=row.tolist())
                    for r, row in zip(batch, logits, strict=True)]
    return out


def _fit(base: str, role: RoleSpec, labels: list[str], slots: dict[str, list[str]], train: list[Record],
         dev: list[Record], seed: int, epochs: int, lr: float) -> tuple[Heads, float]:
    torch.manual_seed(seed)
    rng = random.Random(seed)
    tok = AutoTokenizer.from_pretrained(base)
    model = Heads(base, len(labels), slots)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps = max(1, epochs * ((len(train) + 31) // 32))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / (0.06 * steps)) * max(0.0, 1 - s / steps))
    ce = nn.CrossEntropyLoss(label_smoothing=0.1)
    best_state, best_nll, patience = None, float("inf"), 0
    for _ in range(epochs):
        model.train()
        for batch in _batches(train, 32, rng):
            out = model(**_encode(tok, batch))
            y = torch.tensor([labels.index(r.intent) if r.intent in labels else len(labels) - 1 for r in batch])
            loss = ce(out[0], y) + 0.3 * ce(out[1], torch.tensor([LANGS.index(r.lang) for r in batch]))
            for k, (name, values) in enumerate(slots.items()):
                ys = torch.tensor([values.index(r.slots.get(name, values[0])) if r.slots.get(name) in values else 0 for r in batch])
                loss = loss + 0.2 * ce(out[2 + k], ys)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
        preds = _predict(model, tok, dev, labels)
        nll = -sum(torch.log_softmax(torch.tensor(p.logits), 0)[labels.index(p.intent)].item() for p in preds)
        if nll < best_nll:
            best_nll, best_state, patience = nll, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            patience += 1
            if patience >= 3:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best_nll


def _export(model: Heads, tok: AutoTokenizer, out: Path, slots: dict[str, list[str]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    model.eval()
    sample = _encode(tok, [Record(id="x", role="x", intent="other", lang="en", text="hello", counterpart="x",
                                  style="terse", split="train", source="export")])
    names = ["intent_logits", "lang_logits", *(f"slot_{n}_logits" for n in slots)]
    torch.onnx.export(model, (sample["input_ids"], sample["attention_mask"]), out / "model.onnx",
                      input_names=["input_ids", "attention_mask"], output_names=names,
                      dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}},
                      opset_version=17)
    tok.backend_tokenizer.save(str(out / "tokenizer.json"))


def _report(card: ModelCard, curve: dict[int, float]) -> str:
    rep = card.report
    lines = [f"# {card.role} {card.version}", "", f"Base model: {card.base_model}. Data hash: {card.data_hash}.",
             f"Gate: {'passed' if card.gate.passed else 'failed'}", *(f"- {f}" for f in card.gate.failures), "",
             f"Accuracy {rep.accuracy:.3f}, macro-F1 {rep.macro_f1:.3f}, coverage {rep.coverage:.2f}, ECE {rep.ece:.3f}, "
             f"safety recall {rep.safety_recall:.3f}, actions from other {rep.actions_from_other}", "",
             "| Language | Accuracy |", "|---|---|", *(f"| {k} | {v:.3f} |" for k, v in sorted(rep.per_lang.items())), "",
             "| Intent | Support | Precision at threshold | Recall | Auto share |", "|---|---|---|---|---|",
             *(f"| {k} | {s.support} | {s.precision_at_threshold:.3f} | {s.recall:.3f} | {s.auto_share:.2f} |"
               for k, s in rep.per_intent.items()), "",
             "Learning curve (share of train: test accuracy): " + ", ".join(f"{k}%: {v:.3f}" for k, v in curve.items()),
             "", "Most confused: " + "; ".join(f"{a} -> {b} ({n})" for a, b, n in rep.confusions[:10]), "",
             "Sign-off: pending (mia skills promote ... --signed-by NAME)"]
    return "\n".join(lines) + "\n"


def train_role(folder: Path, base_model: str | None = None, with_real: bool = False,
               seeds: tuple[int, ...] = (0, 1, 2), epochs: int = 20) -> ModelCard:
    role = load_role(folder / "role.yaml")
    base = base_model or role.base_model
    data = folder / "data"
    train, dev, test = (load_records(data / f"{s}.jsonl") for s in ("train", "dev", "test"))
    if with_real:
        real = get_settings().MIA_LEARNING_DIR / role.id / "candidates.jsonl"
        approved = [r for r in load_records(real) if r.review.status in ("kept", "fixed")] if real.exists() else []
        train += [r for r in approved if r.split == "train"]
        dev += [r for r in approved if r.split == "dev"]
    conversation = [c.id for c in catalogue.conversation_intents()]
    labels = role.label_space(conversation)
    slots = _slot_values(role, train)
    tok = AutoTokenizer.from_pretrained(base)
    runs = [_fit(base, role, labels, slots, train, dev, s, epochs, lr) for s in seeds for lr in (3e-5,)]
    model, _ = min(runs, key=lambda x: x[1])
    dev_preds = _predict(model, tok, dev, labels)
    temperature = fit_temperature(dev_preds)
    thresholds = choose_thresholds(dev_preds, role, temperature)
    safety = catalogue.safety_ids()
    report = evaluate(_predict(model, tok, test, labels), role, thresholds, temperature, safety)
    previous = active_version(role.id)
    gate = check_gate(report, role, read_card(role.id, previous).report if previous else None)
    curve: dict[int, float] = {}
    for share in (25, 50, 75):
        part = random.Random(0).sample(train, max(1, len(train) * share // 100))
        m, _ = _fit(base, role, labels, slots, part, dev, seeds[0], max(1, epochs // 2), 3e-5)
        curve[share] = evaluate(_predict(m, tok, test, labels), role, thresholds, temperature, safety).accuracy
    curve[100] = report.accuracy
    version = "v" + dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M")
    digest = hashlib.sha256("".join(r.model_dump_json() for r in train + dev + test).encode()).hexdigest()[:16]
    card = ModelCard(role=role.id, version=version, base_model=base, data_hash=digest, temperature=temperature,
                     medium_floor=role.targets.medium_floor, safety_floor=role.targets.safety_floor, labels=labels,
                     langs=LANGS, slots=slots, thresholds=thresholds, report=report, gate=gate)
    out = get_settings().MIA_MODELS_DIR / role.id / version
    _export(model, tok, out, slots)
    write_card(card)
    (folder / "reports").mkdir(exist_ok=True)
    (folder / "reports" / f"{version}.md").write_text(_report(card, curve), encoding="utf-8")
    return card
```

Note: ONNX int8 quantisation (`onnxruntime.quantization.quantize_dynamic`) runs after export when the model is larger than 50 MB; add it at the end of `_export`:

```python
    if (out / "model.onnx").stat().st_size > 50_000_000:
        from onnxruntime.quantization import QuantType, quantize_dynamic

        quantize_dynamic(out / "model.onnx", out / "model.int8.onnx", weight_type=QuantType.QInt8)
        (out / "model.int8.onnx").replace(out / "model.onnx")
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest node/tests/learning/test_train.py -m learning --no-cov -q`
Expected: PASS (1 passed; under a minute on CPU with the tiny random model)

- [ ] **Step 6: Commit**

```bash
git add node/mia/learning/train.py node/tests/fixtures/role_tiny node/tests/learning/test_train.py
git commit -m "learning: trainer with intent, language and slot heads, calibration, gate, ONNX export"
```

---

### Task 15: ONNX classifier on the node

**Files:**
- Create: `node/mia/skills/onnx.py`
- Test: `node/tests/skills/test_onnx.py` (marker `learning`: it trains the tiny fixture first)

**Interfaces:**
- Consumes: `ScoredClassifier`, `ModelCard`, `package_dir`.
- Produces: `class OnnxClassifier(ScoredClassifier)` with `__init__(card: ModelCard, safety: set[str])` and `classify(text: str, context: str = "") -> Classification`; uses `onnxruntime.InferenceSession(..., providers=["CPUExecutionProvider"])` and `tokenizers.Tokenizer.from_file`.

- [ ] **Step 1: Write the failing test**

```python
# node/tests/skills/test_onnx.py
import shutil
from pathlib import Path

import pytest
from sqlmodel import Session

from mia.core.models import Actor, Person
from mia.learning.package import promote
from mia.settings import get_settings
from mia.skills.runtime import get_classifier, health, reset_classifiers

pytestmark = pytest.mark.learning
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "role_tiny" / "skill"


def test_trained_package_classifies_on_cpu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                           session: Session, people: dict[str, Person]) -> None:
    monkeypatch.setenv("MIA_MODELS_DIR", str(tmp_path / "models"))
    get_settings.cache_clear()
    reset_classifiers()
    from mia.learning.train import train_role

    folder = tmp_path / "skill"
    shutil.copytree(FIXTURE, folder)
    card = train_role(folder, seeds=(0,), epochs=1)
    promote(session, Actor.person(people["Helena"]), "tiny", card.version, signed_by="test")
    c = get_classifier("tiny").classify("oon kipee tänään")
    assert c.version == card.version and c.intent in card.labels
    assert c.band in ("high", "medium", "low") and c.lang in ("en", "fi", "fil", "mixed")
    assert health()["tiny"]["status"] == "active"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/skills/test_onnx.py -m learning --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.skills.onnx'` (runtime falls back; assertion on version fails)

- [ ] **Step 3: Write the implementation**

```python
# node/mia/skills/onnx.py
"""Run a promoted package on the CPU (onnxruntime); about 20 ms per message."""

import numpy as np
import onnxruntime
from tokenizers import Tokenizer

from mia.learning.package import ModelCard, package_dir
from mia.skills.runtime import Classification, ScoredClassifier

MAX_LEN = 96


class OnnxClassifier(ScoredClassifier):
    def __init__(self, card: ModelCard, safety: set[str]) -> None:
        super().__init__(card, safety)
        folder = package_dir(card.role, card.version)
        self.session = onnxruntime.InferenceSession(str(folder / "model.onnx"), providers=["CPUExecutionProvider"])
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(MAX_LEN)
        self.outputs = [o.name for o in self.session.get_outputs()]

    def classify(self, text: str, context: str = "") -> Classification:
        enc = self.tokenizer.encode(text, context or None)
        feeds = {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }
        values = dict(zip(self.outputs, self.session.run(self.outputs, feeds), strict=True))
        slots = {
            name.removeprefix("slot_").removesuffix("_logits"): v[0].tolist()
            for name, v in values.items()
            if name.startswith("slot_")
        }
        return self.from_logits(values["intent_logits"][0].tolist(), values["lang_logits"][0].tolist(), slots)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/skills/test_onnx.py -m learning --no-cov -q && uv run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add node/mia/skills/onnx.py node/tests/skills/test_onnx.py
git commit -m "skills: ONNX classifier on the CPU"
```

---

### Task 16: Teacher generation command

**Files:**
- Create: `node/mia/learning/generate.py`
- Modify: `node/mia/learning/commands.py` (add `mia skills generate <role> --model ROUTE --split train|test --per-cell N [--only intent,lang,...]`)
- Test: `node/tests/learning/test_generate.py`

**Interfaces:**
- Consumes: `RoleSpec`, `Record`, `write_records`, `mia.agents.base.build_model` (gateway routes go through egress, rule 6), Pydantic AI `Agent`.
- Produces: `class Cell(BaseModel)`: `intent, lang, counterpart, style, count, kind`; `plan_cells(role: RoleSpec, split: Split, per_cell: int | None) -> list[Cell]` (covers every intent by language, counterparts by share, styles by share, quotas from targets); `async generate(role, cells, model_name, prompt: str, transport=None) -> list[Record]` (one model call per cell, output type `list[GeneratedMessage]` with `text, context, slots`); records get `source=f"teacher:{model_name}"`, `split` from the call, ids `f"{intent}/{lang}/{source_tag}/{n:04d}"`.

- [ ] **Step 1: Write the failing test**

```python
# node/tests/learning/test_generate.py
import asyncio
import json

import httpx
from pydantic_ai import models

from mia.learning.generate import generate, plan_cells
from mia.learning.schema import IntentSpec, RoleSpec, Targets

ROLE = RoleSpec(
    id="r", job_summary="j", responsibilities=["x"], counterparts=[{"role": "cleaner", "share": 1.0}],  # type: ignore[list-item]
    languages=["en", "fi"], countries=["FI"], styles={"informal": 0.5, "terse": 0.5},
    intents=[IntentSpec(id="r.a", description="d", counterparts=["cleaner"], risk="read", label_en="A")],
    targets=Targets(train_min=4),
)


def test_cells_cover_every_language_and_meet_quota() -> None:
    cells = plan_cells(ROLE, "train", per_cell=None)
    assert {(c.intent, c.lang) for c in cells} == {("r.a", "en"), ("r.a", "fi")}
    assert all(sum(c.count for c in cells if c.lang == lang) >= 4 for lang in ("en", "fi"))


def test_generate_builds_records_from_the_model_output() -> None:
    args = json.dumps({"response": [{"text": "sick today", "context": "", "slots": {}}]})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                         "tool_calls": [{"id": "c", "type": "function", "function": {"name": "final_result", "arguments": args}}]}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    with models.override_allow_model_requests(True):
        recs = asyncio.run(generate(ROLE, plan_cells(ROLE, "train", per_cell=1)[:1], "local/m", "Write messages.",
                                    split="train", transport=httpx.MockTransport(handler)))
    assert recs and recs[0].source == "teacher:local/m" and recs[0].intent == "r.a"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/learning/test_generate.py --no-cov -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mia.learning.generate'`

- [ ] **Step 3: Write the implementation**

```python
# node/mia/learning/generate.py
"""Teacher generation per coverage cell (spec section 4, step 4). Synthetic data only."""

import math

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from mia.agents.base import build_model
from mia.learning.schema import Kind, Lang, Record, RoleSpec, Split, Style


class Cell(BaseModel):
    intent: str
    lang: Lang
    counterpart: str
    style: Style
    count: int
    kind: Kind = "normal"


class GeneratedMessage(BaseModel):
    text: str = Field(min_length=1)
    context: str = ""
    slots: dict[str, str] = Field(default_factory=dict)


def plan_cells(role: RoleSpec, split: Split, per_cell: int | None) -> list[Cell]:
    """Split each intent's quota per language over its counterparts and the role's styles."""
    cells: list[Cell] = []
    shares = {c.role: c.share for c in role.counterparts}
    for intent in role.intents:
        need = role.targets.quota(intent, split)
        speakers = intent.counterparts or ["unknown"]
        total_share = sum(shares.get(s, 1.0) for s in speakers)
        for lang in role.languages:
            for speaker in speakers:
                for style, share in role.styles.items():
                    n = per_cell or math.ceil(need * share * shares.get(speaker, 1.0) / total_share)
                    if n:
                        cells.append(Cell(intent=intent.id, lang=lang, counterpart=speaker, style=style, count=n))
    return cells


async def generate(role: RoleSpec, cells: list[Cell], model_name: str, prompt: str, split: Split,
                   transport: httpx.AsyncBaseTransport | None = None) -> list[Record]:
    """One call per cell; the prompt (from the skill's prompts/) describes the role and rules."""
    agent: Agent[None, list[GeneratedMessage]] = Agent(
        build_model(model_name, rules_model=None, transport=transport),  # type: ignore[arg-type]
        output_type=list[GeneratedMessage], instructions=prompt,
    )
    tag = model_name.replace("/", "-")
    out: list[Record] = []
    for cell in cells:
        spec = role.intent(cell.intent)
        ask = (f"Role: {role.id}. Intent: {cell.intent} ({spec.description if spec else 'other'}). "
               f"Language: {cell.lang}. Speaker: {cell.counterpart}. Style: {cell.style}. "
               f"Write {cell.count} different messages.")
        result = await agent.run(ask)
        for msg in result.output[: cell.count]:
            out.append(Record(id=f"{cell.intent}/{cell.lang}/{tag}/{len(out):04d}", role=role.id,
                              intent=cell.intent, lang=cell.lang, text=msg.text, context=msg.context,
                              counterpart=cell.counterpart, style=cell.style, slots=msg.slots,
                              kind=cell.kind, split=split, source=f"teacher:{model_name}"))
    return out
```

Check `build_model`'s signature in `node/mia/agents/base.py:293`: it requires `rules_model`; pass the dispatcher's `rules_model()` instead of `None` if `None` is rejected by mypy, since a `gateway/` or `local/` route never uses it. Add the `generate` subcommand to `commands.register`: it reads `role.yaml`, reads the prompt from `.claude/skills/mia-train-role/prompts/generator.md`, calls `asyncio.run(generate(...))`, and appends to `data/generated.jsonl` (or writes `data/test.jsonl` when `--split test`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_generate.py --no-cov -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add node/mia/learning/generate.py node/mia/learning/commands.py node/tests/learning/test_generate.py
git commit -m "learning: teacher generation per coverage cell (mia skills generate)"
```

---

### Task 17: The `/mia-train-role` Claude Code skill

**Files:**
- Create: `.claude/skills/mia-train-role/SKILL.md`
- Create: `.claude/skills/mia-train-role/guidelines.md`
- Create: `.claude/skills/mia-train-role/prompts/planner.md`, `prompts/generator.md`, `prompts/reviewer.md`, `prompts/public-research.md`
- Test: `node/tests/learning/test_skill_files.py`

**Interfaces:**
- Consumes: the `mia skills` commands (Tasks 12, 14, 16), the spec.
- Produces: a skill that follows spec section 4 steps 1 to 9 with gate 1 and gate 2.

- [ ] **Step 1: Write the failing test**

```python
# node/tests/learning/test_skill_files.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / ".claude" / "skills" / "mia-train-role"


def test_skill_has_steps_gates_and_prompts() -> None:
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: mia-train-role\n")
    for marker in ("Gate 1", "Gate 2", "mia skills validate", "mia skills train", "mia skills promote", "public.yaml"):
        assert marker in text, marker
    for prompt in ("planner", "generator", "reviewer", "public-research"):
        assert (SKILL / "prompts" / f"{prompt}.md").exists()
    assert "30 minimum" in (SKILL / "guidelines.md").read_text()
    assert "—" not in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/learning/test_skill_files.py --no-cov -q`
Expected: FAIL with `FileNotFoundError`

- [ ] **Step 3: Write the skill**

`.claude/skills/mia-train-role/SKILL.md`:

```markdown
---
name: mia-train-role
description: Build, measure and promote a multilingual intent classifier for one Mia agent role. Use when adding a new agent role, retraining a role's model, or topping up its data. Follows docs/superpowers/specs/2026-10-06-skill-models-design.md.
---

# Train a role's skill model

Argument: the role id (folder name under node/mia/agents/). Work in that role's `skill/` folder.
Each step writes files, so resume from the first step whose output is missing.

## 1. Understand the role
Read the agent's job.md and manifest.yaml, node/mia/learning/catalogue/conversation.yaml,
docs/decisions.md (D16, D18, D26, D27), docs/capabilities.md and this skill's guidelines.md.
Ask the developer only what is missing: countries, languages, main counterparts.

## 2. Plan
Use prompts/planner.md. Write role.yaml: responsibilities, counterparts with shares,
languages, countries, styles, intents (id, description, counterparts, risk, label_en of at most
20 characters, slots, handler, volume, follow_up, look_alikes), targets only where they differ
from guidelines.md. Run `uv run mia skills validate <role>` for schema errors (quota errors are
expected until data exists).

## 3. Research public data
Use prompts/public-research.md. Search dataset hubs and papers for data matching this role's
intents, counterparts' way of speaking, languages and its out-of-scope and safety neighbours.
Apply the licence rules in guidelines.md. Write public.yaml (chosen, with mapping and use;
rejected, with the reason).

## 4. Generate
Train and dev: two teacher models, `uv run mia skills generate <role> --model gateway/<teacher-1>
--split train` and again with `--model gateway/<teacher-2>`. Test: a third model family,
`--split test`. Synthetic data only. Natively per language (Finnish puhekieli, Taglish), with
`context` for follow-up intents.

## 5. Review
Use prompts/reviewer.md with a stronger model than the generators. For every record in
generated.jsonl: check label, language, naturalness, slots; set review.status (kept, fixed,
dropped) and a note. Judge completeness against role.yaml and generate what is missing (then
review it). Write reviewed.jsonl, then run `uv run mia skills split <role>` and
`uv run mia skills validate <role>` until there are no errors. Write review.md with the coverage
notes and the validator's warnings with your judgement on each.

## 6. Gate 1
Show the developer role.yaml, public.yaml, about 20 records per language from train and test,
and review.md. Stop until they approve.

## 7. Train
`uv run mia skills train <role>` (needs `uv sync --group learning`; on a cloud GPU only with
synthetic or scrubbed data, D27). For the first role, run the base-model bake-off with
`--base-model` for jhu-clsp/mmBERT-small, jhu-clsp/mmBERT-base, FacebookAI/xlm-roberta-base and
intfloat/multilingual-e5-base, and compare per-language accuracy, ECE and CPU latency.

## 8. Explain the report
Read reports/<version>.md. If the gate failed: list the weakest intent by language by style
cells and the confused pairs, generate targeted data for exactly those (back to step 4 with
`--only`), review it, and train again. Do not top up everything.

## 9. Gate 2
Show the report. Only after the developer signs off: `uv run mia skills promote <role>
<version> --signed-by "<name>"`. Add one line to docs/research/skill-sizing.md: role, version,
records per intent per language that reached the gate, base model, accuracy per language.

## Rules
- Never use the test split for tuning; regenerate it only when role.yaml changes.
- No example in the prompts repeats a test message.
- Public data goes into train and dev only.
- Real messages never go into git; they are retrained on the node (D27).
- Nothing is promoted without gate 2.
```

`.claude/skills/mia-train-role/guidelines.md`: copy spec section 6 in full (sizing table with "30 minimum, 60 target", distribution shares, public data rules with the licence list, promotion gate values, learning-as-we-go), plus a "Measured so far" section that starts empty and is filled from docs/research/skill-sizing.md.

`prompts/planner.md`: instructions to derive responsibilities, counterparts, intents and look-alikes from job.md the way a hiring manager writes a job description, using docs/capabilities.md as a reference; output YAML matching `RoleSpec`.

`prompts/generator.md`: write realistic chat and WhatsApp messages for the given cell; native in the language (not translated); varied length, typos for `typo`, indirect phrasing for `indirect`, one or two words for `terse`; for follow-up intents fill `context` with Mia's previous question; never include real names of people (use common first names), never copy example sentences; return JSON matching `list[GeneratedMessage]`.

`prompts/reviewer.md`: per record decide kept, fixed or dropped with a short note; check intent label against role.yaml descriptions and look-alikes, language and naturalness, slots; then list missing situations, counterparts and phrasings per intent.

`prompts/public-research.md`: search and evaluate public datasets for the role; record licence, size, languages, mapping and quality; apply the licence rules; prefer data written by people over machine-translated data for style.

Also create `docs/research/skill-sizing.md` with a header and an empty table (`| Role | Version | Train per intent per language | Base model | en | fi | fil |`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest node/tests/learning/test_skill_files.py --no-cov -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/mia-train-role docs/research/skill-sizing.md node/tests/learning/test_skill_files.py
git commit -m "Claude Code skill /mia-train-role with guidelines and prompts"
```

---

### Task 18: Docs and spec alignment

**Files:**
- Modify: `docs/superpowers/specs/2026-10-06-skill-models-design.md` (section 7: "high, intent with a tool handler" now reads "the agent runs with the intent as context; direct slot-to-argument mapping is a later improvement"; section 8 step 2: candidates are stored in MIA_LEARNING_DIR on the node, not in a database table, so no data standard change)
- Modify: `docs/decisions.md` (D26 note: understanding uses the multilingual encoder; translation only for free-text replies, pending the bake-off)
- Modify: `README.md` (a "Role skill models" section with the commands)
- Test: run `uv run mia skills validate dispatcher` (expect quota errors only, since no data exists yet; the seed role.yaml comes from Task 10) and the full suite.

- [ ] **Step 1: Make the edits above.** README section:

```markdown
## Role skill models

Each agent role can have its own multilingual intent classifier (docs/superpowers/specs/2026-10-06-skill-models-design.md).
In Claude Code run `/mia-train-role <role>`; it plans the role, researches public data, generates and reviews
messages, then runs:

    uv run mia skills validate <role>    # data checks
    uv run mia skills split <role>       # train and dev from reviewed.jsonl
    uv sync --group learning && uv run mia skills train <role>   # train, calibrate, evaluate, package
    uv run mia skills promote <role> <version> --signed-by "Name"
    uv run mia skills harvest <role>     # on the node: clarification choices to candidates
```

- [ ] **Step 2: Run the checks**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy node/mia && uv run pytest && uv run pytest node/tests/evals -m evals --no-cov -q`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add docs README.md
git commit -m "Docs: role skill models; spec aligned with the build; dispatcher role plan seed"
```

---

### Task 19: First role (operational, after merge)

Not code: run `/mia-train-role dispatcher` end to end with the developer, including the base-model bake-off, and record the result in docs/research/skill-sizing.md and the decisions log (default base model; D26 confirmed or changed). Prerequisites: Q18 answered and the intent catalogue branch merged; gateway access for the teacher models (OpenRouter with synthetic data only, D18 and D27).

---

## Self-review notes

- Spec coverage: sections 3 (Tasks 1, 7, 17), 4 (Task 17, commands from 12 and 16), 5 (Tasks 7, 12, 14, 15), 6 (Tasks 1, 4, 5, 6, 17), 7 (Tasks 8 to 10), 8 (Tasks 10, 11, 14 `--with-real`), 9 and 12 (Tasks 13, 18, 19), 10 (Tasks 7, 8, 12), 11 (tests in every task).
- Deliberate differences from the spec, recorded in Task 18: high-band tool intents run the agent with the intent (not direct argument mapping) in this version; harvested candidates are files on the node, not a table, avoiding a data standard change.
- Types used across tasks: `Classification`, `Alternative`, `Route`, `ModelCard`, `EvalReport`, `IntentScore`, `GateResult`, `Record`, `RoleSpec`, `IntentSpec`, `Targets`, `Prediction` are defined once (Tasks 1, 4, 5, 7, 8, 9) and used with the same field names.
