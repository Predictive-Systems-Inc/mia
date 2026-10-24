"""A typed answer to Mia's own question fills the missing input (decider.slot_answer): the
owner's "void" then "2" on the phones page got a "Did you mean" because a question asked as
text did not hold the turn and the decider read "2" alone."""

import functools
from typing import Any

import pytest
from sqlmodel import Session

from mia.agents.sales_supervisor import MANIFEST as SS
from mia.agents.shift_supervisor import MANIFEST as SHIFT
from mia.core import jev, orgconfig, sales
from mia.i18n import t
from mia.settings import get_settings
from tests.conftest import Shop
from tests.jev_fake import answers_for, choice, fake_jev
from tests.test_bookkeeper_chat import _turn
from tests.test_data_standard_1_7 import Ferinos
from tests.test_data_standard_1_9 import item
from tests.test_sales_chat import _answers
from tests.test_sales_receipts import _cards, _open_drawer, _paid, _receipts, _scenario, ss_jev

__all__ = ["ss_jev"]  # a fixture


def _seen(monkeypatch: pytest.MonkeyPatch, action: str = "clarify") -> list[dict[str, Any]]:
    """Jev answers `action` from here on; returns the requests it gets."""
    seen: list[dict[str, Any]] = []
    _answers(monkeypatch, action, seen, conversation="other")
    return seen


@pytest.mark.usefixtures("ss_jev")
@pytest.mark.parametrize("answer", ["2", "resibo 2", "#2"])
def test_void_then_the_number_raises_the_void_card(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    _, rows = _scenario(session, rs, monkeypatch)
    _answers(monkeypatch, "void_receipt", conversation="other")
    asked = _turn(session, rs[1]["Ana"], "void")
    assert asked.text() == t("sales.receipt.which_no", "fil")
    seen = _seen(monkeypatch)  # the owner's Jev read "2" alone as a Did you mean
    _turn(session, rs[1]["Ana"], answer, asked.thread_id)
    assert seen == []
    (card,) = _cards(session, sales.VOID)
    assert card.subject_id == rows[1].id


@pytest.mark.usefixtures("ss_jev")
def test_a_message_that_does_not_fill_the_slot_goes_its_own_way(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    _answers(monkeypatch, "void_receipt", conversation="other")
    asked = _turn(session, rs[1]["Ana"], "void")
    seen = _seen(monkeypatch, "sales_today")
    reply = _turn(session, rs[1]["Ana"], "sales today?", asked.thread_id)
    assert len(seen) == 1 and "Mall kiosk" in reply.text()
    assert _cards(session, sales.VOID) == []


@pytest.mark.usefixtures("ss_jev")
def test_after_the_window_a_number_goes_the_normal_way(
    session: Session, rs: Ferinos, rs_shop: Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    rs_shop.pin(10, 0)
    _answers(monkeypatch, "void_receipt", conversation="other")
    asked = _turn(session, rs[1]["Ana"], "void")
    rs_shop.pin(10, 31)
    seen = _seen(monkeypatch, "void_receipt")
    reply = _turn(session, rs[1]["Ana"], "2", asked.thread_id)
    assert len(seen) == 1 and reply.text() == t("sales.receipt.which_no", "fil")
    assert _cards(session, sales.VOID) == []


@pytest.mark.usefixtures("ss_jev")
def test_refund_then_the_number_refunds_the_whole_sale(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No item named: the whole sale, as "refund 2" in one message (the refund rules)."""
    _, rows = _scenario(session, rs, monkeypatch)
    _answers(monkeypatch, "refund_receipt", conversation="other")
    asked = _turn(session, rs[1]["Ana"], "refund")
    assert asked.text() == t("sales.receipt.which_no", "fil")
    seen = _seen(monkeypatch)
    _turn(session, rs[1]["Ana"], "2", asked.thread_id)
    assert seen == []
    (card,) = _cards(session, sales.REFUND)
    assert (card.subject_id, card.evidence["amount"]) == (rows[1].id, rows[1].total)


@pytest.mark.usefixtures("ss_jev")
def test_a_refund_that_named_an_item_is_never_completed_as_the_whole_sale(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ube = item(session, "Ube").id
    _answers(monkeypatch, "refund_receipt", item=ube, conversation="other")
    asked = _turn(session, rs[1]["Ana"], "refund ube")
    assert asked.text() == t("sales.receipt.which_no", "fil")
    seen = _seen(monkeypatch)
    _turn(session, rs[1]["Ana"], "2", asked.thread_id)
    assert len(seen) == 1  # Jev decides, with the question as context
    assert _cards(session, sales.REFUND) == []


@pytest.mark.usefixtures("ss_jev")
def test_a_typed_tender_answers_the_tender_buttons(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_drawer(session, rs, monkeypatch)
    cl, ube = item(session, "Classic").id, item(session, "Ube").id
    _answers(monkeypatch, "record_receipt", item_0=cl, item_1=ube, conversation="other")
    asked = _turn(session, rs[1]["Ana"], "2 cl 1 ube")
    assert asked.blocks[0].text == t("sales.receipt.ask_tender", "fil")  # type: ignore[union-attr]
    seen = _seen(monkeypatch)
    _turn(session, rs[1]["Ana"], "gcash", asked.thread_id)  # the button says "GCash"
    assert seen == []
    (r,) = _receipts(session)
    assert (r.total, _paid(session, r)) == (12_500, [("gcash", 12_500)])


def test_with_two_agents_the_answer_stays_with_the_asking_agent(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The phones page has several agents: the typed answer to a text question is not routed
    (chat.service._pending), the same as a buttoned one."""
    both = orgconfig.load().model_copy(update={"agents": [SHIFT.id, SS.id]})
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: both))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()
    _, rows = _scenario(session, rs, monkeypatch)
    routed: list[dict[str, Any]] = []

    def answer(body: dict[str, Any]) -> dict[str, Any]:
        if "agent" in body["questions"]:
            routed.append(body)
            return {"agent": choice(SS.id)}
        return answers_for(body, "void_receipt", conversation="other")

    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(answer))
    asked = _turn(session, rs[1]["Ana"], "void")
    assert asked.agent_id == SS.id and len(routed) == 1
    reply = _turn(session, rs[1]["Ana"], "2", asked.thread_id)
    assert reply.agent_id == SS.id and len(routed) == 1
    (card,) = _cards(session, sales.VOID)
    assert card.subject_id == rows[1].id
