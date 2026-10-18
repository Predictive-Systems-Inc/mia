import asyncio
import datetime as dt
from typing import Any

import pytest
from sqlmodel import Session, select

from mia.agents.shift_supervisor import actions, decider
from mia.agents.shift_supervisor.agent import MANIFEST
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.jev import JevError
from mia.core.models import Actor, Branch, EgressLog, Person, UsageCloudRequest
from mia.settings import get_settings
from tests.jev_fake import answers_for, choice, fake_jev

TODAY = dt.date(2026, 10, 17)


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A TypeSafe key in the settings (re-read after setenv)."""
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    get_settings.cache_clear()


def _query(**over: Any) -> actions.Query:
    base: dict[str, Any] = {
        "message": "I'm sick tomorrow",
        "previous_mia_message": "",
        "role": "cleaner",
        "today": TODAY,
        "open_cover_request": "",
        "dates": actions._dates(TODAY),
        "visits": {"v1": "Kalasatama, saturday 2026-10-18 06:30-09:00"},
        "sites": {"l1": "Kamppi", "l2": "Kalasatama"},
        "people": {"p1": "Mikael Nieminen", "p2": "Maria Mäkinen"},
        "checklist_items": {"i0": "Vacuum the floors"},
        "last_cover_visit": None,
    }
    base.update(over)
    return actions.Query(**base)


def _body(q: actions.Query) -> dict[str, Any]:
    return actions.build_request(q, "jev-1.13.0")


def test_confident_absence_becomes_record_absence() -> None:
    q = _query()
    a = answers_for(_body(q), "record_absence", date="2026-10-18", reason="sick")
    d = decider.parse(a, q)
    assert d.action == "record_absence" and d.raw_action == "record_absence"
    assert d.args == {
        "date": "2026-10-18",
        "reason": "sick",
        "partial_day": None,
        "person_name": None,
    }


def test_absence_without_a_date_is_today() -> None:
    q = _query(message="I'm sick")
    d = decider.parse(answers_for(_body(q), "record_absence", reason="sick"), q)
    assert d.args["date"] == TODAY.isoformat()


def test_low_confidence_clarifies_with_the_top_actions() -> None:
    q = _query()
    probs = {"record_absence": 0.45, "respond_to_cover": 0.40, "reply_only": 0.15}
    d = decider.parse(answers_for(_body(q), "record_absence", 0.45, probs), q)
    assert d.action == "clarify" and d.raw_action == "record_absence"
    assert [a.action for a in d.alternatives] == [
        "record_absence",
        "respond_to_cover",
        "reply_only",
    ]


def test_an_unstated_slot_does_not_lower_the_confidence() -> None:
    """Not stated means the tool's default applies; nothing was read from the message."""
    q = _query(message="I'm sick today")
    a = answers_for(_body(q), "record_absence", reason="sick")
    a["partial_day"] = choice("not_stated", 0.47)
    d = decider.parse(a, q)
    assert d.action == "record_absence" and d.args["partial_day"] is None


def test_an_uncertain_unstated_date_still_asks_for_an_absence() -> None:
    """For an absence, not stated means "today" and "the sender": an uncertain default writes
    on the wrong day or for the wrong person, so it counts."""
    q = _query(message="I'm sick")
    a = answers_for(_body(q), "record_absence", reason="sick")
    a["date"] = choice("not_stated", 0.4)
    assert decider.parse(a, q).action == "clarify"


def test_an_uncertain_unstated_person_still_asks_for_an_absence() -> None:
    q = _query(message="Mikael is sick today", role="supervisor")
    a = answers_for(_body(q), "record_absence", reason="sick", date=TODAY.isoformat())
    a["person"] = choice("not_stated", 0.45)
    assert decider.parse(a, q).action == "clarify"


def test_a_day_outside_the_list_asks_instead_of_using_today() -> None:
    q = _query(message="I was sick yesterday")
    a = answers_for(_body(q), "record_absence", reason="sick", date=actions.ANOTHER_DAY)
    d = decider.parse(a, q)
    assert d.action == "clarify" and d.missing == "date"


def test_a_stated_slot_with_low_confidence_still_clarifies() -> None:
    q = _query()
    a = answers_for(_body(q), "record_absence", reason="sick")
    a["date"] = choice("2026-10-18", 0.4)
    assert decider.parse(a, q).action == "clarify"


