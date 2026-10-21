import datetime as dt

from mia.agents.parsing import (
    DAY_NAMES,
    find_dates,
    find_prices,
    find_tender,
    find_times,
    has_buy_word,
    has_negation,
    menu_tokens,
    pre_parse,
    strip_dates,
    strip_menu_names,
    strip_times,
    tenders_in,
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


def test_find_dates_today_tomorrow_and_next_week_in_cebuano() -> None:
    assert find_dates("leave ko ugma", MONDAY, "ceb") == [("d0", dt.date(2026, 10, 20))]
    assert find_dates(
        "Mag-file ko og leave sunod semana, Lunes hangtod Miyerkules", MONDAY, "ceb"
    ) == [
        ("d0", dt.date(2026, 10, 26)),
        ("d1", dt.date(2026, 10, 28)),
    ]
    assert find_dates("holiday ba ang Biyernes sa sunod semana?", MONDAY, "ceb") == [
        ("d0", dt.date(2026, 10, 30))
    ]
    # "karong bulana" (this month) is a period, never "karon" (today).
    assert find_dates("pila na ka oras ko nagtrabaho karong bulana", MONDAY, "ceb") == []


def test_find_dates_today_tomorrow_and_next_week_in_hiligaynon() -> None:
    assert find_dates("holiday bala buwas?", MONDAY, "hil") == [("d0", dt.date(2026, 10, 20))]
    assert find_dates("Masakit ako subong", MONDAY, "hil") == [("d0", MONDAY)]
    assert find_dates("sa masunod nga semana Martes", MONDAY, "hil") == [
        ("d0", dt.date(2026, 10, 27))
    ]
    assert find_dates("pila na ka oras ako nag-obra subong nga bulan", MONDAY, "hil") == []


def test_find_dates_today_tomorrow_and_next_week_in_waray() -> None:
    assert find_dates("holiday ba buwas?", MONDAY, "war") == [("d0", dt.date(2026, 10, 20))]
    assert find_dates("Masakit ako yana", MONDAY, "war") == [("d0", MONDAY)]
    assert find_dates("holiday ba an Biyernes ha sunod nga semana?", MONDAY, "war") == [
        ("d0", dt.date(2026, 10, 30))
    ]
    assert find_dates("pira na an akon overtime yana nga bulan", MONDAY, "war") == []


def test_find_dates_today_tomorrow_and_next_week_in_bikol() -> None:
    assert find_dates("holiday daw sa aga?", MONDAY, "bcl") == [("d0", dt.date(2026, 10, 20))]
    assert find_dates("May helang ako ngunyan", MONDAY, "bcl") == [("d0", MONDAY)]
    assert find_dates("leave sa sunod na semana, Lunes sagkod Miyerkules", MONDAY, "bcl") == [
        ("d0", dt.date(2026, 10, 26)),
        ("d1", dt.date(2026, 10, 28)),
    ]
    assert find_dates("sweldo na daw ngunyan na semana?", MONDAY, "bcl") == []
    assert find_dates("marhay na aga", MONDAY, "bcl") == []


def test_domingo_is_sunday_in_hiligaynon_waray_and_bikol() -> None:
    sunday = dt.date(2026, 10, 25)
    for lang, text in (("hil", "sa Domingo"), ("war", "han Domingo"), ("bcl", "sa Domingo")):
        assert find_dates(text, MONDAY, lang) == [("d0", sunday)], lang
        assert DAY_NAMES[lang][6] == "domingo" and DAY_NAMES[lang][0] == "lunes"
    assert find_dates("Miyerkoles", MONDAY, "hil") == [("d0", dt.date(2026, 10, 21))]


def test_find_prices_reads_pesos_to_minor_units() -> None:
    assert find_prices("subukan natin \u20b150 o 49.50 pesos", "fil") == [
        ("p0", 5000),
        ("p1", 4950),
    ]
    assert find_prices("P50, php 45 o 1,450 piso", "fil") == [
        ("p0", 5000),
        ("p1", 4500),
        ("p2", 145000),
    ]
    assert find_prices("49,5 lang", "fil") == [("p0", 4950)]  # a decimal comma


def test_times_and_dates_are_not_prices() -> None:
    assert find_prices("48 simula Nov 2 alas 3", "fil") == [("p0", 4800)]
    assert find_prices("45 from 2026-11-02 at 3 pm or 14:30", "en") == [("p0", 4500)]
    assert find_prices("45 from May 5", "en") == [("p0", 4500)]  # an English date
    assert find_prices("may 5 pesos pa", "fil") == [("p0", 500)]  # Filipino "may": there is
    assert find_prices("sp50 ube", "fil") == []  # a digit inside a word is not an amount


def test_a_count_is_never_a_price() -> None:
    kape = menu_tokens([("Kape", [])])
    assert find_prices("3 kape for 65", "en", kape) == [("p0", 6500)]
    assert find_prices("40 classic for 44", "en", FERINOS) == [("p0", 4400)]  # inside 20 percent
    assert find_prices("subukan natin 50 ang classic", "fil", FERINOS) == [("p0", 5000)]
    assert find_prices("i-promo natin: 3 Classic sa 110", "fil", FERINOS) == [("p0", 11000)]
    assert find_prices("170 na ang Box of 4", "fil", FERINOS) == [("p0", 17000)]
    assert find_prices("2 box of 4 for 280", "en", FERINOS) == [("p0", 28000)]
    assert find_prices("3 kape for 65", "en") == [("p0", 300), ("p1", 6500)]  # no menu given


def test_a_negation_word_marks_the_message() -> None:
    assert has_negation("dai, pundohon na an bagong presyo")
    for text in ("huwag na", "wag na lang", "ayaw ko", "no, go back", "stop it", "hindi"):
        assert has_negation(text), text
    assert not has_negation("ituloy na natin, keep it")


def test_the_count_parser_reads_a_tender_word() -> None:
    found = (
        find_tender("gcash 3 classic"),
        find_tender("3 classic"),
        find_tender("gcash 2 grab 1"),
    )
    assert found == ("gcash", None, None)
    assert (find_tender("G-Cash 3"), find_tender("paymaya 2"), find_tender("panda 4")) == (
        "gcash",
        "maya",
        "foodpanda",
    )
    assert [g.words for g in pre_parse("g-cash 3 classic", {"classic"})[0]] == ["classic"]
    assert tenders_in("gcash 2 grab 1 G-Cash") == ["gcash", "grab"]
    assert tenders_in("3 classic") == []


def test_strip_dates_takes_out_times_and_dates_but_a_filipino_may() -> None:
    assert strip_dates("200 classic sa Dec 24 alas 3", "fil").split() == ["200", "classic", "sa"]
    assert strip_dates("may 5 ube", "fil").split() == ["may", "5", "ube"]
    assert strip_dates("May 5 ube", "en").split() == ["ube"]


def test_strip_menu_names_takes_out_a_name_with_a_digit() -> None:
    assert strip_menu_names("3 Box of 4 at 2 kape", FERINOS).split() == ["3", "at", "2", "kape"]
