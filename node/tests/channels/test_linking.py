"""One-time code linking: hashed codes, single use, expiry, lockout, taken addresses, revoke."""

import datetime as dt

import pytest
from sqlmodel import Session, select

from mia.channels import linking
from mia.cli import main
from mia.core import people
from mia.core.db import utcnow
from mia.core.models import (
    Actor,
    ChannelIdentity,
    ChannelLinkCode,
    Message,
    Person,
    Thread,
)

ADDR = "358401234567"


def _code(session: Session, person: Person, by: Person, purpose: str = "invite") -> str:
    code = linking.create_code(session, Actor.person(by), person, purpose)  # type: ignore[arg-type]
    session.commit()
    return code


def test_code_is_six_digits_and_stored_only_as_hmac(
    session: Session, people: dict[str, Person]
) -> None:
    code = _code(session, people["Juha"], people["Sanna"])
    assert len(code) == 6 and code.isdigit()
    row = session.exec(select(ChannelLinkCode)).one()
    assert code not in row.code_hmac and len(row.code_hmac) == 64
    assert row.created_by == people["Sanna"].id


def test_invite_link_prefills_the_code() -> None:
    assert linking.invite_link("012345") == "https://wa.me/358401110000?text=LINK%20012345"


@pytest.mark.parametrize(
    ("text", "code"),
    [("LINK 012345", "012345"), ("  link 012345 ", "012345"), ("LINK 1234", None), ("hei", None)],
)
def test_parse_link_text(text: str, code: str | None) -> None:
    assert linking.parse_link_text(text) == code


def test_redeem_links_the_address(session: Session, people: dict[str, Person]) -> None:
    code = _code(session, people["Juha"], people["Sanna"])
    result = linking.redeem(session, "whatsapp", ADDR, code, utcnow())
    assert result.status == "linked" and result.person and result.person.id == people["Juha"].id
    identity = linking.identity_for(session, "whatsapp", ADDR)
    assert identity and identity.person_id == people["Juha"].id
    assert identity.verified_at and identity.consent_at


def test_code_is_single_use(session: Session, people: dict[str, Person]) -> None:
    code = _code(session, people["Juha"], people["Sanna"])
    linking.redeem(session, "whatsapp", ADDR, code, utcnow())
    assert linking.redeem(session, "whatsapp", "358409999999", code, utcnow()).status == "used"


def test_expired_code(session: Session, people: dict[str, Person]) -> None:
    code = _code(session, people["Juha"], people["Sanna"], purpose="self")
    later = utcnow() + dt.timedelta(minutes=11)
    assert linking.redeem(session, "whatsapp", ADDR, code, later).status == "expired"


def test_unknown_code_is_invalid(session: Session, people: dict[str, Person]) -> None:
    assert linking.redeem(session, "whatsapp", ADDR, "000000", utcnow()).status == "invalid"


def test_address_linked_to_someone_else_is_taken_and_inviter_told(
    session: Session, people: dict[str, Person]
) -> None:
    linking.redeem(
        session, "whatsapp", ADDR, _code(session, people["Juha"], people["Sanna"]), utcnow()
    )
    code = _code(session, people["Mikael"], people["Sanna"])
    result = linking.redeem(session, "whatsapp", ADDR, code, utcnow())
    assert result.status == "taken"
    identity = linking.identity_for(session, "whatsapp", ADDR)
    assert identity and identity.person_id == people["Juha"].id  # nothing overwritten
    told = session.exec(
        select(Message)
        .join(Thread, Thread.id == Message.thread_id)  # type: ignore[arg-type]
        .where(Thread.person_id == people["Sanna"].id)
    ).all()
    assert any("Mikael" in m.text for m in told)


def test_five_failures_in_an_hour_block_the_address(
    session: Session, people: dict[str, Person]
) -> None:
    for _ in range(5):
        assert linking.redeem(session, "whatsapp", ADDR, "000000", utcnow()).status == "invalid"
    good = _code(session, people["Juha"], people["Sanna"])
    assert linking.redeem(session, "whatsapp", ADDR, good, utcnow()).status == "blocked"
    an_hour_later = utcnow() + dt.timedelta(minutes=61)
    assert linking.redeem(session, "whatsapp", ADDR, good, an_hour_later).status == "linked"


def test_deactivating_a_person_revokes_their_identities(
    session: Session, people: dict[str, Person]
) -> None:
    linking.redeem(
        session, "whatsapp", ADDR, _code(session, people["Juha"], people["Sanna"]), utcnow()
    )
    people_service_deactivate(session, people["Juha"])
    assert linking.identity_for(session, "whatsapp", ADDR) is None
    row = session.exec(select(ChannelIdentity)).one()
    assert row.status == "revoked"


def people_service_deactivate(session: Session, person: Person) -> None:
    people.deactivate(session, Actor.system(person.branch_id), person)


def test_no_node_secret_refuses_to_create_codes(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia.settings import get_settings

    monkeypatch.setenv("MIA_NODE_SECRET", "")
    get_settings.cache_clear()
    with pytest.raises(linking.LinkingError):
        _code(session, people["Juha"], people["Sanna"])


def test_cli_invite_prints_link_and_refuses_ambiguous_names(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    capsys.readouterr()
    assert main(["invite", "Juha"]) == 0
    assert "https://wa.me/358401110000?text=LINK%20" in capsys.readouterr().out
    with pytest.raises(
        SystemExit, match="Maria Mäkinen.*Mikael Nieminen|Mikael Nieminen.*Maria Mäkinen"
    ):
        main(["invite", "M"])
