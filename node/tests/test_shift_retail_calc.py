"""The retail shift supervisor's pure code (roster.py) and the cover candidates across the
organisation (scheduling.candidate_data, D39): negative tests first."""

import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.agents.shift_supervisor import roster, scoring
from mia.core import scheduling, store
from mia.core.models import Actor, Branch, Job, Organisation, Person, Visit
from mia.core.people import add_person
from tests.conftest import RS_TODAY

Ferinos = tuple[Branch, dict[str, Person]]
NINE, FIVE_PM, NINE_PM = dt.time(9), dt.time(17), dt.time(21)
TU_SU = "TU,WE,TH,FR,SA,SU"
WEEK = TU_SU.split(",")
MONDAY = dt.date(2026, 11, 2)  # the week after RS_TODAY's
TUESDAY, SATURDAY = MONDAY + dt.timedelta(days=1), MONDAY + dt.timedelta(days=5)
PATTERN = (
    "Ana opening Martes hanggang Linggo 9 to 5, Liza closing 1 to 9, "
    "Sabado at Linggo dagdag si Liza 9 to 1 sa umaga"
)


def at(day: dt.date, hour: int) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour), ZoneInfo("Asia/Manila"))


def visit_of(session: Session, person: Person, day: dt.date) -> Visit:
    return next(
        v
        for v in session.exec(select(Visit).where(Visit.date == day))
        if person.id in v.assigned_person_ids
    )


def test_cover_never_reaches_another_organisation(session: Session, rs: Ferinos) -> None:
    org = store.insert(
        session,
        Organisation(name="Other", country="PH", default_language="fil"),
        Actor.system(rs[0].id),
    )
    other = store.insert(
        session,
        Branch(organisation_id=org.id, name="Other kiosk", timezone="Asia/Manila"),
        Actor.system(rs[0].id),
    )
    add_person(
        session,
        Actor.system(other.id),
        branch_id=other.id,
        name="Mila",
        roles=["clerk"],
        language="fil",
    )
    visit = visit_of(session, rs[1]["Ana"], TUESDAY)
    names = {c.name for c in scheduling.candidate_data(session, rs[0], visit, org_wide=True)}
    # Berto is the commissary's driver (same organisation, staff); without availability windows
    # scoring never finds him free for a kiosk shift
    assert names == {"Liza", "Pao", "Berto"}


def test_cover_stays_in_the_branch_by_default(session: Session, rs: Ferinos) -> None:
    visit = visit_of(session, rs[1]["Ana"], TUESDAY)
    assert [c.name for c in scheduling.candidate_data(session, rs[0], visit)] == ["Liza"]


def test_approved_leave_makes_a_clerk_absent(session: Session, rs: Ferinos) -> None:
    day = RS_TODAY - dt.timedelta(days=9)  # Liza's seeded vacation
    job = session.exec(select(Job).where(Job.name == "Closing Liza")).one()
    ghost = Visit(
        branch_id=rs[0].id,
        job_id=job.id,
        location_id=job.location_id,
        date=day,
        planned_start=at(day, 13),
        planned_end=at(day, 21),
    )
    data = scheduling.candidate_data(session, rs[0], ghost, only={rs[1]["Liza"].id})
    assert day in data[0].absent_dates


def test_cover_candidates_carry_their_other_kiosk_bookings(session: Session, rs: Ferinos) -> None:
    visit = visit_of(session, rs[1]["Ana"], TUESDAY)
    data = scheduling.candidate_data(session, rs[0], visit, org_wide=True)
    pao = next(c for c in data if c.name == "Pao")
    slot = scheduling.slot_of(session, visit, "Asia/Manila")
    assert (len(pao.booked), scoring.ineligibility(pao, slot)) == (
        6,
        ["outside availability", "over the weekly hour limit"],
    )


def test_shift_ranges_read_the_branch_hours() -> None:
    r = lambda text: [(x.start, x.end) for _, x in roster.find_ranges(text, NINE, NINE_PM)]
    assert (r("9 to 5"), r("1 to 9"), r("1-9pm"), r("9 to 1 sa umaga"), r("3 classic")) == (
        [(NINE, FIVE_PM)],
        [(dt.time(13), NINE_PM)],
        [(dt.time(13), NINE_PM)],
        [(NINE, dt.time(13))],
        [],
    )
    assert r("9am-5pm") == r("9 hanggang 5") == r("alas 9 hanggang alas 5") == [(NINE, FIVE_PM)]
    assert [i for i, _ in roster.find_ranges("9 to 1, 1 to 9", NINE, NINE_PM)] == ["r0", "r1"]


def test_a_negated_day_is_a_correction() -> None:
    d = roster.find_days("hindi Sabado, Linggo")
    assert (d.byday, d.corrected) == (["SU"], True)


def test_weekday_ranges_and_lists_become_byday() -> None:
    assert roster.find_days("Martes hanggang Linggo").byday == WEEK
    assert roster.find_days("Sabado at Linggo") == roster.Days(["SA", "SU"], False)
    assert roster.find_days("Biyernes hangtod Lunes").byday == ["MO", "FR", "SA", "SU"]


