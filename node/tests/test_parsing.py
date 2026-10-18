import datetime as dt

from mia.agents.parsing import (
    find_dates,
    find_times,
    has_buy_word,
    menu_tokens,
    pre_parse,
    strip_times,
    was_corrected,
)
from mia.templates.retail.seed import ITEMS as MENU

FERINOS = menu_tokens((name, codes) for name, codes, _ in MENU)


def split(text: str) -> list[tuple[int | None, str]]:
    return [(g.quantity, g.words) for g in pre_parse(text, FERINOS)[0]]


def test_number_then_words_and_words_then_number() -> None:
    groups, _ = pre_parse("3 special 5 classic", FERINOS)
    assert [(g.quantity, g.words) for g in groups] == [(3, "special"), (5, "classic")]
    groups, _ = pre_parse("special 3 classic 5", FERINOS)
    assert [(g.quantity, g.words) for g in groups] == [(3, "special"), (5, "classic")]


def test_short_codes_and_filler_words() -> None:
    groups, _ = pre_parse("sp 3 cl 5 po", FERINOS)
    assert [(g.quantity, g.words) for g in groups] == [(3, "sp"), (5, "cl")]
    groups, _ = pre_parse("nakabenta ng 12 ube", FERINOS)
    assert [(g.quantity, g.words) for g in groups] == [(12, "ube")]  # a leading stray word


def test_total_is_split_from_the_groups() -> None:
    groups, total = pre_parse("3 special 5 classic total 1,450", FERINOS)
    assert total == 1450 and len(groups) == 2
    groups, total = pre_parse("kabuuan 1450", FERINOS)
    assert total == 1450 and groups == []


def test_no_numbers_gives_no_groups() -> None:
    assert pre_parse("how are we doing today", FERINOS) == ([], None)


def test_currency_symbols_are_stripped() -> None:
    assert pre_parse("kabuuan \u20b11,450", FERINOS)[1] == 1450
    assert pre_parse("total $1450", FERINOS)[1] == 1450


def test_was_corrected_follows_the_negation_rule() -> None:
    assert was_corrected("5 classic hindi 6")
    assert not was_corrected("5 classic 6 special")


def test_a_negation_drops_the_old_number() -> None:
    assert split("5 classic hindi 6") == [(5, "classic")]
    assert split("4 special instead of 3") == [(4, "special")]
    assert split("sorry, 4 special not 3") == [(4, "special")]
    assert split("cl dapat 8, dili 6") == [(8, "cl dapat")]


def test_a_leading_verb_is_not_an_item() -> None:
    assert split("sold 3 special 5 classic") == [(3, "special"), (5, "classic")]


def test_words_then_number_with_a_trailing_particle() -> None:
    assert split("sp 4 cl 6 la") == [(4, "sp"), (6, "cl")]
    assert split("salted egg 5 karon") == [(5, "salted egg")]


def test_on_a_tie_the_ending_decides() -> None:
    assert split("zorblax 3 quux 5") == [(3, "zorblax"), (5, "quux")]
    assert split("3 zorblax 5 quux") == [(3, "zorblax"), (5, "quux")]


def test_find_times() -> None:
    assert find_times("sold out of special at 2pm") == [("t0", dt.time(14, 0))]
    assert find_times("14:30 ubos na") == [("t0", dt.time(14, 30))]
    assert find_times("alas dos ubos na ang ube") == [("t0", dt.time(14, 0))]
    assert find_times("alas 10") == [("t0", dt.time(10, 0))]
    assert find_times("3 special 5 classic") == []
    assert find_times("at 2:15 pm and again 5pm") == [
        ("t0", dt.time(14, 15)),
        ("t1", dt.time(17, 0)),
    ]


def test_find_times_edges() -> None:
    assert find_times("12am 12 PM") == [("t0", dt.time(0, 0)), ("t1", dt.time(12, 0))]
    assert find_times("alas 9 at alas siyete") == [("t0", dt.time(9, 0)), ("t1", dt.time(7, 0))]
    assert find_times("13pm 25:00 alas 13 2") == []


