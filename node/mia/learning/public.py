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
    """Determine licence approval status.

    A licence is "never" allowed if it contains non-commercial restrictions or is unknown/empty.
    A licence is "allowed" if it is in the pre-approved list.
    Otherwise, it "needs_approval" (e.g. share-alike, custom terms, training restrictions).
    """
    key = licence.strip().lower()
    if not key or "nc" in key.replace("-", " ").split() or key == "unknown":
        return "never"
    if key in ALLOWED:
        return "allowed"
    return "needs_approval"  # share-alike, custom terms, training restrictions


def load_public(path: Path) -> PublicSpec:
    """Load public dataset spec from YAML file.

    Raises ValueError if any dataset has a "never" licence or a "needs_approval"
    licence without approval.
    """
    spec = PublicSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    for d in spec.datasets:
        verdict = licence_verdict(d.licence)
        if verdict == "never":
            raise ValueError(f"{d.name}: licence {d.licence} is never allowed")
        if verdict == "needs_approval" and not d.approved_by:
            raise ValueError(f"{d.name}: licence {d.licence} needs approval (approved_by)")
    return spec
