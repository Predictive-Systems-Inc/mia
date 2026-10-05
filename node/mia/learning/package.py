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
    """Everything needed to load, judge and audit one built model version."""

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
    """Directory holding one version's files."""
    return get_settings().MIA_MODELS_DIR / role / version


def write_card(card: ModelCard) -> Path:
    """Write card.json for the card's version, creating the directory."""
    path = package_dir(card.role, card.version) / "card.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_card(role: str, version: str) -> ModelCard:
    """Read card.json; raises FileNotFoundError if absent, ValidationError if corrupt."""
    path = package_dir(role, version) / "card.json"
    return ModelCard.model_validate_json(path.read_text("utf-8"))


def active_version(role: str) -> str | None:
    """The promoted version, or None when no ACTIVE marker exists or it is empty."""
    marker = get_settings().MIA_MODELS_DIR / role / "ACTIVE"
    return (marker.read_text("utf-8").strip() or None) if marker.exists() else None


def promote(session: Session, actor: Actor, role: str, version: str, signed_by: str) -> ModelCard:
    """Mark a signed, gate-passing version active; the previous one stays on disk for rollback.

    Files are written first and the event is emitted last, so a failed write emits nothing.
    """
    try:
        card = read_card(role, version)
    except FileNotFoundError as exc:
        raise PromotionRefused(f"{role}@{version} not found") from exc
    if not card.gate.passed:
        raise PromotionRefused(f"{role}@{version} failed the gate: {card.gate.failures}")
    if not signed_by.strip():
        raise PromotionRefused("a sign-off name is required")
    previous = active_version(role)
    signed_at = dt.datetime.now(dt.UTC).isoformat()
    card = card.model_copy(update={"signed_by": signed_by, "signed_at": signed_at})
    write_card(card)
    (get_settings().MIA_MODELS_DIR / role / "ACTIVE").write_text(version, encoding="utf-8")
    events.emit(
        session,
        "skill_model.promoted",
        ("skill_model", f"{role}@{version}"),
        {"active": previous},
        {"active": version, "signed_by": signed_by},
        actor,
    )
    return card
