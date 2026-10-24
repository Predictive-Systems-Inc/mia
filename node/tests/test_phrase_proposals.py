"""Teach Mia phase 2 (spec 2026-10-22-teach-mia-design section 5, D45, D49): unrecognised
messages are recorded by key, the nightly proposals go through egress with their own purpose
inside the report model's cap, and an owner or admin approves each on a chat card."""

import asyncio
import datetime as dt
import functools
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic_ai import models
from sqlmodel import Session, col, select

from mia.agents.sales_supervisor import MANIFEST as SALES
from mia.agents.sales_supervisor import report_model
from mia.chat import features, phrases, proposals
from mia.chat.blocks import ChatReply
from mia.chat.proposals import Answer, Proposal
from mia.chat.service import _store, run_turn
from mia.core import approvals, db, jev, orgconfig, people
from mia.core.models import (
    Actor,
    Approval,
    Branch,
    EgressLog,
    Event,
    Message,
    Person,
    Thread,
    UsageCloudRequest,
)
from mia.i18n import t
from mia.settings import get_settings
from tests.conftest import RS_TODAY, Shop
from tests.jev_fake import answers_for, fake_jev
from tests.test_sales_report_model import Gateway, _spent

Ferinos = tuple[Branch, dict[str, Person]]
TODAY = {"message": 0, "agent_id": SALES.id, "action": "sales_today"}


def _route(monkeypatch: pytest.MonkeyPatch, report: str) -> None:
    monkeypatch.setenv("MIA_REPORT_MODEL", report)
    get_settings.cache_clear()


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch, rs_en: Ferinos) -> list[dict[int, str]]:
    """MIA_REPORT_MODEL=test answering sales_today for every message (production mode: a key
    needs two occurrences); the messages it read."""
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    _route(monkeypatch, "test")
    seen: list[dict[int, str]] = []

    def answer(messages: dict[int, str], offer: dict[str, Any]) -> Answer:
        seen.append(messages)
        return Answer(proposals=[Proposal(**{**TODAY, "message": i}) for i in messages])

    monkeypatch.setattr(proposals, "_fake_answer", answer)
    return seen


def _say(session: Session, person: Person, text: str, times: int = 1) -> None:
    """`times` turns of `text` by the person that ended in the ask to rephrase."""
    for _ in range(times):
        _, message = _store(session, person, text, None)
        phrases.record_unrecognised(session, Actor.person(person), person, message, SALES.id)
        session.commit()


def _night(session: Session, shop: Shop, days: int = 0, **kw: Any) -> int:
    shop.pin(22, 30, days)  # the Mall kiosk closes at 21:00
    return asyncio.run(proposals.propose(session, shop.kiosk.id, db.utcnow(), **kw))


def _turn(session: Session, person: Person, text: str, thread: str | None = None) -> ChatReply:
    reply = asyncio.run(run_turn(session, None, person, text, thread))
    session.commit()
    return reply


def _open(session: Session) -> list[Approval]:
    return list(session.exec(select(Approval).where(Approval.type == proposals.PROPOSAL)))


# ---- unrecognised messages -----------------------------------------------------------------


@pytest.fixture
def decider(monkeypatch: pytest.MonkeyPatch, rs_en: Ferinos) -> dict[str, Callable[..., Any]]:
    """Only the sales supervisor, its decider faked (offline): answers with state["answer"]."""
    only = orgconfig.OrgSettings(agents=[SALES.id])
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()
    state: dict[str, Callable[..., Any]] = {"answer": lambda b: answers_for(b, "clarify")}
    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(lambda b: state["answer"](b)))
    return state


def test_a_rephrase_and_something_else_are_recorded_by_key_only(
    session: Session, rs_en: Ferinos, decider: dict[str, Callable[..., Any]]
) -> None:
    rosa = rs_en[1]["Rosa"]
    reply = _turn(session, rosa, "Kumusta ang tinda 3?")
    assert t("clarify.rephrase", "en") in reply.text()
    unsure = {"sales_period": 0.4, "sales_today": 0.35}
    decider["answer"] = lambda b: answers_for(b, "sales_period", 0.4, unsure)
    asked = _turn(session, rosa, "total benta")
    _turn(session, rosa, t("clarify.something_else", "en"), asked.thread_id)
    found = session.exec(select(Event).where(Event.action == phrases.UNRECOGNISED)).all()
    assert [(e.after or {})["key"] for e in found] == ["kumusta ang tinda #", "total benta"]
    after = found[0].after or {}
    assert (after["agent_id"], after["role"], after["branch_id"]) == (
        SALES.id,
        "owner",
        rosa.branch_id,
    )
    assert "Kumusta" not in json.dumps([e.after for e in found])  # never the text


