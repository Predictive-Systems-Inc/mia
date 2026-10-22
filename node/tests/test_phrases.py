"""Teach Mia (spec 2026-10-22-teach-mia-design, phase 1): the phrasebook, its routing, the
decider's taught examples and hint, and learning from "Did you mean" taps."""

import asyncio
import functools
import json
from collections.abc import Callable
from typing import Any

import pytest
from sqlmodel import Session, col, select

from mia.agents import decider
from mia.agents.decider import Alternative, Decision
from mia.chat import phrases
from mia.chat.blocks import ChatReply
from mia.chat.route_memory import key_of
from mia.chat.service import run_turn
from mia.core import jev, orgconfig
from mia.core.models import Actor, Event, Person
from mia.i18n import t
from mia.settings import get_settings
from tests.jev_fake import answers_for, choice, fake_jev

STOCK_SALES = ["inventory_manager", "sales_supervisor"]
UNSURE = {"sales_period": 0.4, "sales_today": 0.35}


class Jev:
    """The fake Jev's state: router requests seen, decider bodies seen, the decider's answer."""

    def __init__(self) -> None:
        self.routed: list[dict[str, Any]] = []
        self.decided: list[dict[str, Any]] = []
        self.answer: Callable[[dict[str, Any]], dict[str, Any]] = lambda b: answers_for(
            b, "sales_today"
        )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, ferinos: tuple[Any, dict[str, Person]]) -> Jev:
    """Ferino's with the inventory manager and the sales supervisor, Jev faked: the router
    picks inventory_manager (so a phrase that routes to sales is visible), deciders answer
    with fake.answer."""
    only = orgconfig.OrgSettings(agents=STOCK_SALES)
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()
    state = Jev()

    def answer(body: dict[str, Any]) -> dict[str, Any]:
        if "agent" in body["questions"]:
            state.routed.append(body)
            return {"agent": choice("sales_supervisor")}
        state.decided.append(body)
        return state.answer(body)

    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(answer))
    return state


def _turn(session: Session, person: Person, text: str, thread: str | None = None) -> ChatReply:
    reply = asyncio.run(run_turn(session, None, person, text, thread))
    session.commit()
    return reply


def _buttons(reply: ChatReply) -> list[str]:
    return [o for b in reply.blocks if b.type == "quick_replies" for o in b.options]


def _rosa(ferinos: tuple[Any, dict[str, Person]]) -> Person:
    return ferinos[1]["Rosa"]


# ---- the phrasebook ------------------------------------------------------------------------


def test_teach_refuses_money_and_unknown_actions(
    session: Session, ferinos: tuple[Any, dict[str, Person]]
) -> None:
    rosa = _rosa(ferinos)
    actor = Actor.person(rosa)
    with pytest.raises(phrases.TeachError, match="cannot be taught"):
        phrases.teach(session, actor, None, "kansel", "sales_supervisor", "void_receipt")
    with pytest.raises(phrases.TeachError, match="cannot be taught"):
        phrases.teach(session, actor, None, "balik", "sales_supervisor", "refund_receipt")
    with pytest.raises(phrases.TeachError, match="no action"):
        phrases.teach(session, actor, None, "x", "sales_supervisor", "launch_rockets")
    assert "void_receipt" not in phrases.teachable("sales_supervisor")
    assert "sales_today" in phrases.teachable("sales_supervisor")
    assert not session.exec(select(Event).where(Event.action == phrases.TAUGHT)).all()


def test_the_fold_teaches_retires_and_counts_the_version(
    session: Session, ferinos: tuple[Any, dict[str, Person]]
) -> None:
    rosa = _rosa(ferinos)
    branch = rosa.branch_id
    actor = Actor.person(rosa)
    assert phrases.phrasebook(session, branch) == (0, {})
    phrases.teach(session, actor, None, "Total benta 12?", "sales_supervisor", "sales_today")
    version, book = phrases.phrasebook(session, branch)
    assert version == 1 and book == {"total benta #": ("sales_supervisor", "sales_today")}
    assert phrases.phrasebook(session, "other-branch")[1] == book  # None: every branch
    phrases.retire(session, actor, None, "total benta 3")
    assert phrases.phrasebook(session, branch) == (2, {})


def test_a_read_tool_that_declares_writes_is_never_picked_by_a_phrase() -> None:
    """hr_officer's my_payslip runs resend_payslip: risk read, but it sends a message."""
    assert "my_payslip" in phrases.teachable("hr_officer")
    assert "my_payslip" not in phrases.reads("hr_officer")
    assert "sales_today" in phrases.reads("sales_supervisor")