def test_an_uncertain_visit_falls_back_to_site_and_date() -> None:
    q = _query(message="Who can cover Kalasatama tomorrow at 6:30?", role="supervisor")
    a = answers_for(_body(q), "find_replacements", site="l2", date="2026-10-18")
    a["visit"] = choice("v1", 0.5)
    d = decider.parse(a, q)
    assert d.action == "find_replacements"
    assert d.args == {"location_name": "Kalasatama", "date": "2026-10-18"}


def test_an_alternative_with_an_uncertain_input_is_not_offered() -> None:
    """The input that caused the question must not ride along on a button."""
    q = _query(message="Mikael sick today", role="supervisor")
    a = answers_for(_body(q), "record_absence", reason="sick", date=TODAY.isoformat())
    a["person"] = choice("p1", 0.40)
    d = decider.parse(a, q)
    assert d.action == "clarify"
    absence = next(x for x in d.alternatives if x.action == "record_absence")
    assert absence.missing is not None


def test_a_shared_first_name_without_a_surname_asks() -> None:
    people = {"p1": "Maria Mäkinen", "p2": "Maria Virtanen"}
    q = _query(message="Maria is sick today", role="supervisor", people=people)
    a = answers_for(_body(q), "record_absence", reason="sick", date=TODAY.isoformat(), person="p1")
    d = decider.parse(a, q)
    assert d.action == "clarify" and d.missing == "person"


def test_a_shared_first_name_with_the_surname_acts() -> None:
    people = {"p1": "Maria Mäkinen", "p2": "Maria Virtanen"}
    q = _query(message="Maria Virtanen is sick today", role="supervisor", people=people)
    a = answers_for(_body(q), "record_absence", reason="sick", date=TODAY.isoformat(), person="p2")
    d = decider.parse(a, q)
    assert d.action == "record_absence" and d.args["person_name"] == "Maria Virtanen"


def test_a_blank_staff_name_does_not_break_the_name_check() -> None:
    """A person row with an empty name (a half-filled import) is never a namesake."""
    people = {"p1": "Maria Mäkinen", "p2": "  "}
    q = _query(message="Maria is sick today", role="supervisor", people=people)
    a = answers_for(_body(q), "record_absence", reason="sick", date=TODAY.isoformat(), person="p1")
    assert decider.parse(a, q).action == "record_absence"
    a = answers_for(_body(q), "record_absence", reason="sick", date=TODAY.isoformat(), person="p2")
    assert decider.parse(a, q).action == "record_absence"


def test_assign_without_a_cover_search_clarifies() -> None:
    q = _query(message="Assign Mikael", role="supervisor")
    d = decider.parse(answers_for(_body(q), "assign_cover", person="p1"), q)
    assert d.action == "clarify" and d.missing == "visit"


def test_assign_after_a_cover_search_uses_that_visit() -> None:
    q = _query(message="Assign Mikael", role="supervisor", last_cover_visit="v1")
    d = decider.parse(answers_for(_body(q), "assign_cover", person="p1"), q)
    assert d.action == "assign_cover"
    assert d.args == {"visit_id": "v1", "candidate_id": "p1"}


def test_find_cover_by_site_and_date_when_no_visit_matched() -> None:
    q = _query(message="Who can cover Kalasatama tomorrow?", role="supervisor")
    a = answers_for(_body(q), "find_replacements", site="l2", date="2026-10-18")
    d = decider.parse(a, q)
    assert d.args == {"location_name": "Kalasatama", "date": "2026-10-18"}


def test_cover_reply_reads_the_noul() -> None:
    q = _query(message="sorry I can't")
    d = decider.parse(answers_for(_body(q), "respond_to_cover", accept=0.05), q)
    assert d.action == "respond_to_cover" and d.args == {"accept": False}


def test_site_problem_copies_the_message() -> None:
    q = _query(message="the door code does not work at Kamppi")
    a = answers_for(_body(q), "report_site_problem", problem_kind="cannot_access", site="l1")
    d = decider.parse(a, q)
    assert d.args == {"kind": "cannot_access", "text": q.message, "location_name": "Kamppi"}


def test_reply_only_carries_its_kind() -> None:
    q = _query(message="thanks!")
    d = decider.parse(answers_for(_body(q), "reply_only", conversation="thanks"), q)
    assert d.action == "reply_only" and d.args == {"kind": "thanks"}


def test_unknown_choice_is_a_decide_error() -> None:
    q = _query()
    a = answers_for(_body(q), "record_absence")
    a["date"] = choice("1999-01-01")  # not an option
    with pytest.raises(decider.DecideError):
        decider.parse(a, q)
    with pytest.raises(decider.DecideError):
        decider.parse({"action": choice("no_such_action")}, q)


