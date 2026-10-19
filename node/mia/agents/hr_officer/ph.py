"""The Philippine pay rules as pure code (rule 7): employee contributions, the premium
multipliers, the split of a shift into pay kinds and the payslip arithmetic.

The contribution tables are dated constants (TABLES_AS_OF) written from memory of the 2026
schedules; verify every bracket with the accountant before a real payslip is issued (Q61). The
mechanism (brackets, floors, caps, rounding) is what the tests prove, not the figures. Money is
integer minor units (PHP centavos); rates are integer percents, never floats.
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from fractions import Fraction

TABLES_AS_OF = "2026-01"

# SSS: 5% employee share of the monthly salary credit (MSC), MSC 5,000 to 35,000 pesos in
# 500-peso steps; each MSC covers pay from 250 below it to 250 below the next.
SSS_RATE_PERCENT = 5
SSS_MSC_MIN = 500_000
SSS_MSC_MAX = 3_500_000
SSS_MSC_STEP = 50_000
# PhilHealth: 5% premium on pay floored at 10,000 and capped at 100,000 pesos, half the
# employee's (2.5%).
PHILHEALTH_PERMILLE_EMPLOYEE = 25
PHILHEALTH_FLOOR = 1_000_000
PHILHEALTH_CEILING = 10_000_000
# Pag-IBIG: 1% up to 1,500 pesos a month, else 2%, on pay capped at 10,000 pesos (so 200 max).
PAGIBIG_LOW_PAY = 150_000
PAGIBIG_CAP = 1_000_000

# Premiums as fractions of the hourly rate. NIGHT is the night differential added on top.
# ponytail: night is 10% of the base hourly rate even on overtime, rest day or holiday
# minutes (the law takes 10% of that hour's own rate); split it per kind when a contract needs.
OVERTIME = Fraction(125, 100)
NIGHT = Fraction(10, 100)
REST_DAY = Fraction(130, 100)
REGULAR_HOLIDAY = Fraction(200, 100)
SPECIAL_HOLIDAY = Fraction(130, 100)
RATES: dict[str, Fraction] = {
    "regular": Fraction(1),
    "overtime": OVERTIME,
    "night": NIGHT,
    "rest_day": REST_DAY,
    "regular_holiday": REGULAR_HOLIDAY,
    "special_holiday": SPECIAL_HOLIDAY,
}
REGULAR_MINUTES = 480  # eight hours a day
# Payslip lines for days paid though not worked, at 100% of the daily rate.
PAID_LEAVE = "paid_leave"  # approved vacation or sick (service incentive) leave days
UNWORKED_HOLIDAY = "unworked_holiday"  # a regular holiday not worked (calendar rule)
BASIC_KINDS = ("regular", PAID_LEAVE)  # the lines the 13th month counts as basic pay
NIGHT_START = dt.time(22)
NIGHT_END = dt.time(6)
# The monthly basic the tables read for a daily-paid worker: daily rate times 26 (the usual
# divisor for six working days a week; verify with the accountant, Q61).
MONTHLY_DIVISOR = 26


def _half_up(value: Fraction) -> int:
    """The nearest integer, a half rounded up (values here are never negative)."""
    return int((value * 2 + 1) // 2)


def monthly_basic(daily_rate: int) -> int:
    """The monthly basic for the contribution tables: daily rate times MONTHLY_DIVISOR."""
    return daily_rate * MONTHLY_DIVISOR


def sss_employee(monthly_basic: int) -> int:
    """The employee's monthly SSS share in centavos: 5% of the salary credit bracket the pay
    falls in, between the floor and the cap."""
    above = monthly_basic - (SSS_MSC_MIN + SSS_MSC_STEP // 2)  # 5,250 pesos starts 5,500
    steps = above // SSS_MSC_STEP + 1 if above >= 0 else 0
    msc = min(SSS_MSC_MAX, SSS_MSC_MIN + steps * SSS_MSC_STEP)
    return msc * SSS_RATE_PERCENT // 100


def philhealth_employee(monthly_basic: int) -> int:
    """The employee's monthly PhilHealth share in centavos: 2.5% of the pay between the floor
    and the ceiling, rounded half up."""
    base = min(max(monthly_basic, PHILHEALTH_FLOOR), PHILHEALTH_CEILING)
    return _half_up(Fraction(base * PHILHEALTH_PERMILLE_EMPLOYEE, 1000))


def pagibig_employee(monthly_basic: int) -> int:
    """The employee's monthly Pag-IBIG share in centavos: 1% of a pay up to 1,500 pesos, else
    2% of the pay capped at 10,000 pesos, rounded half up."""
    percent = 1 if monthly_basic <= PAGIBIG_LOW_PAY else 2
    return _half_up(Fraction(min(monthly_basic, PAGIBIG_CAP) * percent, 100))


@dataclass(frozen=True)
class Minutes:
    regular: int = 0
    overtime: int = 0
    night: int = 0
    rest_day: int = 0
    regular_holiday: int = 0
    special_holiday: int = 0


def _night_minutes(start: dt.datetime, end: dt.datetime) -> int:
    """The minutes of start to end (local, same zone) inside 22:00 to 06:00 windows."""
    total = 0
    day = start.date() - dt.timedelta(days=1)
    while day <= end.date():
        window_start = dt.datetime.combine(day, NIGHT_START, start.tzinfo)
        window_end = dt.datetime.combine(day + dt.timedelta(days=1), NIGHT_END, start.tzinfo)
        overlap = min(end, window_end) - max(start, window_start)
        total += max(0, int(overlap.total_seconds()) // 60)
        day += dt.timedelta(days=1)
    return total


def split_minutes(
    start: dt.datetime,
    end: dt.datetime,
    tz: dt.tzinfo,
    rest_day: int,
    holidays: Mapping[dt.date, str],
) -> Minutes:
    """A shift's minutes by pay kind, by its local start day. A shift on a holiday goes wholly
    to regular_holiday or special_holiday, else on the rest day wholly to rest_day, else the
    first 480 minutes are regular and the rest overtime. Night (22:00 to 06:00 local, across
    midnight) is counted alongside."""
    start, end = start.astimezone(tz), end.astimezone(tz)
    worked = max(0, int((end - start).total_seconds()) // 60)
    night = _night_minutes(start, end)
    # ponytail: a holiday on the rest day pays as the holiday only (the law adds 30%), and
    # overtime on a rest day or holiday is not split out; add both when a contract needs it.
    kind = holidays.get(start.date())
    if kind == "regular":
        return Minutes(regular_holiday=worked, night=night)
    if kind == "special":
        return Minutes(special_holiday=worked, night=night)
    if start.weekday() == rest_day:
        return Minutes(rest_day=worked, night=night)
    regular = min(worked, REGULAR_MINUTES)
    return Minutes(regular=regular, overtime=worked - regular, night=night)


@dataclass(frozen=True)
class Line:
    kind: str
    minutes: int
    rate_percent: int
    amount: int


@dataclass(frozen=True)
class PayslipCalc:
    lines: list[Line]
    gross: int
    deductions: list[Line]
    net: int


def payslip(
    minutes_by_day: Sequence[Minutes],
    daily_rate: int,
    monthly_basic: int,
    *,
    leave_days: int = 0,
    holidays: int = 0,
) -> PayslipCalc:
    """One cutoff's payslip: a line per pay kind worked (its minutes summed over the days, at
    hourly rate = daily_rate / 8 times the kind's rate, rounded half up to the centavo), a
    paid_leave line (leave_days at the daily rate) and an unworked_holiday line (holidays,
    unworked regular holidays, at 100% of the daily rate) when there are any, the gross, half
    of each monthly contribution for the semi-monthly cutoff (rounded half up, Q61) taken in
    order while the gross lasts, and the net (gross less deductions, never below zero).
    Integer arithmetic only."""
    lines = []
    for f in fields(Minutes):
        minutes = sum(getattr(day, f.name) for day in minutes_by_day)
        if minutes:
            rate = RATES[f.name]
            amount = _half_up(Fraction(daily_rate * minutes, 8 * 60) * rate)
            lines.append(Line(f.name, minutes, int(rate * 100), amount))
    for kind, days in ((PAID_LEAVE, leave_days), (UNWORKED_HOLIDAY, holidays)):
        if days:
            lines.append(Line(kind, days * REGULAR_MINUTES, 100, days * daily_rate))
    gross = sum(line.amount for line in lines)
    monthly = {
        "sss": sss_employee(monthly_basic),
        "philhealth": philhealth_employee(monthly_basic),
        "pagibig": pagibig_employee(monthly_basic),
    }
    # ponytail: half a month's contribution per cutoff; some employers take it all on one.
    # Contributions read daily_rate x 26, whatever was worked, so a short cutoff caps them at
    # the gross; the fuller rule reads the month's actual earnings (Q65).
    deductions, left = [], gross
    for kind, monthly_share in monthly.items():
        amount = min(left, _half_up(Fraction(monthly_share, 2)))
        deductions.append(Line(kind, 0, 0, amount))
        left -= amount
    return PayslipCalc(lines, gross, deductions, left)
