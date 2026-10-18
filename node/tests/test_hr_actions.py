"""The hr officer's actions, Jev request and argument mapping (pure, no model)."""

import dataclasses
import datetime as dt
from typing import Any

from sqlmodel import Session

from mia.agents.decider import Reader, pseudonymised
from mia.agents.hr_officer.actions import Query, build_query, build_request
from mia.agents.hr_officer.decider import _args
from mia.core.egress import Pseudonymiser
from mia.core.models import Branch, Person
from tests.jev_fake import answers_for
from tests.test_sales_tools import deps_for

TODAY = dt.date(2026, 10, 19)  # a Monday


def build(session: Session, ferinos: tuple[Branch, dict[str, Person]], who: str, message: str):
    q = build_query(deps_for(session, ferinos[1][who]), message, "")
    from mia.agents.parsing import find_dates

    return dataclasses.replace(
        q,
        today=TODAY,
        dates={i: d.isoformat() for i, d in find_dates(message, TODAY, "en")},
    )


def args(
    q: Query, action: str, confidence: float = 0.95, **slots: Any
) -> tuple[dict[str, Any], str | None]:
    answers = answers_for(build_request(q, "m"), action, confidence, **slots)
    return _args(action, Reader(answers, q))


def test_file_leave_next_week_monday_to_wednesday(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "Ana", "I want to file leave next week Monday to Wednesday")
    assert list(q.dates.values()) == ["2026-10-26", "2026-10-28"]
    out, missing = args(q, "file_leave", leave_kind="sick", leave_start="d0", leave_end="d1")
    assert missing is None
    assert out == {"kind": "sick", "start": "2026-10-26", "end": "2026-10-28"}


def test_leave_end_defaults_to_start(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "Ana", "leave tomorrow")
    out, missing = args(q, "file_leave", leave_start="d0")
    assert missing is None
    assert out == {"kind": "vacation", "start": "2026-10-20", "end": "2026-10-20"}
    _, missing = args(q, "file_leave")
    assert missing == "leave_start"


def test_my_hours_last_cutoff(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "Ana", "how many hours last cutoff")
    out, missing = args(q, "my_hours", period="last_cutoff")
    assert missing is None
    assert out == {"start": "2026-10-01", "end": "2026-10-15", "person_id": None}
    out, _ = args(q, "my_hours")  # not stated: this cutoff
    assert (out["start"], out["end"]) == ("2026-10-16", "2026-10-31")
    out, _ = args(q, "my_hours", period="last_month")
    assert (out["start"], out["end"]) == ("2026-09-01", "2026-09-30")


def test_certificate_by_the_owner_names_a_person(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "Rosa", "certificate of employment for Ana")
    ana = ferinos[1]["Ana"].id
    assert ana in q.people
    out, missing = args(q, "certificate", person=ana)
    assert (out, missing) == ({"person_id": ana}, None)
    assert args(q, "certificate")[1] == "person"


def test_no_person_question_for_a_clerk(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "Ana", "certificate of employment")
    assert q.people == {}
    assert "person" not in build_request(q, "m")["questions"]
    assert args(q, "certificate")[1] == "person"


def test_holiday_question_needs_a_day(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "Ana", "is Monday a holiday")
    assert len(q.days) == 14 and q.days["h0"] == "2026-10-19 (lunes)"
    assert args(q, "holiday_pay")[1] == "day"
    out, missing = args(q, "holiday_pay", day="h7")
    assert (out, missing) == ({"day": "2026-10-26"}, None)


def test_which_contribution_and_empty_actions(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "Ana", "sss")
    assert args(q, "contributions", which="sss")[0] == {"which": "sss"}
    assert args(q, "contributions", which="all")[0] == {"which": "all"}
    for action in ("payday", "thirteenth", "leave_balance", "my_payslip"):
        assert args(q, action) == ({}, None)
    assert args(q, "reply_only", conversation="greeting")[0] == {"kind": "greeting"}


def test_instructions_carry_no_message_text(session: Session, ferinos: Any) -> None:
    message = "zebra-quartz leave on 2026-12-25"
    q = build(session, ferinos, "Rosa", message)
    body = build_request(q, "m")
    assert body["state"]["message"] == message and body["state"]["dates"] == ["2026-12-25"]
    assert all(message not in qn["instructions"] for qn in body["questions"].values())
    assert "zebra" not in str([qn["criteria"] for qn in body["questions"].values()])


def test_dates_are_pseudonymised_item_by_item(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "Ana", "leave on 2026-12-25 for Maria")
    body = build_request(q, "m")
    out = pseudonymised(body, Pseudonymiser({"Maria": "Person_1"}))["state"]
    assert out["dates"] == ["2026-12-25"] and "Person_1" in out["message"]