# ---- the nightly run -----------------------------------------------------------------------


def test_the_night_proposes_a_repeated_key_and_not_a_single_one(
    session: Session, rs_en: Ferinos, rs_shop: Shop, model: list[dict[int, str]]
) -> None:
    ana = rs_en[1]["Ana"]
    _say(session, ana, "total benta", 2)
    _say(session, ana, "magkano ube")
    assert _night(session, rs_shop) == 1
    assert model == [{0: "total benta"}]
    (card,) = _open(session)
    assert card.evidence == {
        "key": "total benta",
        "agent_id": SALES.id,
        "action": "sales_today",
        "branch_id": rs_shop.kiosk.id,
    }
    assert (card.channel, card.approver_roles) == ("chat", ["owner", "admin"])
    assert _night(session, rs_shop) == 0 and len(model) == 1  # once per branch per day


def test_dev_mode_proposes_a_single_key(
    monkeypatch: pytest.MonkeyPatch, session: Session, rs_en: Ferinos, rs_shop: Shop,
    model: list[dict[int, str]],
) -> None:  # fmt: skip
    monkeypatch.setenv("MIA_AUTH_MODE", "dev")
    get_settings.cache_clear()
    _say(session, rs_en[1]["Ana"], "magkano ube")
    assert _night(session, rs_shop) == 1


def test_nothing_before_closing_and_off_without_a_route(
    monkeypatch: pytest.MonkeyPatch, session: Session, rs_en: Ferinos, rs_shop: Shop,
    model: list[dict[int, str]],
) -> None:  # fmt: skip
    _say(session, rs_en[1]["Ana"], "total benta", 2)
    rs_shop.pin(20, 0)
    assert asyncio.run(proposals.propose(session, rs_shop.kiosk.id, db.utcnow())) == 0
    _route(monkeypatch, "")
    assert asyncio.run(proposals.run_due(db.utcnow())) == 0
    assert model == [] and _open(session) == []


def test_a_proposal_outside_the_lists_is_dropped(
    monkeypatch: pytest.MonkeyPatch, session: Session, rs_en: Ferinos, rs_shop: Shop,
    model: list[dict[int, str]],
) -> None:  # fmt: skip
    bad = [
        {"message": 0, "agent_id": SALES.id, "action": "void_receipt"},  # money: never taught
        {"message": 0, "agent_id": SALES.id, "action": "launch_rockets"},
        {"message": 0, "agent_id": "dispatcher", "action": "sales_today"},
        {"message": 7, "agent_id": SALES.id, "action": "sales_today"},  # no such message
        {"message": 0, "agent_id": SALES.id, "action": "sales_today", "missing": "both"},
    ]
    answer = Answer.model_construct(proposals=[Proposal.model_construct(**b) for b in bad])
    monkeypatch.setattr(proposals, "_fake_answer", lambda m, o: answer)
    _say(session, rs_en[1]["Ana"], "total benta", 2)
    assert _night(session, rs_shop) == 0
    assert _open(session) == [] and not features.groups(session)
    with pytest.raises(ValueError):
        Proposal.model_validate({**TODAY, "total": 5})  # an extra field fails the shape


def test_the_card_reaches_owner_and_admin_only(
    session: Session, rs_en: Ferinos, rs_shop: Shop, model: list[dict[int, str]]
) -> None:
    staff = rs_en[1]
    kiosk = rs_shop.kiosk
    admin = people.add_person(
        session, Actor.system(kiosk.id), branch_id=kiosk.id, name="Dina Admin", roles=["admin"],
        language="en",
    )  # fmt: skip
    session.commit()
    _say(session, staff["Ana"], "total benta", 2)
    _night(session, rs_shop)
    (card,) = _open(session)
    sent = session.exec(select(Event).where(Event.approval_id == card.id)).all()
    told = {e.entity_id for e in sent if e.action == "notification.sent"}  # message ids
    owners = {
        session.get(Thread, m.thread_id).person_id  # type: ignore[union-attr]
        for m in session.exec(select(Message).where(col(Message.id).in_(told)))
    }
    assert owners == {staff["Rosa"].id, admin.id}
    note = session.exec(select(Message).where(col(Message.id).in_(told))).first()
    assert note is not None and "Teach Mia: 'total benta' means" in note.text
    assert note.blocks[-1]["options"] == ["Approve", "Reject"]