def test_an_old_bare_number_key_is_dropped_by_the_fold(
    session: Session, ferinos: tuple[Any, dict[str, Person]]
) -> None:
    """A "#" tap written before keys needed a letter never becomes a phrase."""
    from mia.core import events

    rosa = _rosa(ferinos)
    after = {"key": "#", "agent_id": "sales_supervisor", "action": "sales_today"}
    events.emit(session, phrases.CONFIRMED, ("person", rosa.id), None, after, Actor.person(rosa))
    assert phrases.phrasebook(session, rosa.branch_id)[1] == {}


# ---- routing and deciding ------------------------------------------------------------------


def test_a_taught_phrase_routes_without_jev_also_with_another_agent_active(
    session: Session, ferinos: tuple[Any, dict[str, Person]], fake: Jev
) -> None:
    """Rosa's "sales today?" taught to sales_today answers at once, with no router request,
    even right after the inventory manager answered; the decision records the version."""
    rosa = _rosa(ferinos)
    phrases.teach(
        session,
        Actor.person(rosa),
        rosa.branch_id,
        "sales today?",
        "sales_supervisor",
        "sales_today",
    )
    from mia.chat.channels import notify

    note = notify(session, rosa, [], Actor.system(rosa.branch_id), "inventory_manager")
    session.commit()
    reply = _turn(session, rosa, "Sales today", note.thread_id)
    assert fake.routed == [] and reply.agent_id == "sales_supervisor"
    assert "Mall kiosk" in reply.text()
    switched = session.exec(select(Event).where(Event.action == "chat.agent_switched")).all()
    assert [(e.after or {})["to"] for e in switched] == ["sales_supervisor"]
    made = session.exec(select(Event).where(Event.action == "decision.made")).all()
    assert (made[-1].after or {})["phrasebook_version"] == 1


def test_a_retired_phrase_stops_routing(
    session: Session, ferinos: tuple[Any, dict[str, Person]], fake: Jev
) -> None:
    rosa = _rosa(ferinos)
    actor = Actor.person(rosa)
    phrases.teach(session, actor, None, "sales today?", "sales_supervisor", "sales_today")
    phrases.retire(session, actor, None, "sales today?")
    _turn(session, rosa, "sales today?")
    assert len(fake.routed) == 1


def test_taught_examples_reach_the_decider_option_text(
    session: Session, ferinos: tuple[Any, dict[str, Person]], fake: Jev
) -> None:
    """Only an owner's or admin's taught phrase of at most 60 characters is an example; a
    clerk's teach, a long one and a tapped phrase never are (H3)."""
    rosa, ana = _rosa(ferinos), ferinos[1]["Ana"]
    owner = Actor.person(rosa)
    phrases.teach(
        session, owner, None, "kumusta benta", "sales_supervisor", "sales_today", roles=["owner"]
    )
    phrases.teach(
        session, Actor.person(ana), None, "benta ng clerk", "sales_supervisor", "sales_today",
        roles=["clerk"],
    )  # fmt: skip
    long = "ano na ang benta natin ngayong araw sa lahat ng mga kiosk po ba"
    phrases.teach(session, owner, None, long, "sales_supervisor", "sales_today", roles=["owner"])
    from mia.core import events

    tap = {"key": "tapped benta", "agent_id": "sales_supervisor", "action": "sales_today"}
    events.emit(session, phrases.CONFIRMED, ("phrase", "tapped benta"), None, tap, owner)
    session.commit()
    _turn(session, rosa, "kumusta benta")
    criteria = fake.decided[-1]["questions"]["action"]["criteria"]
    assert '"kumusta benta"' in criteria["sales_today"]
    assert "taught" not in criteria["sales_period"]
    sent = json.dumps(fake.decided[-1])
    assert "benta ng clerk" not in sent and "lahat ng mga kiosk" not in sent
    assert "tapped benta" not in sent


def test_honour_takes_the_taught_action_only_when_jev_was_unsure() -> None:
    alts = [Alternative(action="sales_today", args={"x": 1}, probability=0.35)]
    unsure = Decision(
        action="clarify", confidence=0.4, raw_action="sales_period", alternatives=alts
    )
    taken = decider.honour(unsure, "sales_today")
    assert taken.action == "sales_today" and taken.args == {"x": 1}
    guarded = unsure.model_copy(update={"confidence": 0.9})  # an agent's guard asked
    assert decider.honour(guarded, "sales_today").action == "clarify"
    missing = unsure.model_copy(update={"missing": "item_0"})
    assert decider.honour(missing, "sales_today").action == "clarify"
    assert decider.honour(unsure, "sales_period").action == "clarify"  # not an alternative
    assert decider.honour(unsure, None) is unsure
    flagged = unsure.model_copy(update={"guarded": True})
    assert decider.honour(flagged, "sales_today") is flagged


