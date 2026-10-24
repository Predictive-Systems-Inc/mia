"""The customer service's public side: the message throttle per channel:address key, the
24-hour window, the customer principal and what rbac lets it reach."""

import datetime as dt

import pytest
from sqlmodel import Session, col, select

from mia.agents.customer_service import MANIFEST, public
from mia.agents.customer_service.models import Customer
from mia.agents.registry import AGENTS
from mia.core import auth
from mia.core.models import Actor, Event
from mia.core.rbac import Resource, get_rbac


def test_customer_message_limit_is_30_per_hour(session: Session) -> None:
    now, key = dt.datetime(2026, 10, 20, 2, tzinfo=dt.UTC), "a1b2@-"
    for i in range(30):
        assert not auth.throttled(session, "customer_message", key, now)
        auth.record_attempt(session, "customer_message", key, False, now + dt.timedelta(seconds=i))
    assert auth.throttled(session, "customer_message", key, now + dt.timedelta(minutes=1))
    assert not auth.throttled(session, "customer_message", "other@-", now)
    assert not auth.throttled(session, "customer_message", key, now + dt.timedelta(hours=2))


def test_a_limit_from_settings_replaces_the_default(session: Session) -> None:
    now, key = dt.datetime(2026, 10, 20, 2, tzinfo=dt.UTC), "c3d4@-"
    auth.record_attempt(session, "customer_message", key, False, now)
    tight = auth.Limit(1, auth.H1, auth.H1)
    assert auth.throttled(session, "customer_message", key, now, limit=tight)
    assert not auth.throttled(session, "customer_message", key, now)


def test_the_window_is_24_hours() -> None:
    now = dt.datetime(2026, 10, 20, 4, tzinfo=dt.UTC)
    assert public.window_open(now - dt.timedelta(hours=23, minutes=59), now)
    assert not public.window_open(now - dt.timedelta(hours=24), now)
    assert not public.window_open(None, now)


@pytest.mark.usefixtures("cs")
def test_the_customer_role_is_never_offered_an_agent(session: Session) -> None:
    who = public.customer_actor(_first(session))
    assert who.on_behalf_of is not None and who.on_behalf_of.roles == ["customer"]
    alone = Actor(principal=who.on_behalf_of, branch_id=who.branch_id)
    assert [
        a for a in AGENTS if get_rbac().check(alone, Resource(kind="agent", name=a), "use")
    ] == []


@pytest.mark.usefixtures("cs")
def test_the_customer_actor_is_checked_with_the_agent(session: Session) -> None:
    who = public.customer_actor(_first(session))
    staff_tool = Resource(kind="tool", name=f"{MANIFEST.id}.orders_today")
    agent_alone = who.model_copy(update={"on_behalf_of": None})
    assert get_rbac().check(agent_alone, staff_tool, "execute")
    assert not get_rbac().check(who, staff_tool, "execute", session=session)
    deny = session.exec(select(Event).where(Event.action == "rbac.deny")).one()
    assert deny.after is not None and deny.after["failed_on"] == who.on_behalf_of.id  # type: ignore[union-attr]


@pytest.mark.usefixtures("cs")
def test_the_customer_principal_is_the_row_id_and_the_key_an_hmac(session: Session) -> None:
    customer = _first(session)
    who = public.customer_actor(customer)
    assert who.on_behalf_of is not None and who.on_behalf_of.id == customer.id
    key = public.throttle_key(customer.channel, customer.address)
    assert customer.address not in key and key.endswith("@-") and len(key) == 34


def _first(session: Session) -> Customer:
    return session.exec(select(Customer).order_by(col(Customer.id))).first()  # type: ignore[return-value]


@pytest.mark.usefixtures("cs", "fresh_rbac")
def test_ensure_role_loads_the_agent_role_once(session: Session) -> None:
    hours = Resource(kind="tool", name=f"{MANIFEST.id}.hours")
    agent = public.customer_actor(_first(session)).model_copy(update={"on_behalf_of": None})
    assert not get_rbac().check(agent, hours, "execute")
    public.ensure_role()
    public.ensure_role()
    assert get_rbac().check(agent, hours, "execute")
    assert len(get_rbac().enforcer.get_filtered_policy(0, MANIFEST.roles.agent_role)) == len(
        MANIFEST.roles.grants
    ) + len(MANIFEST.roles.denies)
