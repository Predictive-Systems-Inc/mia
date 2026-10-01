"""Organisation settings, read from config/org/<org>/settings.yaml (configs ship as files in
Phase 1; Mia Cloud distributes them later). Missing files or keys fall back to the defaults."""

import datetime as dt
from functools import lru_cache

import yaml
from pydantic import BaseModel, Field

from mia.settings import get_settings


class QuietHours(BaseModel):
    start: dt.time = dt.time(21, 0)
    end: dt.time = dt.time(6, 0)

    def contains(self, local: dt.time) -> bool:
        """True when a local wall clock time falls inside quiet hours (which may wrap midnight)."""
        if self.start <= self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end


class CoverConfirmation(BaseModel):
    message_wait_minutes: int = 15
    call_wait_minutes: int = 10
    soon_window_minutes: int = 60
    soon_call_wait_minutes: int = 5
    urgent_until: dt.time = dt.time(10, 0)


class OrgSettings(BaseModel):
    quiet_hours: QuietHours = Field(default_factory=QuietHours)
    cover_confirmation: CoverConfirmation = Field(default_factory=CoverConfirmation)


@lru_cache
def load(org: str | None = None) -> OrgSettings:
    """Settings for an organisation (default settings.MIA_ORG)."""
    settings = get_settings()
    path = settings.config_dir / "org" / (org or settings.MIA_ORG) / "settings.yaml"
    if not path.exists():
        return OrgSettings()
    return OrgSettings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