def test_tubtob_and_sagkod_read_as_hanggang() -> None:
    """hil and war "tubtob", bcl "sagkod": the same range and days as "hanggang"."""
    r = lambda text: [(x.start, x.end) for _, x in roster.find_ranges(text, NINE, NINE_PM)]
    assert r("9 tubtob 5") == r("alas 9 sagkod alas 5") == r("9 hanggang 5") == [(NINE, FIVE_PM)]
    tu_su = roster.find_days("Martes hanggang Domingo").byday
    assert roster.find_days("Martes tubtob Domingo").byday == tu_su == WEEK
    assert roster.find_days("Martes sagkod Domingo").byday == WEEK


def test_the_owners_pattern_parses_clause_by_clause() -> None:
    p = roster.parse_pattern(PATTERN, {"a": "Ana", "l": "Liza"}, NINE, NINE_PM)
    assert [(c.person_id, c.byday, c.start, c.end) for c in p.clauses] == [
        ("a", WEEK, NINE, FIVE_PM),
        ("l", WEEK, dt.time(13), NINE_PM),
        ("l", ["SA", "SU"], NINE, dt.time(13)),
    ]
    assert p.unclear == []
    assert roster.parse_pattern("si Ana sa umaga", {"a": "Ana"}, NINE, NINE_PM).unclear == [
        "si Ana sa umaga"
    ]


def test_a_split_shift_is_two_clauses() -> None:
    p = roster.parse_pattern("Ana Sabado 9 to 1 at 5 to 9", {"a": "Ana"}, NINE, NINE_PM)
    assert [(c.start, c.end) for c in p.clauses] == [(NINE, dt.time(13)), (FIVE_PM, NINE_PM)]


def test_the_roster_week_is_the_manila_week() -> None:
    assert roster.week_of(dt.datetime(2026, 11, 1, 23, 30, tzinfo=dt.UTC), "Asia/Manila") == MONDAY


def test_a_swap_checks_both_clerks_in_the_others_slot() -> None:
    early, late = (
        scoring.Slot(at(SATURDAY, 9), at(SATURDAY, 17)),
        scoring.Slot(at(SATURDAY, 13), at(SATURDAY, 21)),
    )
    a = scoring.CandidateData("a", "Ana", [], {5: (NINE, NINE_PM)}, 600, 3240, booked=[early])
    b = scoring.CandidateData(
        "l", "Liza", [], {5: (dt.time(13), NINE_PM)}, 600, 3240, booked=[late]
    )
    assert roster.swap_breaks(a, early, b, late) == ["Liza: outside availability"]


def test_job_names_follow_the_hours() -> None:
    assert roster.job_name(NINE, FIVE_PM, WEEK, NINE, NINE_PM, "Ana") == "Opening Ana"
    assert (
        roster.job_name(NINE, dt.time(13), ["SA", "SU"], NINE, NINE_PM, "Liza")
        == "Weekend opening Liza"
    )
    assert roster.job_name(dt.time(11), dt.time(19), WEEK, NINE, NINE_PM, "Pao") == "Mid Pao"
    assert roster.rrule(["SU", "SA"]) == "FREQ=WEEKLY;BYDAY=SA,SU"


def test_outside_hours_names_the_days_the_clause_leaves() -> None:
    from mia.templates.retail.models import RetailBranchHours

    hours = [
        RetailBranchHours(branch_id="b", weekday=d, opens="09:00", closes="21:00")
        for d in range(1, 7)
    ]
    clause = roster.Clause("a", ["MO", "TU", "WE"], NINE, FIVE_PM)
    assert roster.outside_hours(clause, hours) == ["MO"]
    assert roster.outside_hours(roster.Clause("a", ["TU"], dt.time(8), FIVE_PM), hours) == ["TU"]


def test_reason_keys_cover_every_scoring_reason() -> None:
    slot = scoring.Slot(at(SATURDAY, 9), at(SATURDAY, 17))
    c = scoring.CandidateData("a", "Ana", [], {}, 0, 0, booked=[slot], absent_dates={SATURDAY})
    assert sorted(roster.REASON_KEYS) == sorted(scoring.ineligibility(c, slot))


def test_a_negated_day_is_removed_from_a_range() -> None:
    d = roster.find_days("Martes hanggang Linggo hindi Sabado")
    assert (d.byday, d.corrected) == (["TU", "WE", "TH", "FR", "SU"], True)


def test_a_week_phrase_is_not_a_sunday() -> None:
    assert roster.find_days("sa susunod na linggo Lunes at Martes").byday == ["MO", "TU"]
    assert roster.find_days("ngayong linggo Sabado").byday == ["SA"]


def test_a_comma_between_days_keeps_one_clause() -> None:
    p = roster.parse_pattern("Ana Lunes, Martes at Miyerkules 9 to 5", {"a": "Ana"}, NINE, NINE_PM)
    assert ([(c.byday, c.start, c.end) for c in p.clauses], p.unclear) == (
        [(["MO", "TU", "WE"], NINE, FIVE_PM)],
        [],
    )


def test_an_unclear_clause_passes_no_days_on() -> None:
    p = roster.parse_pattern("si Pedro Sabado 9 to 5, Ana 1 to 9", {"a": "Ana"}, NINE, NINE_PM)
    assert (p.clauses, p.unclear) == ([], ["si Pedro Sabado 9 to 5", "Ana 1 to 9"])
