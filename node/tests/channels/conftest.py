"""Channel fixtures: the sim adapter registered and switched on, and linked identities."""

import datetime as dt
from collections.abc import Callable, Iterator

import pytest
from sqlmodel import Session

from mia.channels import registry
from mia.channels.simulator import SimAdapter
from mia.core import orgconfig, store
from mia.core.models import Actor, ChannelIdentity, Person
from mia.core.orgconfig import ChannelConfig, OrgSettings


@pytest.fixture
def sim(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimAdapter]:
    adapter = SimAdapter()
    saved = dict(registry._adapters)
    registry._adapters.clear()
    registry.register(adapter)
    org = OrgSettings(channels={"sim": ChannelConfig(enabled=True)})
    monkeypatch.setattr(orgconfig, "load", lambda org_name=None: org)
    yield adapter
    registry._adapters.clear()
    registry._adapters.update(saved)


LinkFn = Callable[..., ChannelIdentity]


@pytest.fixture
def link(session: Session) -> LinkFn:
    def make(
        person: Person, address: str, last_inbound_at: dt.datetime | None = None
    ) -> ChannelIdentity:
        identity = ChannelIdentity(
            branch_id=person.branch_id,
            person_id=person.id,
            channel="sim",
            address=address,
            last_inbound_at=last_inbound_at,
        )
        row = store.insert(session, identity, Actor.person(person), action="channel.linked")
        session.commit()
        return row

    return make
