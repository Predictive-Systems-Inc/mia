"""The branch manager's people tools (Q117): an admin adds a user (roles clerk, staff, supervisor
or admin, never owner) with the invite, or links a Philippine mobile number to a person; the
number is redacted in every event of the call and shown by its last four digits. The account
takeover guard: never the owner's number, an admin's only for the owner, never a second one."""

import asyncio
import functools
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session, select

from mia.agents.base import call_tool
from mia.agents.branch_manager import MANIFEST, tools
from mia.agents.branch_manager.tools import AddPersonInput, SetPhoneInput
from mia.api.main import app
from mia.channels import linking, registry
from mia.channels.simulator import SimAdapter
from mia.chat.service import run_turn
from mia.core import jev, orgconfig, people
from mia.core.db import utcnow
from mia.core.models import (
    Actor,
    AuthCode,
    Branch,
    ChannelIdentity,
    ChannelInbound,
    Event,
    Message,
    Person,
    Thread,
)
from mia.i18n import t
from mia.settings import get_settings
from tests.channels.kits import _hub_sign
from tests.conftest import Shop
from tests.jev_fake import answers_for, fake_jev
from tests.test_branch_manager_tools import deps_for

Ferinos = tuple[Branch, dict[str, Person]]
ADD = {b.tool_id: b for b in tools.BINDINGS}[f"{MANIFEST.id}.add_person"]
SET = {b.tool_id: b for b in tools.BINDINGS}[f"{MANIFEST.id}.set_phone"]
TYPED = "0917 123 4567"
ADDRESS = "639171234567"
DIGITS = ("9171234567", "917 123", "1234567")


def _admin(session: Session, kiosk: Branch, name: str = "Dina", lang: str = "en") -> Person:
    actor = Actor.system(kiosk.id)
    admin = people.add_person(
        session, actor, branch_id=kiosk.id, name=name, roles=["admin"], language=lang
    )
    session.commit()
    return admin


def _people_named(session: Session, name: str) -> list[Person]:
    return list(session.exec(select(Person).where(Person.name == name)))


def _no_digits_in_events(session: Session) -> None:
    for e in session.exec(select(Event)):
        text = json.dumps([e.before, e.after])
        assert not any(d in text for d in DIGITS), e.action


# ---- the number --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "address"),
    [
        ("09171234567", ADDRESS),
        ("+63 917 123 4567", ADDRESS),
        ("639171234567", ADDRESS),
        ("917-123-4567", ADDRESS),
        ("0817 123 4567", None),  # a landline shape
        ("0917 123 456", None),
        ("0917 ABC 4567", None),
        ("+1 917 123 4567", None),
    ],
)
def test_a_ph_mobile_is_normalised_to_e164_digits(typed: str, address: str | None) -> None:
    assert linking.ph_mobile(typed) == address


# ---- add_person --------------------------------------------------------------------------


def test_an_admin_adds_a_clerk_with_the_invite(session: Session, bm: Ferinos) -> None:
    kiosk, _ = bm
    deps = deps_for(session, _admin(session, kiosk))
    args = AddPersonInput(name="Maria", role="clerk")
    out = call_tool(deps, ADD, args, "a1")
    (maria,) = _people_named(session, "Maria")
    assert (maria.roles, maria.branch_id, maria.language) == (["clerk"], kiosk.id, "fil")
    assert out["person_id"] == maria.id and out["invite_code"]
    created = session.exec(select(Event).where(Event.action == "person.created")).all()
    assert maria.id in {e.entity_id for e in created}
    code = session.exec(select(AuthCode).where(AuthCode.person_id == maria.id)).one()
    assert (
        code.purpose == "invite" and code.created_by == deps.person.id
    )  # the admin, not the agent
    logged = session.exec(select(Event).where(Event.tool_call_id == "a1")).all()
    called = next(e for e in logged if e.action == "tool.called")
    assert called.after and called.after["output"]["invite_code"] == "<redacted>"
    assert linking.redeem(session, "whatsapp", "639981112222", out["invite_code"], utcnow())


def test_the_admin_adds_at_the_commissary_with_a_phone(session: Session, bm: Ferinos) -> None:
    kiosk, _ = bm
    commissary = session.exec(select(Branch).where(Branch.name == "Commissary")).one()
    deps = deps_for(session, _admin(session, kiosk))
    args = AddPersonInput(name="Ben", role="staff", branch_id=commissary.id, phone=TYPED)
    out = call_tool(deps, ADD, args, "a1")
    (ben,) = _people_named(session, "Ben")
    assert ben.branch_id == commissary.id and out["invite_code"] is None
    identity = linking.identity_for(session, "whatsapp", ADDRESS)
    assert identity is not None and identity.person_id == ben.id
    tools_out = tools.PersonOut.model_validate(
        tools.add_person(deps, AddPersonInput(name="Cy", role="clerk", phone="09981112222"), "a2")
    )
    assert tools_out.phone_last4 == "2222"
    _no_digits_in_events(session)


