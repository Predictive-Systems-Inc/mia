"""Organisation settings, read from config/org/<org>/settings.yaml (configs ship as files in
Phase 1; Mia Cloud distributes them later). Missing files or keys fall back to the defaults."""

import datetime as dt
from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

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


class Holiday(BaseModel):
    """One Philippine holiday: regular (double pay) or special non-working day."""

    date: dt.date
    kind: Literal["regular", "special"]
    name: str


class Payroll(BaseModel):
    """Payroll cycle: cutoffs and how many days after a cutoff the pay date falls."""

    cutoffs: Literal["semi_monthly"] = "semi_monthly"
    pay_lag_days: int = 5


class DeliveryArea(BaseModel):
    """One area the shop delivers to, matched by name; fee in minor units."""

    name: str
    fee: int
    currency: str


class CustomerServiceSettings(BaseModel):
    """Limits for the customer service: items per order, inbound messages per hour per address,
    and public turns (each one Jev request) per hour across the whole node; menu_words are the
    org's generic words for every item ("bibingka" at Ferino's)."""

    max_order_quantity: int = 50
    messages_per_hour: int = 30
    public_calls_per_hour: int = 600
    menu_words: list[str] = Field(default_factory=list)  # a price question on one asks the menu


class BranchManagerSettings(BaseModel):
    """The branch manager's limits: an experiment's length in days, and how many missed day
    targets in a row earn a clerk one kind nudge."""

    experiment_days: int = 14
    nudge_after_misses: int = 3


class BookkeeperSettings(BaseModel):
    """The bookkeeper's limits, money in minor units and percents as integers: one threshold
    for the cash count, settlements and payouts (flagged only when the gap is over it), the
    expense limit (over it waits for the owner), the e-wallet fees and platform commissions
    (placeholders the owner corrects), the tax regime, the petty cash floor and the
    undeposited cash limit (Q90)."""

    threshold: int = 10_000
    expense_limit: int = 500_000
    fees: dict[str, int] = Field(default_factory=lambda: {"gcash": 2, "maya": 2})
    commissions: dict[str, int] = Field(default_factory=lambda: {"grab": 25, "foodpanda": 28})
    tax_regime: Literal["vat", "percentage"] = "vat"
    petty_floor: int = 50_000
    undeposited_limit: int = 2_000_000


class ProductionHours(BaseModel):
    """The commissary's production window (local times): the ovens run from start to end."""

    start: dt.time = dt.time(3, 0)
    end: dt.time = dt.time(9, 0)


class ProductionPlannerSettings(BaseModel):
    """The production planner's commissary: the branch by name (empty: the agent does nothing),
    the kiosks it bakes for by name, the number of ovens, the production window, when the draft
    plan goes to the head (the day before) and when the dispatch list goes out at the latest."""

    commissary: str = ""
    serves: list[str] = Field(default_factory=list)
    ovens: int = 2
    hours: ProductionHours = Field(default_factory=ProductionHours)
    plan_at: dt.time = dt.time(14, 0)
    dispatch_at: dt.time = dt.time(8, 30)


class ShiftSupervisorSettings(BaseModel):
    """When the shift supervisor sends the next week's roster (retail, Q110): the local weekday
    (0 is Monday) and time; the roster covers the Monday to Sunday that follows."""

    weekly_roster_weekday: int = Field(6, ge=0, le=6)
    weekly_roster_time: dt.time = dt.time(17, 0)


class SalesSettings(BaseModel):
    """Where a kiosk's day of sales comes from (D43, ADR 022): receipts_from maps a branch name
    to its first receipts day (a local date). Before it, or for a branch not named, the day's
    sales are the clerks' counts; from it, the till's receipts. One source per day, never both."""

    receipts_from: dict[str, dt.date] = Field(default_factory=dict)
    # Branch name to the change fund at a session's opening, minor units; 0 when absent.
    opening_float: dict[str, int] = Field(default_factory=dict)

    def source(self, branch_name: str, day: dt.date) -> Literal["counts", "receipts"]:
        """counts or receipts for the branch's business date (counts unless named and due)."""
        start = self.receipts_from.get(branch_name)
        return "receipts" if start is not None and day >= start else "counts"


class OrgSettings(BaseModel):
    # Which demo seed and industry tables the organisation uses.
    template: Literal["cleaning", "retail"] = "cleaning"
    quiet_hours: QuietHours = Field(default_factory=QuietHours)
    alerts: AlertSettings = Field(default_factory=AlertSettings)
    cover_confirmation: CoverConfirmation = Field(default_factory=CoverConfirmation)
    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    # Offered in the language question; fewer than two: nobody is asked.
    languages: list[str] = Field(default_factory=list)
    holidays: list[Holiday] = Field(default_factory=list)
    payroll: Payroll = Field(default_factory=Payroll)
    delivery_areas: list[DeliveryArea] = Field(default_factory=list)
    customer_service: CustomerServiceSettings = Field(default_factory=CustomerServiceSettings)
    branch_manager: BranchManagerSettings = Field(default_factory=BranchManagerSettings)
    bookkeeper: BookkeeperSettings = Field(default_factory=BookkeeperSettings)
    production_planner: ProductionPlannerSettings = Field(default_factory=ProductionPlannerSettings)
    shift_supervisor: ShiftSupervisorSettings = Field(default_factory=ShiftSupervisorSettings)
    sales: SalesSettings = Field(default_factory=SalesSettings)
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

    @model_validator(mode="after")
    def _one_currency(self) -> "OrgSettings":
        """The delivery areas share one currency (an order totals items and fee in one)."""
        if len({a.currency for a in self.delivery_areas}) > 1:
            raise ValueError("delivery_areas must all use one currency")
        return self


@lru_cache
def load(org: str | None = None) -> OrgSettings:
    """Settings for an organisation (default settings.MIA_ORG)."""
    settings = get_settings()
    path = settings.config_dir / "org" / (org or settings.MIA_ORG) / "settings.yaml"
    if not path.exists():
        return OrgSettings()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    extra = path.with_name("holidays.yaml")  # holidays live next to settings.yaml when present
    if extra.exists():
        listed = yaml.safe_load(extra.read_text(encoding="utf-8")) or []
        data["holidays"] = [*data.get("holidays", []), *listed]
    return OrgSettings.model_validate(data)
