"""The sales supervisor's item codes read: each active item of the sender's kiosk in menu order
with its short codes and today's dated price, asked in the chat and routed to from another
agent ("send me list of item codes" had no answer)."""

import asyncio
import functools
from typing import Any

import pytest
from sqlmodel import Session, select

from mia.agents.registry import AGENTS
from mia.agents.sales_supervisor import tools
from mia.chat import agent_router
from mia.chat.blocks import ChatReply
from mia.chat.service import run_turn
from mia.core import jev, orgconfig, people
from mia.core.models import Actor, Branch, Person
from mia.settings import get_settings
from tests.jev_fake import answers_for, choice, fake_jev
from tests.test_sales_tools import deps_for

Ferinos = tuple[Branch, dict[str, Person]]
ASKED = "send me list of item codes"
# The seed's menu in order; the Mall kiosk runs a price experiment on Special (49.50 today).
MALL = [
    "Special: sp, special ₱49.50",
    "Classic: cl, classic, bibingka ₱40.00",
    "Ube: ube, ub ₱45.00",
    "Salted egg: se, salted ₱50.00",
    "Cheese overload: co, overload ₱55.00",
    "Puto bumbong: pb ₱35.00",
    "Box of 4: b4, box ₱160.00",
    "Kape: kape, coffee ₱25.00",
]


def _english(session: Session, kiosk: Branch) -> dict[str, Person]:
    for person in session.exec(select(Person)).all():
        people.set_language(session, Actor.system(kiosk.id), person, "en")
    session.commit()
    return {p.name.split()[0]: p for p in session.exec(select(Person)).all()}


def _jev(monkeypatch: pytest.MonkeyPatch, agents: list[str]) -> None:
    only = orgconfig.OrgSettings(agents=agents)
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()


def _sales_answers(body: dict[str, Any]) -> dict[str, Any]:
    """The sales supervisor's Jev picks item_codes (a choice, or its yes under the nouls)."""
    return answers_for(body, "item_codes", is_item_codes=0.95)


def _turn(session: Session, person: Person, text: str) -> ChatReply:
    reply = asyncio.run(run_turn(session, None, person, text, None))
    session.commit()
    return reply


def _lines(out: tools.ItemCodesOutput) -> list[str]:
    from mia.agents.sales_supervisor import replies

    text = replies.tool_reply("item_codes", out.model_dump(mode="json"), {}, "en")[0]
    return text.text.splitlines()[1:]  # type: ignore[union-attr]


def test_the_mall_kiosk_lists_its_items_codes_and_todays_prices(
    session: Session, ferinos: Ferinos
) -> None:
    kiosk, _ = ferinos
    ana = _english(session, kiosk)["Ana"]
    out = tools.item_codes(deps_for(session, ana), tools.ItemCodesInput(), "c1")
    assert out.branch == "Mall kiosk"
    assert (out.items[0].item, out.items[0].codes, out.items[0].price) == (
        "Special",
        ["sp", "special"],
        4950,
    )
    assert _lines(out) == MALL


def test_a_street_stall_clerk_gets_the_street_stalls_prices(
    session: Session, ferinos: Ferinos
) -> None:
    kiosk, _ = ferinos
    pao = _english(session, kiosk)["Pao"]
    out = tools.item_codes(deps_for(session, pao), tools.ItemCodesInput(), "c1")
    assert out.branch == "Street stall"
    assert _lines(out) == ["Special: sp, special ₱45.00", *MALL[1:]]  # no experiment there


def test_the_chat_answers_send_me_list_of_item_codes(
    session: Session, ferinos: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    kiosk, _ = ferinos
    ana = _english(session, kiosk)["Ana"]
    _jev(monkeypatch, ["sales_supervisor"])
    for mode in ("choice", "nouls"):
        monkeypatch.setenv("MIA_SALES_QUESTION", mode)
        get_settings.cache_clear()
        monkeypatch.setattr(jev, "_inner", lambda: fake_jev(_sales_answers))
        text = _turn(session, ana, ASKED).text()
        assert "Mall kiosk" in text and all(line in text for line in MALL), (mode, text)


def test_the_router_sends_item_codes_to_the_sales_supervisor(
    session: Session, ferinos: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fake router that picks the agent whose description names item codes, as Jev reads it;
    unclear and unsure without one."""
    kiosk, _ = ferinos
    marites = _english(session, kiosk)["Marites"]
    _jev(monkeypatch, ["shift_supervisor", "sales_supervisor"])
    body = agent_router.build_request(ASKED, list(AGENTS.values()), None, "", "m")
    assert "item codes" in body["questions"]["agent"]["criteria"]["sales_supervisor"]

    def answer(body: dict[str, Any]) -> dict[str, Any]:
        if "agent" not in body["questions"]:
            return _sales_answers(body)
        named = [a for a, d in body["questions"]["agent"]["criteria"].items() if "item codes" in d]
        return {"agent": choice(named[0], 0.95) if named else choice("unclear", 0.4)}

    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(answer))
    reply = _turn(session, marites, ASKED)
    assert reply.agent_id == "sales_supervisor" and MALL[0] in reply.text()