def test_a_supervisor_may_not_add_a_person(session: Session, bm: Ferinos) -> None:
    out = call_tool(
        deps_for(session, bm[1]["Marites"]), ADD, AddPersonInput(name="X", role="clerk"), "a1"
    )
    assert out["status"] == "denied" and _people_named(session, "X") == []


def test_a_duplicate_name_in_the_branch_is_refused(session: Session, bm: Ferinos) -> None:
    deps = deps_for(session, _admin(session, bm[0]))
    out = call_tool(deps, ADD, AddPersonInput(name="ana", role="clerk"), "a1")
    assert (out["status"], out["message"]) == ("invalid", "person_exists")
    assert len(session.exec(select(Person).where(Person.name == "Ana")).all()) <= 1


@pytest.mark.parametrize("role", ["owner", "accountant", "viewer"])
def test_owner_is_never_assignable(role: str) -> None:
    with pytest.raises(ValidationError):
        AddPersonInput(name="X", role=role)  # type: ignore[arg-type]


@pytest.mark.parametrize("phone", [None, TYPED])
def test_only_the_owner_adds_an_admin(session: Session, bm: Ferinos, phone: str | None) -> None:
    """An admin adding an admin is refused with no hint (no_person); clerks, staff and
    supervisors stay theirs to add."""
    kiosk, ppl = bm
    admin = deps_for(session, _admin(session, kiosk))
    args = AddPersonInput(name="Eve", role="admin", phone=phone)
    out = call_tool(admin, ADD, args, "a1")
    assert (out["message"], _people_named(session, "Eve")) == ("no_person", [])
    for i, role in enumerate(("clerk", "staff", "supervisor")):
        add = AddPersonInput(name=f"New{i}", role=role)  # type: ignore[arg-type]
        assert call_tool(admin, ADD, add, f"b{i}")["role"] == role
    assert call_tool(deps_for(session, ppl["Rosa"]), ADD, args, "a2")["role"] == "admin"


def _notices(session: Session, person: Person) -> list[str]:
    stmt = select(Message).join(Thread).where(Thread.person_id == person.id)
    return [m.text for m in session.exec(stmt.where(Message.role == "notification"))]


def test_the_owner_is_told_of_a_person_and_a_link_made_in_the_chat(
    session: Session, bm: Ferinos
) -> None:
    kiosk, ppl = bm
    dina = _admin(session, kiosk)
    admin = deps_for(session, dina)
    call_tool(admin, ADD, AddPersonInput(name="Maria", role="clerk"), "a1")
    call_tool(admin, SET, SetPhoneInput(person_id=ppl["Liza"].id, phone=TYPED), "s1")
    rosa = ppl["Rosa"]
    added = t("bm.person.owner_added", rosa.language, actor="Dina", name="Maria", role="clerk",
              branch=kiosk.name)  # fmt: skip
    linked = t("bm.person.owner_linked", rosa.language, actor="Dina", name=ppl["Liza"].name,
               last4="4567")  # fmt: skip
    assert _notices(session, rosa) == [added, linked]
    assert _notices(session, dina) == []  # the sender is not told of their own act
    before = len(_notices(session, rosa))
    call_tool(deps_for(session, rosa), ADD, AddPersonInput(name="Ben", role="clerk"), "a2")
    assert len(_notices(session, rosa)) == before  # nor is the owner of their own
    _no_digits_in_events(session)


def test_the_admin_is_told_when_their_invite_meets_a_number_someone_holds(
    session: Session, bm: Ferinos
) -> None:
    kiosk, ppl = bm
    dina = _admin(session, kiosk)
    admin = deps_for(session, dina)
    call_tool(admin, SET, SetPhoneInput(person_id=ppl["Liza"].id, phone=TYPED), "s1")
    out = call_tool(admin, ADD, AddPersonInput(name="Maria", role="clerk"), "a1")
    result = linking.redeem(session, "whatsapp", ADDRESS, out["invite_code"], utcnow())
    assert result.status == "taken"
    assert _notices(session, dina) == [t("channel.link_taken", dina.language, name="Maria")]


def test_a_direct_link_revokes_the_open_invite(session: Session, bm: Ferinos) -> None:
    kiosk, _ = bm
    admin = deps_for(session, _admin(session, kiosk))
    out = call_tool(admin, ADD, AddPersonInput(name="Maria", role="clerk"), "a1")
    (maria,) = _people_named(session, "Maria")
    call_tool(admin, SET, SetPhoneInput(person_id=maria.id, phone=TYPED), "s1")
    late = linking.redeem(session, "whatsapp", "639981112222", out["invite_code"], utcnow())
    assert (
        late.status == "invalid"
    )  # a different number than the linked one: the guard answers first
    assert linking.identity_for(session, "whatsapp", "639981112222") is None
    (code,) = session.exec(select(AuthCode).where(AuthCode.person_id == maria.id)).all()
    assert code.expires_at == code.created_at and code.used_at is None
    revoked = session.exec(select(Event).where(Event.action == "auth.code_revoked")).all()
    assert [e.entity_id for e in revoked] == [code.id]


