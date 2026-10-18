import datetime as dt

from mia.chat.route_memory import Switch, Tap, key_of, learned

NOW = dt.datetime(2026, 10, 19, 9, tzinfo=dt.UTC)
A, B = "agent_a", "agent_b"  # ids are opaque to the memory


def _tap(key: str, agent: str, days_ago: float = 1, thread: str = "t1", eid: str = "e") -> Tap:
    return Tap(key, agent, NOW - dt.timedelta(days=days_ago), thread, eid)


def test_key_normalises_case_space_punctuation_and_digits() -> None:
    assert key_of("  3 Special,  5 classic!! ") == "# special, # classic"
    assert key_of("Sold 12 Overload") == key_of("sold 7 overload")


def test_digits_normalise_but_words_do_not() -> None:
    assert key_of("3 special") != key_of("3 classic")


def test_one_tap_learns_nothing() -> None:
    assert learned([_tap("k", A)], [], {}, NOW) == {}


def test_two_taps_for_the_same_agent_learn_the_key() -> None:
    assert learned([_tap("k", A), _tap("k", A, 2)], [], {}, NOW) == {"k": A}


def test_conflicting_taps_learn_nothing() -> None:
    taps = [_tap("k", A), _tap("k", A, 2), _tap("k", B, 3)]
    assert learned(taps, [], {}, NOW) == {}


def test_taps_older_than_the_window_do_not_count() -> None:
    assert learned([_tap("k", A, 1), _tap("k", A, 91)], [], {}, NOW) == {}


def test_a_switch_away_within_an_hour_undoes_the_tap() -> None:
    tap = _tap("k", A)
    undo = Switch(A, tap.at + dt.timedelta(minutes=30), "t1")  # on any message
    assert learned([tap, _tap("k", A, 2)], [undo], {}, NOW) == {}


def test_a_switch_after_an_hour_or_in_another_thread_does_not_undo() -> None:
    tap = _tap("k", A)
    late = Switch(A, tap.at + dt.timedelta(hours=2), "t1")
    elsewhere = Switch(A, tap.at + dt.timedelta(minutes=5), "t2")
    assert learned([tap, _tap("k", A, 2)], [late, elsewhere], {}, NOW) == {"k": A}


def test_a_switch_from_another_agent_or_before_the_tap_does_not_undo() -> None:
    tap = _tap("k", A)
    other = Switch(B, tap.at + dt.timedelta(minutes=5), "t1")
    before = Switch(A, tap.at - dt.timedelta(minutes=5), "t1")
    assert learned([tap, _tap("k", A, 2)], [other, before], {}, NOW) == {"k": A}


def test_forget_discards_taps_before_it_only() -> None:
    old = [_tap("k", A, 5), _tap("k", A, 4)]
    forgotten = {"k": NOW - dt.timedelta(days=3)}
    assert learned(old, [], forgotten, NOW) == {}
    new = [*old, _tap("k", A, 2), _tap("k", A, 1)]
    assert learned(new, [], forgotten, NOW) == {"k": A}


def test_two_new_taps_after_forget_learn_again() -> None:
    forgotten = {"k": NOW - dt.timedelta(days=3)}
    taps = [_tap("k", A, 5), _tap("k", A, 4), _tap("k", A, 2), _tap("k", A, 1)]
    assert learned(taps, [], forgotten, NOW) == {"k": A}
    assert learned(taps[:3], [], forgotten, NOW) == {}
