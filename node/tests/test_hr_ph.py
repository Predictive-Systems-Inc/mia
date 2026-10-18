import datetime as dt
from zoneinfo import ZoneInfo

from mia.agents.hr_officer.ph import (
    Line,
    Minutes,
    monthly_basic,
    pagibig_employee,
    payslip,
    philhealth_employee,
    split_minutes,
    sss_employee,
)

MANILA = ZoneInfo("Asia/Manila")
SUNDAY = 6
DAILY = 60_000  # 600.00 pesos a day, 75.00 an hour


def at(day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=MANILA)


def one_line(m: Minutes) -> Line:
    return payslip([m], DAILY, monthly_basic(DAILY)).lines[0]


def test_each_multiplier_on_a_worked_example() -> None:
    # One hour at 75.00: regular 75.00, overtime 93.75, night premium 7.50, rest day 97.50,
    # regular holiday 150.00, special holiday 97.50.
    assert one_line(Minutes(regular=60)) == Line("regular", 60, 100, 7_500)
    assert one_line(Minutes(overtime=60)) == Line("overtime", 60, 125, 9_375)
    assert one_line(Minutes(night=60)) == Line("night", 60, 10, 750)
    assert one_line(Minutes(rest_day=60)) == Line("rest_day", 60, 130, 9_750)
    assert one_line(Minutes(regular_holiday=60)) == Line("regular_holiday", 60, 200, 15_000)
    assert one_line(Minutes(special_holiday=60)) == Line("special_holiday", 60, 130, 9_750)
    # 90 overtime minutes: 140.625 rounds half up to 140.63.
    assert one_line(Minutes(overtime=90)).amount == 14_063


def test_contribution_tables_at_their_brackets() -> None:
    assert sss_employee(0) == 25_000  # the floor: credit 5,000
    assert sss_employee(524_999) == 25_000
    assert sss_employee(525_000) == 27_500  # 5,250 starts the 5,500 credit
    assert sss_employee(1_560_000) == 77_500  # 15,600 is in the 15,500 credit
    assert sss_employee(3_474_999) == 172_500
    assert sss_employee(3_475_000) == 175_000  # the cap: credit 35,000
    assert sss_employee(9_000_000) == 175_000
    assert philhealth_employee(500_000) == 25_000  # floor 10,000
    assert philhealth_employee(1_560_000) == 39_000
    assert philhealth_employee(12_000_000) == 250_000  # ceiling 100,000
    assert pagibig_employee(150_000) == 1_500  # 1% up to 1,500
    assert pagibig_employee(150_001) == 3_000
    assert pagibig_employee(1_560_000) == 20_000  # 2% capped at 10,000


def test_split_an_evening_shift_into_regular_overtime_and_night() -> None:
    m = split_minutes(at(19, 14), at(19, 23, 30), MANILA, SUNDAY, {})
    assert m == Minutes(regular=480, overtime=90, night=90)


def test_split_a_shift_across_midnight() -> None:
    m = split_minutes(at(19, 21), at(20, 5), MANILA, SUNDAY, {})
    assert m == Minutes(regular=480, night=420)


def test_split_reads_local_time_from_utc() -> None:
    utc = dt.UTC
    start = dt.datetime(2026, 10, 19, 6, tzinfo=utc)  # 14:00 in Manila
    end = dt.datetime(2026, 10, 19, 15, 30, tzinfo=utc)
    assert split_minutes(start, end, MANILA, SUNDAY, {}).night == 90


def test_a_rest_day_or_holiday_shift_goes_wholly_to_its_bucket() -> None:
    sunday = split_minutes(at(18, 8), at(18, 18), MANILA, SUNDAY, {})
    assert sunday == Minutes(rest_day=600)
    holidays = {dt.date(2026, 10, 19): "regular", dt.date(2026, 10, 20): "special"}
    assert split_minutes(at(19, 8), at(19, 17), MANILA, SUNDAY, holidays) == Minutes(
        regular_holiday=540
    )
    assert split_minutes(at(20, 8), at(20, 12), MANILA, SUNDAY, holidays) == Minutes(
        special_holiday=240
    )


def test_a_full_payslip_by_hand_at_the_15500_credit() -> None:
    days = [Minutes(regular=480)] * 10 + [
        Minutes(overtime=90, night=90),
        Minutes(rest_day=480),
        Minutes(regular_holiday=480),
        Minutes(special_holiday=240),
    ]
    slip = payslip(days, DAILY, monthly_basic(DAILY))  # 15,600 a month
    assert [(line.kind, line.amount) for line in slip.lines] == [
        ("regular", 600_000),  # 80 h at 75.00
        ("overtime", 14_063),  # 1.5 h at 93.75 = 140.625
        ("night", 1_125),  # 1.5 h at 7.50
        ("rest_day", 78_000),  # 8 h at 97.50
        ("regular_holiday", 120_000),  # 8 h at 150.00
        ("special_holiday", 39_000),  # 4 h at 97.50
    ]
    assert slip.gross == 852_188
    # Half a month each: SSS 775.00 / 2, PhilHealth 390.00 / 2, Pag-IBIG 200.00 / 2.
    assert [(d.kind, d.amount) for d in slip.deductions] == [
        ("sss", 38_750),
        ("philhealth", 19_500),
        ("pagibig", 10_000),
    ]
    assert slip.net == 852_188 - 68_250


def test_a_payslip_at_the_26000_credit() -> None:
    daily = 100_000  # 1,000.00 a day, 26,000 a month
    slip = payslip([Minutes(regular=480)] * 5, daily, monthly_basic(daily))
    assert slip.gross == 500_000
    # SSS 1,300 / 2, PhilHealth 650 / 2, Pag-IBIG 200 / 2.
    assert [d.amount for d in slip.deductions] == [65_000, 32_500, 10_000]
    assert slip.net == 392_500