def test_find_times_alas_12_is_noon_and_an_hour_starts_a_number() -> None:
    assert find_times("alas 12") == [("t0", dt.time(12, 0))]
    assert find_times("alas dose") == [("t0", dt.time(12, 0))]
    assert find_times("112pm 3:105pm") == []


def test_times_with_a_space_are_not_count_groups() -> None:
    assert split(strip_times("ubos na ang special 3 pm")) == []
    assert split(strip_times("5 ube na lang alas 2")) == [(5, "ube")]
    assert find_times("5 ube na lang alas 2") == [("t0", dt.time(14, 0))]
    assert split(strip_times("special sold out at 2:15 pm")) == []
    assert split(strip_times("5 ube left at 3 pm")) == [(5, "ube left at")]
    assert strip_times("3 special 5 classic 13pm") == "3 special 5 classic 13pm"  # not a time


def test_buy_words() -> None:
    for text in (
        "order 10 trays of eggs",
        "mag-order ng 5 kg asukal",
        "pa reorder sa flour",
        "bumili ng 2 kg keso",
        "palit og 30 niyog",
        "osta 3 kg sokeria",
    ):
        assert has_buy_word(text), text
    assert not has_buy_word("4 kg asukal na lang")
    assert not has_buy_word("received 10 trays of eggs")


MONDAY = dt.date(2026, 10, 19)


def test_find_dates_next_week_weekday_in_english_filipino_and_finnish() -> None:
    assert find_dates("next week Monday", MONDAY, "en") == [("d0", dt.date(2026, 10, 26))]
    assert find_dates("sa susunod na linggo Lunes", MONDAY, "fil") == [
        ("d0", dt.date(2026, 10, 26))
    ]
    assert find_dates("ensi viikon keskiviikkona", MONDAY, "fi") == [("d0", dt.date(2026, 10, 28))]


def test_find_dates_a_range_after_next_week_stays_in_that_week() -> None:
    dates = find_dates("leave next week Monday to Wednesday", MONDAY, "en")
    assert dates == [("d0", dt.date(2026, 10, 26)), ("d1", dt.date(2026, 10, 28))]


def test_find_dates_weekday_is_the_next_one_today_excluded() -> None:
    assert find_dates("monday", MONDAY, "en") == [("d0", dt.date(2026, 10, 26))]
    assert find_dates("Biyernes po", MONDAY, "fil") == [("d0", dt.date(2026, 10, 23))]
    assert find_dates("today", MONDAY, "en") == [("d0", MONDAY)]


def test_find_dates_month_names_iso_and_day_words() -> None:
    christmas = dt.date(2026, 12, 25)
    assert find_dates("Dec 25", MONDAY, "en") == [("d0", christmas)]
    assert find_dates("25 Disyembre", MONDAY, "fil") == [("d0", christmas)]
    assert find_dates("2026-12-25", MONDAY, "en") == [("d0", christmas)]
    assert find_dates("bukas", MONDAY, "fil") == [("d0", dt.date(2026, 10, 20))]
    assert find_dates("huomenna", MONDAY, "fi") == [("d0", dt.date(2026, 10, 20))]
    assert find_dates("ugma ug karon", MONDAY, "ceb") == [
        ("d0", dt.date(2026, 10, 20)),
        ("d1", MONDAY),
    ]


def test_find_dates_never_a_bare_number() -> None:
    assert find_dates("3 special 5 classic", MONDAY, "en") == []
    assert find_dates("may 3 special po", MONDAY, "fil") == []
    assert find_dates("Feb 30 or 2026-13-01", MONDAY, "en") == []


def test_find_dates_a_filipino_week_phrase_alone_is_not_a_sunday() -> None:
    assert find_dates("sa susunod na linggo po", MONDAY, "fil") == []
    assert find_dates("susunod na linggo", MONDAY, "fil") == []
    assert find_dates("ngayong linggo", MONDAY, "fil") == []
    assert find_dates("sa susunod na linggo Lunes", MONDAY, "fil") == [
        ("d0", dt.date(2026, 10, 26))
    ]
    assert find_dates("sa Linggo", MONDAY, "fil") == [("d0", dt.date(2026, 10, 25))]
