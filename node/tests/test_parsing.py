import datetime as dt

from mia.agents.parsing import find_times, menu_tokens, pre_parse, was_corrected
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