def test_a_code_never_links_a_second_whatsapp_number(session: Session, bm: Ferinos) -> None:
    kiosk, ppl = bm
    admin = deps_for(session, _admin(session, kiosk))
    call_tool(admin, SET, SetPhoneInput(person_id=ppl["Liza"].id, phone=TYPED), "s1")
    code = linking.create_code(session, Actor.system(kiosk.id), ppl["Liza"], "self")
    second = linking.redeem(session, "whatsapp", "639981112222", code, utcnow())
    assert second.status == "invalid"
    assert linking.identity_for(session, "whatsapp", "639981112222") is None


# ---- set_phone ---------------------------------------------------------------------------


def test_an_admin_links_a_clerks_number_and_a_clerk_may_not(session: Session, bm: Ferinos) -> None:
    kiosk, ppl = bm
    admin = deps_for(session, _admin(session, kiosk))
    refused = call_tool(
        deps_for(session, ppl["Ana"]),
        SET,
        SetPhoneInput(person_id=ppl["Liza"].id, phone=TYPED),
        "s0",
    )
    assert refused["status"] == "denied"
    out = call_tool(admin, SET, SetPhoneInput(person_id=ppl["Ana"].id, phone=TYPED), "s1")
    assert out["phone_last4"] == "4567"
    identity = linking.identity_for(session, "whatsapp", ADDRESS)
    assert identity is not None and identity.person_id == ppl["Ana"].id
    _no_digits_in_events(session)


def test_a_number_held_by_someone_else_is_never_relinked(session: Session, bm: Ferinos) -> None:
    kiosk, ppl = bm
    admin = deps_for(session, _admin(session, kiosk))
    call_tool(admin, SET, SetPhoneInput(person_id=ppl["Ana"].id, phone=TYPED), "s1")
    out = call_tool(admin, SET, SetPhoneInput(person_id=ppl["Liza"].id, phone=TYPED), "s2")
    assert out["message"] == "phone_taken"
    second = call_tool(
        admin, SET, SetPhoneInput(person_id=ppl["Ana"].id, phone="09981112222"), "s3"
    )
    assert second["message"] == "phone_set"  # a second number: no silent replace
    rows = session.exec(select(ChannelIdentity)).all()
    assert [(r.person_id, r.address) for r in rows] == [(ppl["Ana"].id, ADDRESS)]
    _no_digits_in_events(session)


def test_an_invalid_number_is_refused(session: Session, bm: Ferinos) -> None:
    admin = deps_for(session, _admin(session, bm[0]))
    out = call_tool(admin, SET, SetPhoneInput(person_id=bm[1]["Ana"].id, phone="12345"), "s1")
    assert out["message"] == "phone_invalid"


def test_takeover_guard_owner_never_admin_only_by_the_owner(session: Session, bm: Ferinos) -> None:
    kiosk, ppl = bm
    admin = deps_for(session, _admin(session, kiosk))
    other = _admin(session, kiosk, "Fe")
    for target in (ppl["Rosa"], other):
        out = call_tool(admin, SET, SetPhoneInput(person_id=target.id, phone=TYPED), "s1")
        assert out["message"] == "no_person"  # never a hint
    assert session.exec(select(ChannelIdentity)).all() == []
    rosa = deps_for(session, ppl["Rosa"])
    assert call_tool(rosa, SET, SetPhoneInput(person_id=other.id, phone=TYPED), "s2")["phone_last4"]
    _no_digits_in_events(session)


# ---- the sim channel ---------------------------------------------------------------------


@pytest.fixture
def sim(monkeypatch: pytest.MonkeyPatch, bm_shop: Shop) -> Iterator[SimAdapter]:
    adapter = SimAdapter()
    saved = dict(registry._adapters)
    registry._adapters.clear()
    registry.register(adapter)
    org = orgconfig.load().model_copy(
        update={"channels": {"sim": orgconfig.ChannelConfig(enabled=True)}}
    )
    monkeypatch.setattr(orgconfig, "load", lambda org_name=None: org)
    yield adapter
    registry._adapters.clear()
    registry._adapters.update(saved)