def test_approve_teaches_and_the_next_message_routes_by_it(
    session: Session, rs_en: Ferinos, rs_shop: Shop, model: list[dict[int, str]]
) -> None:
    rosa = rs_en[1]["Rosa"]
    _say(session, rs_en[1]["Ana"], "total benta", 2)
    _night(session, rs_shop)
    rs_shop.pin(8, 0, 1)
    reply = _turn(session, rosa, "Approve")
    label = t("intent.sales_supervisor.sales_today", "en")
    assert reply.text() == t("phrases.proposal.taught", "en", phrase="total benta", action=label)
    (taught,) = session.exec(select(Event).where(Event.action == phrases.TAUGHT)).all()
    assert taught.actor_id == rosa.id and (taught.after or {})["roles"] == ["owner"]
    assert _open(session)[0].status == "approved"
    routed = _turn(session, rosa, "Total benta")
    assert routed.agent_id == SALES.id
    assert t("route.question", "en") not in routed.text()


def test_reject_rests_the_key_for_30_days(
    session: Session, rs_en: Ferinos, rs_shop: Shop, model: list[dict[int, str]]
) -> None:
    rosa, ana = rs_en[1]["Rosa"], rs_en[1]["Ana"]
    _say(session, ana, "total benta", 2)
    _night(session, rs_shop)
    reply = _turn(session, rosa, "Reject")
    assert reply.text() == t("phrases.proposal.rejected", "en", phrase="total benta")
    assert session.exec(select(Event).where(Event.action == proposals.REJECTED)).one()
    assert not session.exec(select(Event).where(Event.action == phrases.TAUGHT)).all()
    for days, made in ((1, 0), (31, 1)):
        rs_shop.pin(10, 0, days)
        _say(session, ana, "total benta", 2)
        assert _night(session, rs_shop, days) == made
    assert len(_open(session)) == 2


def test_a_missing_capability_becomes_a_feature_request(
    monkeypatch: pytest.MonkeyPatch, session: Session, rs_en: Ferinos, rs_shop: Shop,
    model: list[dict[int, str]],
) -> None:  # fmt: skip
    answer = Answer(proposals=[Proposal(message=0, missing="Print a price list")])
    monkeypatch.setattr(proposals, "_fake_answer", lambda m, o: answer)
    _say(session, rs_en[1]["Ana"], "print presyo", 2)
    assert _night(session, rs_shop) == 1
    assert _open(session) == []
    (group,) = features.groups(session)
    assert (group.text, group.failed) == ("Print a price list", ["print presyo"])


def test_the_cap_stops_the_nightly_call(
    session: Session, rs_en: Ferinos, rs_shop: Shop, model: list[dict[int, str]]
) -> None:
    """D49: the proposals count in the report questions' US$10 a month."""
    _spent(session, rs_en[1]["Rosa"], 1000, "USD", dt.datetime(2026, 10, 2, tzinfo=dt.UTC))
    _say(session, rs_en[1]["Ana"], "total benta", 2)
    assert _night(session, rs_shop) == 0 and model == []
    assert session.exec(select(Event).where(Event.action == report_model.CAPPED)).one()


def test_a_clerk_cannot_approve(
    session: Session, rs_en: Ferinos, rs_shop: Shop, model: list[dict[int, str]]
) -> None:
    ana = rs_en[1]["Ana"]
    _say(session, ana, "total benta", 2)
    _night(session, rs_shop)
    (card,) = _open(session)
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(
            session, card.id, Actor.person(ana), "approved", channel="chat", aal="aal1"
        )
    session.rollback()
    _turn(session, ana, "Approve")  # no card in her chat: a normal turn
    session.refresh(card)
    assert card.status == "pending"
    assert not session.exec(select(Event).where(Event.action == phrases.TAUGHT)).all()


def test_the_request_leaves_only_through_egress_with_its_purpose(
    monkeypatch: pytest.MonkeyPatch, session: Session, rs_en: Ferinos, rs_shop: Shop
) -> None:
    _route(monkeypatch, "gateway/report")
    net = Gateway({"proposals": [TODAY]})
    _say(session, rs_en[1]["Rosa"], "Ana total benta", 2)
    with models.override_allow_model_requests(True):
        assert _night(session, rs_shop, transport=httpx.MockTransport(net)) == 1
    (body,) = net.bodies
    assert "Person_" in body and "ana total" not in body.casefold()
    (log,) = session.exec(select(EgressLog)).all()
    assert (log.purpose, log.agent_id) == ("phrases.propose", "phrases")
    (usage,) = session.exec(select(UsageCloudRequest)).all()
    assert usage.task == "phrases.propose"
    ran = session.exec(select(Event).where(Event.action == proposals.RAN)).one()
    assert (ran.after or {})["date"] == RS_TODAY.isoformat()
