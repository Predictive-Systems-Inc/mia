"""Organisation settings, read from config/org/<org>/settings.yaml (configs ship as files in
Phase 1; Mia Cloud distributes them later). Missing files or keys fall back to the defaults."""

import datetime as dt
from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from mia.i18n import SUPPORTED
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


class ChannelConfig(BaseModel):
    """Per-organisation switch for one messaging channel (off unless enabled)."""

    enabled: bool = False


class AlertSettings(BaseModel):
    """When the ticker's alerts fire (local times)."""

    check_in_grace_minutes: int = 15
    check_out_grace_minutes: int = 30
    overtime_minutes: int = 30  # past the planned end before the supervisors hear
    unstaffed_check_time: dt.time = dt.time(15, 0)
    daily_plan_time: dt.time = dt.time(17, 0)


class OrgSettings(BaseModel):
    # Which demo seed and industry tables the organisation uses.
    template: Literal["cleaning", "retail"] = "cleaning"
    quiet_hours: QuietHours = Field(default_factory=QuietHours)
    alerts: AlertSettings = Field(default_factory=AlertSettings)
    cover_confirmation: CoverConfirmation = Field(default_factory=CoverConfirmation)
    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    # Offered in the language question; fewer than two: nobody is asked.
    languages: list[str] = Field(default_factory=list)
    # The agents this organisation runs, in routing order.
    agents: list[str] = Field(default_factory=lambda: ["shift_supervisor"])

    @field_validator("languages")
    @classmethod
    def _supported(cls, value: list[str]) -> list[str]:
        """Every offered language is one Mia speaks (i18n.SUPPORTED)."""
        bad = [code for code in value if code not in SUPPORTED]
        if bad:
            raise ValueError(f"unsupported language code(s) {bad}; supported: {list(SUPPORTED)}")
        return value


@lru_cache
def load(org: str | None = None) -> OrgSettings:
    """Settings for an organisation (default settings.MIA_ORG)."""
    settings = get_settings()
    path = settings.config_dir / "org" / (org or settings.MIA_ORG) / "settings.yaml"
    if not path.exists():
        return OrgSettings()
    return OrgSettings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