def test_a_linked_number_acts_as_the_person_on_the_sim_channel(
    session: Session, bm: Ferinos, sim: SimAdapter
) -> None:
    kiosk, ppl = bm
    admin = deps_for(session, _admin(session, kiosk))
    call_tool(admin, SET, SetPhoneInput(person_id=ppl["Liza"].id, phone=TYPED), "s1")
    session.commit()
    body = json.dumps(
        {"messages": [{"from": ADDRESS, "id": "m1", "text": "hi", "button": None, "media": False}]}
    ).encode()
    client = TestClient(app, client=("127.0.0.1", 50000))
    posted = client.post("/channels/sim/webhook", content=body, headers=_hub_sign(sim.secret)(body))
    assert posted.status_code == 200
    row = session.exec(select(ChannelInbound)).one()
    assert row.person_id == ppl["Liza"].id


# ---- chat --------------------------------------------------------------------------------


@pytest.fixture
def jev_on(monkeypatch: pytest.MonkeyPatch, bm_shop: Shop) -> None:
    only = orgconfig.load().model_copy(update={"agents": [MANIFEST.id]})
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()


def _answers(
    monkeypatch: pytest.MonkeyPatch, action: str, seen: list[dict[str, Any]], **slots: Any
) -> None:
    monkeypatch.setattr(
        jev, "_inner", lambda: fake_jev(lambda b: answers_for(b, action, **slots), seen)
    )


def _turn(session: Session, person: Person, text: str) -> str:
    reply = asyncio.run(run_turn(session, None, person, text, None))
    session.commit()
    return reply.text()


@pytest.mark.parametrize(
    ("text", "lang"),
    [("add user maria clerk mall", "en"), ("idagdag si maria clerk sa mall", "fil")],
)
def test_an_admin_adds_a_user_from_the_chat(
    session: Session,
    bm: Ferinos,
    jev_on: None,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    lang: str,
) -> None:
    kiosk, _ = bm
    admin = _admin(session, kiosk, lang=lang)
    seen: list[dict[str, Any]] = []
    _answers(monkeypatch, "add_person", seen, new_name="n0", role="clerk", branch=kiosk.id)
    reply = _turn(session, admin, text)
    assert seen[0]["state"]["names"] == ["Maria"]
    (maria,) = _people_named(session, "Maria")
    assert (maria.roles, maria.branch_id) == (["clerk"], kiosk.id)
    assert reply.startswith(
        t("bm.person.added", lang, name="Maria", role="clerk", branch=kiosk.name)
    )
    assert "LINK " in reply
    print(f"\n[{lang}] {text!r} -> {reply!r}")


def test_a_missing_role_asks(
    session: Session, bm: Ferinos, jev_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = _admin(session, bm[0])
    _answers(monkeypatch, "add_person", [], new_name="n0")
    assert _turn(session, admin, "add user maria") == t("bm.person.ask_role", "en")
    assert _people_named(session, "Maria") == []


def test_a_supervisor_is_refused_in_the_chat(
    session: Session, bm: Ferinos, jev_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    marites = bm[1]["Marites"]
    _answers(monkeypatch, "add_person", [], new_name="n0", role="clerk")
    assert _turn(session, marites, "idagdag si maria clerk") == t("bm.not_allowed", "fil")
    assert _people_named(session, "Maria") == []


def test_a_not_owner_admin_add_replies_no_record_in_the_chat(
    session: Session, bm: Ferinos, jev_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = _admin(session, bm[0])
    _answers(monkeypatch, "add_person", [], new_name="n0", role="admin")
    assert _turn(session, admin, "add user eve admin") == t("bm.no_record", "en")
    assert _people_named(session, "Eve") == []


@pytest.mark.parametrize(
    "typed",
    [TYPED, "0917-123-45-67", "(0917) 123 4567", "+63 917 - 123 -- 4567", "0 9 1 7 1 2 3 4 5 6 7"],
)
def test_a_phone_is_set_from_the_chat_and_never_sent_to_jev(
    session: Session, bm: Ferinos, jev_on: None, monkeypatch: pytest.MonkeyPatch, typed: str
) -> None:
    """Extraction, the mask and the parser share events.phone_candidates: every shape the mask
    hides is the number the tool links, and none of its digits reaches Jev."""
    kiosk, ppl = bm
    admin = _admin(session, kiosk, lang="fil")
    seen: list[dict[str, Any]] = []
    _answers(monkeypatch, "set_phone", seen, person=ppl["Ana"].id)
    reply = _turn(session, admin, f"number ni ana {typed}")
    assert reply == t("bm.person.phone_linked", "fil", name=ppl["Ana"].name, last4="4567")
    assert linking.identity_for(session, "whatsapp", ADDRESS) is not None
    assert seen[0]["state"]["message"].endswith(" <number>")
    assert not any(d in json.dumps(seen) for d in (*DIGITS, "4567"))
    _no_digits_in_events(session)
    assert _turn(session, admin, "number ni ana 0917 123") == t(
        "bm.person.ask_phone", "fil", example="0917 123 4567"
    )
