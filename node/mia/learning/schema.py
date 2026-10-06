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
    embedding_model: str = "intfloat/multilingual-e5-small"

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