def test_a_wrongly_shaped_answer_is_a_decide_error() -> None:
    q = _query()
    a = answers_for(_body(q), "record_absence")
    a["action"]["probabilities"] = [["record_absence", 0.9]]  # a list, not an object
    with pytest.raises(decider.DecideError):
        decider.parse(a, q)


@pytest.mark.parametrize("payload", [[1, 2], None, {"answers": None}])
def test_a_body_that_is_not_an_answer_object_is_a_jev_error(
    payload: Any,
    session: Session,
    people: dict[str, Person],
    branch: Branch,
    monkeypatch: pytest.MonkeyPatch,
    key: None,
) -> None:
    import httpx

    monkeypatch.setattr(
        jev, "_inner", lambda: httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    )
    with egress_context(_ctx(session, people, branch)), pytest.raises(JevError):
        _run(_query())


def _ctx(
    session: Session, people: dict[str, Person], branch: Branch, level: str = "pseudonymised"
) -> EgressContext:
    return EgressContext(
        session=session,
        actor=Actor.person(people["Juha"]).as_agent(MANIFEST.roles.agent_role),
        organisation_id=branch.organisation_id,
        agent_id=MANIFEST.id,
        purpose="shift_supervisor.decide",
        level=level,
        provider="typesafe",
    )


def _run(q: actions.Query) -> decider.Decision:
    return asyncio.run(decider.decide(q))


def test_decide_goes_through_egress(
    session: Session,
    people: dict[str, Person],
    branch: Branch,
    monkeypatch: pytest.MonkeyPatch,
    key: None,
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        jev, "_inner", lambda: fake_jev(lambda b: answers_for(b, "reply_only"), seen)
    )
    with egress_context(_ctx(session, people, branch)):
        d = _run(_query())
    assert d.action == "reply_only" and len(seen) == 1
    assert session.exec(select(EgressLog).where(EgressLog.provider == "typesafe")).first()
    used = session.exec(select(UsageCloudRequest)).one()  # Jev's input/output token names
    assert (used.input_tokens, used.output_tokens) == (100, 12)


def test_a_name_that_prefixes_a_key_leaves_keys_and_ids_alone(
    session: Session,
    people: dict[str, Person],
    branch: Branch,
    monkeypatch: pytest.MonkeyPatch,
    key: None,
) -> None:
    """Pseudonymising a staff member called Per must not turn the `person` and `period`
    question keys, or the `tomorrow` option, into tokens; the name in the message still goes."""
    from mia.core import store

    store.insert(
        session, Person(branch_id=branch.id, name="Per Lindqvist"), Actor.person(people["Sanna"])
    )
    store.insert(
        session, Person(branch_id=branch.id, name="Tom Berg"), Actor.person(people["Sanna"])
    )
    session.commit()
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        jev,
        "_inner",
        lambda: fake_jev(lambda b: answers_for(b, "get_my_visits", period="tomorrow"), seen),
    )
    q = _query(message="Per Lindqvist: show my visits tomorrow")
    with egress_context(_ctx(session, people, branch)):
        d = _run(q)
    body = seen[0]
    assert {"person", "period"} <= set(body["questions"])
    assert "tomorrow" in body["questions"]["period"]["criteria"]
    assert "Lindqvist" not in body["state"]["message"]
    assert "Mikael" not in str(body["questions"]["person"]["criteria"])  # descriptions go too
    assert d.action == "get_my_visits"


def test_egress_none_blocks_before_the_network(
    session: Session,
    people: dict[str, Person],
    branch: Branch,
    monkeypatch: pytest.MonkeyPatch,
    key: None,
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(lambda b: {}, seen))
    with (
        egress_context(_ctx(session, people, branch, level="none")),
        pytest.raises(JevError),
    ):
        _run(_query())
    assert seen == []


def test_no_key_is_a_jev_error() -> None:
    with pytest.raises(JevError):
        _run(_query())


@pytest.mark.parametrize("status", [400, 401, 422, 529])
def test_error_status_is_a_jev_error(
    status: int,
    session: Session,
    people: dict[str, Person],
    branch: Branch,
    monkeypatch: pytest.MonkeyPatch,
    key: None,
) -> None:
    monkeypatch.setattr(jev, "BACKOFF", 0.0)
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(lambda b: {}, seen, status=status))
    with egress_context(_ctx(session, people, branch)), pytest.raises(JevError):
        _run(_query())
    assert len(seen) == (3 if status == 529 else 1)  # 429 and 529 retry twice