def test_a_phrase_never_picks_a_write(
    session: Session, ferinos: tuple[Any, dict[str, Person]], fake: Jev
) -> None:
    """A tapped report_sales phrase plus Jev unsure with confident counts still asks (H1):
    the phrase only routes; a write keeps its Did you mean."""
    rosa = _rosa(ferinos)
    actor = Actor.person(rosa)
    from mia.core import events

    tap = {"key": "ube # pan #", "agent_id": "sales_supervisor", "action": "report_sales"}
    events.emit(session, phrases.CONFIRMED, ("phrase", "ube # pan #"), None, tap, actor)
    session.commit()
    assert phrases.phrasebook(session, rosa.branch_id)[1]["ube # pan #"][1] == "report_sales"
    probabilities = {"report_sales": 0.45, "sales_today": 0.3}
    fake.answer = lambda b: answers_for(b, "report_sales", 0.45, probabilities)
    reply = _turn(session, rosa, "ube 2 pan 7?")
    assert _buttons(reply)
    made = session.exec(select(Event).where(Event.action == "decision.made")).all()
    assert (made[-1].after or {})["action"] == "clarify"
    assert "report_sales" not in phrases.reads("sales_supervisor")


# ---- learning from "Did you mean" taps -----------------------------------------------------


def _unsure(body: dict[str, Any]) -> dict[str, Any]:
    return answers_for(body, "sales_period", 0.4, UNSURE)


def test_a_did_you_mean_tap_is_learned_and_unlearned(
    session: Session, ferinos: tuple[Any, dict[str, Person]], fake: Jev
) -> None:
    """The owner, 22 Oct: "total benta" asked Did you mean; the tap on Sales today answers and
    is confirmed; the next "total benta" goes straight to sales_today; a tap on another action
    for the key drops the confidence to 0 and the question comes back."""
    rosa = _rosa(ferinos)
    lang = rosa.language
    today, period = (
        t(f"intent.sales_supervisor.{a}", lang) for a in ("sales_today", "sales_period")
    )
    fake.answer = _unsure
    asked = _turn(session, rosa, "total benta")
    assert today in _buttons(asked)
    tapped = _turn(session, rosa, today, asked.thread_id)
    assert "Mall kiosk" in tapped.text()
    confirmed = session.exec(select(Event).where(Event.action == phrases.CONFIRMED)).all()
    assert [(e.after or {})["key"] for e in confirmed] == ["total benta"]
    assert (confirmed[0].after or {})["action"] == "sales_today"
    routed = len(fake.routed)
    again = _turn(session, rosa, "Total benta")  # a new thread: a tapped phrase routes
    assert len(fake.routed) == routed and not _buttons(again) and "Mall kiosk" in again.text()
    entry = phrases.entries(session, rosa.branch_id)[0]
    assert (entry.confidence, entry.taps, entry.taught) == (1, 1, False)
    # another action for the same key: Jev offers only sales_period this time
    fake.answer = lambda b: answers_for(b, "sales_period", 0.4, {"sales_period": 0.4})
    other = _turn(session, rosa, "total benta")
    assert period in _buttons(other)
    _turn(session, rosa, period, other.thread_id)
    assert phrases.phrasebook(session, rosa.branch_id)[1] == {}
    fake.answer = _unsure
    back = _turn(session, rosa, "total benta")
    assert today in _buttons(back)


def test_numbers_share_the_learned_key(
    session: Session, ferinos: tuple[Any, dict[str, Person]], fake: Jev
) -> None:
    rosa = _rosa(ferinos)
    fake.answer = _unsure
    today = t("intent.sales_supervisor.sales_today", rosa.language)
    asked = _turn(session, rosa, "total benta 2")
    _turn(session, rosa, today, asked.thread_id)
    again = _turn(session, rosa, "total benta 5")
    assert not _buttons(again) and key_of("total benta 5") == "total benta #"


def test_something_else_learns_nothing(
    session: Session, ferinos: tuple[Any, dict[str, Person]], fake: Jev
) -> None:
    rosa = _rosa(ferinos)
    fake.answer = _unsure
    asked = _turn(session, rosa, "total benta")
    _turn(session, rosa, t("clarify.something_else", rosa.language), asked.thread_id)
    assert not session.exec(select(Event).where(Event.action == phrases.CONFIRMED)).all()


def test_a_tap_on_a_money_action_is_never_learned(
    session: Session, ferinos: tuple[Any, dict[str, Person]]
) -> None:
    """A confirmation of an untaught action whose tool risks money stays out of the book."""
    from mia.core import events

    rosa = _rosa(ferinos)
    after = {"key": "kansel", "agent_id": "sales_supervisor", "action": "void_receipt"}
    events.emit(session, phrases.CONFIRMED, ("phrase", "kansel"), None, after, Actor.person(rosa))
    session.commit()
    assert phrases.phrasebook(session, rosa.branch_id)[1] == {}


