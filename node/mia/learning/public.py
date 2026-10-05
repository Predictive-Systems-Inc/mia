"""Public datasets chosen per role (spec section 6, public data rules)."""

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Verdict = Literal["allowed", "needs_approval", "never"]


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
    """Determine licence approval status with robust non-commercial detection.

    Fail closed: defaults to "never" for unrecognised licences.
    - Never: non-commercial (any spelling), empty, proprietary, unknown, n/a, etc.
    - Allowed: recognised permissive licences (CC-BY, CC0, MIT, Apache, BSD, MPL)
    - Needs approval: recognised share-alike/copyleft/custom (SA, GPL, AGPL, etc.)
    """
    key = licence.strip().lower()

    # Empty/blank
    if not key:
        return "never"

    # Tokenise: split on non-alphanumeric (keep dots for version numbers)
    tokens = re.split(r"[^a-z0-9.]+", key)
    tokens = [t for t in tokens if t]  # remove empty tokens
    compact = "".join(tokens)

    # ==================== NEVER: Non-commercial markers ====================
    nc_patterns = [
        # "nc" as a standalone token
        "nc" in tokens,
        # "nc" followed by digit: nc4.0, nc-4.0
        any(re.match(r"^nc\d", t) for t in tokens),
        # Spelled out: noncommercial, non-commercial, non commercial
        "noncommercial" in compact,
        ("non" in tokens and "commercial" in tokens),
        # by-nc in any form (underscores, hyphens, URLs, etc.)
        "bync" in compact,
        # Explicit strings that are always "never"
        key in {
            "non-commercial",
            "noncommercial",
            "(nc)",
            "proprietary",
            "other",
            "n/a",
            "none",
            "unknown",
            "unknown license",
            "unspecified",
            "tbd",
        },
    ]

    if any(nc_patterns):
        return "never"

    # ==================== ALLOWED: Permissive licences ====================
    allowed_keys = {
        "cc-by-4.0",
        "cc by 4.0",
        "cc by-4.0",
        "cc-by-3.0",
        "cc by 3.0",
        "cc by-3.0",
        "cc0-1.0",
        "cc0 1.0",
        "cc0",
        "mit",
        "apache-2.0",
        "apache 2.0",
        "apache license 2.0",
        "bsd-2-clause",
        "bsd 2-clause",
        "bsd-3-clause",
        "bsd 3-clause",
        "mpl-2.0",
    }

    if key in allowed_keys:
        return "allowed"

    # Compact form matching for variations
    allowed_compact = {
        "ccby40",
        "ccby30",
        "cc010",
        "cc0",
        "mit",
        "apache20",
        "bsd2clause",
        "bsd3clause",
        "mpl20",
    }
    if compact in allowed_compact:
        return "allowed"

    # ==================== NEEDS_APPROVAL: Share-alike/copyleft/custom ====================
    needs_approval_patterns = [
        # Share-alike: cc-by-sa-*
        "sa" in tokens,
        # GPL variants
        "gpl" in tokens,
        "agpl" in tokens,
        "lgpl" in tokens,
        # Other copyleft
        "odbl" in tokens,
        ("cdla" in tokens and "sharing" in tokens),
        # Custom
        "custom" in tokens,
    ]

    if any(needs_approval_patterns):
        return "needs_approval"

    # ==================== NEVER: Everything else (fail closed) ====================
    return "never"


def load_public(path: Path) -> PublicSpec:
    """Load public dataset spec from YAML file.

    Raises ValueError if any dataset has a "never" licence or a "needs_approval"
    licence without approval. Blank/whitespace approved_by is treated as missing.
    """
    spec = PublicSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    for d in spec.datasets:
        # Treat blank/whitespace approved_by as missing
        approved_by = d.approved_by.strip() if d.approved_by else None

        verdict = licence_verdict(d.licence)
        if verdict == "never":
            raise ValueError(f"{d.name}: licence {d.licence} is never allowed")
        if verdict == "needs_approval" and not approved_by:
            raise ValueError(f"{d.name}: licence {d.licence} needs approval (approved_by)")
    return spec
