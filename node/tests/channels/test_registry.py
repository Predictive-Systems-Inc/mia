"""Adapter registry and the per-organisation on/off switch."""

from collections.abc import Iterator

import pytest

from mia.channels import registry
from mia.core.orgconfig import ChannelConfig, OrgSettings


class Dummy:
    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    saved = dict(registry._adapters)
    registry._adapters.clear()
    yield
    registry._adapters.clear()
    registry._adapters.update(saved)


def test_get_returns_registered_adapter_and_raises_for_unknown() -> None:
    dummy = Dummy("sim")
    registry.register(dummy)  # type: ignore[arg-type]
    assert registry.get("sim") is dummy
    with pytest.raises(KeyError):
        registry.get("viber")


def test_enabled_needs_both_registration_and_org_switch() -> None:
    for cid in ("sim", "whatsapp"):
        registry.register(Dummy(cid))  # type: ignore[arg-type]
    org = OrgSettings(
        channels={"sim": ChannelConfig(enabled=True), "sms": ChannelConfig(enabled=True)}
    )
    assert [a.channel_id for a in registry.enabled(org)] == ["sim"]


def test_channels_are_off_by_default() -> None:
    registry.register(Dummy("whatsapp"))  # type: ignore[arg-type]
    assert registry.enabled(OrgSettings()) == []