def test_a_taught_phrase_outranks_taps(
    session: Session, ferinos: tuple[Any, dict[str, Person]]
) -> None:
    from mia.core import events

    rosa = _rosa(ferinos)
    actor = Actor.person(rosa)
    after = {"key": "benta", "agent_id": "sales_supervisor", "action": "sales_period"}
    for _ in range(3):
        events.emit(session, phrases.CONFIRMED, ("phrase", "benta"), None, after, actor)
    phrases.teach(session, actor, rosa.branch_id, "benta", "sales_supervisor", "sales_today")
    assert phrases.phrasebook(session, rosa.branch_id)[1]["benta"][1] == "sales_today"
    ids = session.exec(select(Event.id).where(col(Event.action).in_(phrases.ALL))).all()
    assert phrases.version(session, rosa.branch_id) == len(ids) == 4


# ---- review round 1 ------------------------------------------------------------------------


def test_a_bare_number_is_never_a_phrase(
    session: Session, ferinos: tuple[Any, dict[str, Person]], fake: Jev
) -> None:
    """ "12" asked Did you mean and the tap answers, but key "#" is never learned or taught."""
    rosa = _rosa(ferinos)
    with pytest.raises(phrases.TeachError):
        phrases.teach(session, Actor.person(rosa), None, "12", "sales_supervisor", "sales_today")
    fake.answer = _unsure
    asked = _turn(session, rosa, "12")
    today = t("intent.sales_supervisor.sales_today", rosa.language)
    assert today in _buttons(asked)
    _turn(session, rosa, today, asked.thread_id)
    assert not session.exec(select(Event).where(Event.action == phrases.CONFIRMED)).all()


def test_a_tapped_phrase_never_switches_an_active_agent(
    session: Session, ferinos: tuple[Any, dict[str, Person]], fake: Jev
) -> None:
    """A learned (tapped) phrase routes only when no agent is active (H4); taught ones may."""
    from mia.chat.channels import notify
    from mia.core import events

    rosa = _rosa(ferinos)
    tap = {"key": "stock benta", "agent_id": "sales_supervisor", "action": "sales_today"}
    events.emit(
        session, phrases.CONFIRMED, ("phrase", "stock benta"), None, tap, Actor.person(rosa)
    )
    note = notify(session, rosa, [], Actor.system(rosa.branch_id), "inventory_manager")
    session.commit()
    _turn(session, rosa, "stock benta", note.thread_id)
    assert len(fake.routed) == 1  # Jev routed it: the tap did not switch the live agent
    fresh = _turn(session, rosa, "stock benta")  # a new thread, no agent active
    assert len(fake.routed) == 1 and fresh.agent_id == "sales_supervisor"


def test_the_version_counts_the_branchs_events_only(
    session: Session, ferinos: tuple[Any, dict[str, Person]]
) -> None:
    from mia.core import events

    rosa = _rosa(ferinos)
    other = Actor.system("another-branch")
    tap = {"key": "benta", "agent_id": "sales_supervisor", "action": "sales_today"}
    events.emit(session, phrases.CONFIRMED, ("phrase", "benta"), None, tap, other)
    session.commit()
    assert phrases.version(session, rosa.branch_id) == 0
    assert phrases.version(session, "another-branch") == 1


def test_pagsira_stays_a_question_after_a_tap(
    session: Session, bk: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bookkeeper's cash count or expense guard (H2): a tap on its Cash count is not a
    licence; the next "pagsira 800" with Jev unsure asks again and writes nothing."""
    from mia.agents.bookkeeper import MANIFEST
    from mia.agents.bookkeeper.models import CashCount, Expense
    from mia.core import people

    only = orgconfig.load().model_copy(update={"agents": [MANIFEST.id]})
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()
    probabilities = {"expense": 0.55, "cash_count": 0.4}
    monkeypatch.setattr(
        jev,
        "_inner",
        lambda: fake_jev(
            lambda b: answers_for(
                b, "expense", 0.55, probabilities, amount="p0", category="repairs"
            )
        ),
    )
    marites = people.set_language(session, Actor.system(bk[0].id), bk[1]["Marites"], "war")
    session.commit()
    asked = _turn(session, marites, "pagsira 500")
    count = t("intent.bookkeeper.cash_count", "war")
    assert count in _buttons(asked)
    _turn(session, marites, count, asked.thread_id)
    again = _turn(session, marites, "pagsira 800")
    assert _buttons(again)
    assert session.exec(select(CashCount).where(CashCount.counted == 80_000)).all() == []
    assert session.exec(select(Expense).where(Expense.amount == 80_000)).all() == []
