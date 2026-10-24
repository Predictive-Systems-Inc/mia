"""A person asking what Mia can do gets the help list by code, never a rephrase (the owner's
test, 23 Oct: Berto's "commands?" and "ano kaya mo gawin?")."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from mia.api.main import app
from mia.channels.simulator import SimAdapter
from mia.chat import help_menu
from mia.chat.access import agents_for
from mia.chat.blocks import ChatReply
from mia.chat.service import run_turn
from mia.core import jev
from mia.core.models import Person
from mia.i18n import t
from tests.conftest import Shop
from tests.jev_fake import answers_for, fake_jev
from tests.test_sim_api import answer, shop, sim  # noqa: F401 (fixtures)


def _turn(session: Session, person: Person, text: str) -> ChatReply:
    reply = asyncio.run(run_turn(session, None, person, text))
    session.commit()
    return reply


@pytest.fixture
def no_jev(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Jev on, every request recorded (a help message must make none)."""
    seen: list[dict[str, Any]] = []
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    from mia.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        jev, "_inner", lambda: fake_jev(lambda b: answers_for(b, "clarify", 0.9), seen)
    )
    return seen


def test_the_fixed_list() -> None:
    for text in ("commands?", "Ano kaya mo gawin?", "HELP!", "what can you do", "mitä osaat?"):
        assert help_menu.is_help(text), text
    for text in ("menu", "help me with sp 5", "sales today", "tulong po sa order 5"):
        assert not help_menu.is_help(text), text


def test_bertos_two_messages_answer_with_his_agents_only(
    session: Session, ferinos: tuple[Any, dict[str, Person]], no_jev: list[dict[str, Any]]
) -> None:
    berto = ferinos[1]["Berto"]
    lang = berto.language
    mine = agents_for(session, berto)
    for text in ("commands?", "ano kaya mo gawin?"):
        reply = _turn(session, berto, text)
        lines = reply.text().splitlines()
        assert lines[0] == t("help.title", lang) and lines[-1] == t("help.footer.dev", lang)
        assert lines[1:-1] == [
            f"{t(a.label_key, lang)}: {t(f'help.{a.manifest.id}', lang)}" for a in mine
        ]
    assert no_jev == []


def test_a_clerk_sees_the_sales_and_inventory_lines(
    session: Session, ferinos: tuple[Any, dict[str, Person]], no_jev: list[dict[str, Any]]
) -> None:
    ana = ferinos[1]["Ana"]
    text = _turn(session, ana, "help").text()
    for agent in ("sales_supervisor", "inventory_manager"):
        assert t(f"help.{agent}", ana.language) in text
    assert no_jev == []


def test_required_mode_leaves_teach_out(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    ferinos: tuple[Any, dict[str, Person]],
    no_jev: list[dict[str, Any]],
) -> None:
    from mia.settings import get_settings

    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    ana = ferinos[1]["Ana"]
    assert _turn(session, ana, "help").text().splitlines()[-1] == t("help.footer", ana.language)


def test_menu_alone_still_goes_to_routing(
    session: Session, ferinos: tuple[Any, dict[str, Person]], no_jev: list[dict[str, Any]]
) -> None:
    ana = ferinos[1]["Ana"]
    reply = _turn(session, ana, "menu")
    assert t("help.title", ana.language) not in reply.text() and no_jev


def test_a_customer_phone_keeps_the_customer_services_replies(
    shop: Shop,  # noqa: F811
    sim: SimAdapter,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer(monkeypatch, "hours")
    client = TestClient(app)
    sent = {"address": "639170000188", "text": "help", "name": "Lorna"}
    replies = client.post("/sim/messages", json=sent).json()
    assert replies and all(t("help.title", "fil") not in (r.get("text") or "") for r in replies)
    assert all(t("help.title", "en") not in (r.get("text") or "") for r in replies)
