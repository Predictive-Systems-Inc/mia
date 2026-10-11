"""Model packages on disk and their promotion (spec section 5)."""

import datetime as dt
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from mia.core import events
from mia.core.models import Actor
from mia.learning.gate import GateResult
from mia.learning.metrics import EvalReport
from mia.settings import get_settings

Kind = Literal["encoder", "knn", "contrastive"]
ARTIFACTS: dict[str, tuple[str, ...]] = {
    "encoder": ("model.onnx", "tokenizer.json"),
    "contrastive": ("model.onnx", "tokenizer.json"),
    "knn": ("model.onnx", "tokenizer.json", "examples.npy", "examples.json"),
}


class PromotionRefused(Exception):
    """The version cannot become active (gate failed, no sign-off, missing, or files that do
    not match the card)."""


class ModelCard(BaseModel):
    """Everything needed to load, judge and audit one built model version."""

    role: str
    version: str
    kind: Kind = "encoder"
    prefix: str = ""  # embedding input prefix (e5: "query: ")
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
    artifacts: dict[str, str] = {}  # filename -> sha256 hex of the file bytes
    with_real: bool = False  # trained with local real messages (D18): the package holds them
    signed_by: str | None = None
    signed_at: str | None = None


def _atomic_write(path: Path, text: str) -> None:
    """Write text so a reader or a crash never sees a partial file (temp file, fsync, replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=f".{path.name}."
    ) as tmp:
        try:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            Path(tmp.name).unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp.name, path)
    except BaseException:
        Path(tmp.name).unlink(missing_ok=True)
        raise


def package_dir(role: str, version: str) -> Path:
    """Directory holding one version's files."""
    return get_settings().MIA_MODELS_DIR / role / version


def verify_artifacts(card: ModelCard) -> None:
    """Returns only when every runtime file exists and matches the card's sha256; otherwise
    raises ValueError naming the first bad file."""
    folder = package_dir(card.role, card.version)
    for name in ARTIFACTS[card.kind]:
        expected = card.artifacts.get(name)
        if expected is None:
            raise ValueError(f"{name}: no sha256 in card artifacts")
        try:
            with (folder / name).open("rb") as f:
                digest = hashlib.file_digest(f, "sha256").hexdigest()
        except FileNotFoundError:
            raise ValueError(f"{name}: file is missing") from None
        except OSError as exc:  # a directory or an unreadable file is just as unusable
            raise ValueError(f"{name}: file is unreadable ({type(exc).__name__})") from None
        if digest != expected:
            raise ValueError(f"{name}: sha256 does not match card artifacts")


def write_card(card: ModelCard) -> Path:
    """Write card.json for the card's version, creating the directory."""
    path = package_dir(card.role, card.version) / "card.json"
    _atomic_write(path, card.model_dump_json(indent=2))
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

    Order: signed card first (harmless on a version that is not active), then the ACTIVE marker
    (the switch itself, atomic), then the event, so a failed write emits nothing. Files cannot
    join the DB transaction: if the later emit or commit fails, ACTIVE has changed without an
    event (known gap).
    """
    try:
        card = read_card(role, version)
    except FileNotFoundError as exc:
        raise PromotionRefused(f"{role}@{version} not found") from exc
    except ValidationError as exc:
        raise PromotionRefused(f"{role}@{version} card is unreadable: {exc}") from exc
    if not card.gate.passed:
        raise PromotionRefused(f"{role}@{version} failed the gate: {card.gate.failures}")
    if not signed_by.strip():
        raise PromotionRefused("a sign-off name is required")
    try:
        verify_artifacts(card)
    except ValueError as exc:
        raise PromotionRefused(f"{role}@{version} cannot be loaded: {exc}") from exc
    previous = active_version(role)
    signed_at = dt.datetime.now(dt.UTC).isoformat()
    card = card.model_copy(update={"signed_by": signed_by, "signed_at": signed_at})
    write_card(card)
    _atomic_write(get_settings().MIA_MODELS_DIR / role / "ACTIVE", version)
    events.emit(
        session,
        "skill_model.promoted",
        ("skill_model", f"{role}@{version}"),
        {"active": previous},
        {"active": version, "signed_by": signed_by},
        actor,
    )
    return card
