import asyncio
import datetime as dt
from typing import Any

import pytest
from sqlmodel import Session, select

from mia.agents.dispatcher import actions, decider
from mia.agents.dispatcher.agent import MANIFEST
from mia.core.egress import EgressContext, egress_context
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


def _ctx(
    session: Session, people: dict[str, Person], branch: Branch, level: str = "pseudonymised"
) -> EgressContext:
    return EgressContext(
        session=session,
        actor=Actor.person(people["Juha"]).as_agent(MANIFEST.roles.agent_role),
        organisation_id=branch.organisation_id,
        agent_id=MANIFEST.id,
        purpose="dispatcher.decide",
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
        decider, "_inner", lambda: fake_jev(lambda b: answers_for(b, "reply_only"), seen)
    )
    with egress_context(_ctx(session, people, branch)):
        d = _run(_query())
    assert d.action == "reply_only" and len(seen) == 1
    assert session.exec(select(EgressLog).where(EgressLog.provider == "typesafe")).first()
    used = session.exec(select(UsageCloudRequest)).one()  # Jev's input/output token names
    assert (used.input_tokens, used.output_tokens) == (100, 12)


def test_egress_none_blocks_before_the_network(
    session: Session,
    people: dict[str, Person],
    branch: Branch,
    monkeypatch: pytest.MonkeyPatch,
    key: None,
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(decider, "_inner", lambda: fake_jev(lambda b: {}, seen))
    with (
        egress_context(_ctx(session, people, branch, level="none")),
        pytest.raises(decider.DecideError),
    ):
        _run(_query())
    assert seen == []


def test_no_key_is_a_decide_error() -> None:
    with pytest.raises(decider.DecideError):
        _run(_query())


@pytest.mark.parametrize("status", [400, 401, 422, 529])
def test_error_status_is_a_decide_error(
    status: int,
    session: Session,
    people: dict[str, Person],
    branch: Branch,
    monkeypatch: pytest.MonkeyPatch,
    key: None,
) -> None:
    monkeypatch.setattr(decider, "BACKOFF", 0.0)
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(decider, "_inner", lambda: fake_jev(lambda b: {}, seen, status=status))
    with egress_context(_ctx(session, people, branch)), pytest.raises(decider.DecideError):
        _run(_query())
    assert len(seen) == (3 if status == 529 else 1)  # 429 and 529 retry twice
