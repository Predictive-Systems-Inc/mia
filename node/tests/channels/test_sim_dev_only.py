"""The sim channel's webhook secret is public, so it registers only in dev mode (ADR 021)."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.channels import registry
from mia.cli import main
from mia.core import orgconfig
from mia.core.models import ChannelInbound
from mia.core.orgconfig import ChannelConfig, OrgSettings
from mia.settings import get_settings
from tests.channels.kits import _hub_sign

BODY = json.dumps({"messages": [{"from": "358401234567", "id": "m1", "text": "hei"}]}).encode()


@pytest.fixture
def sim_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    org = OrgSettings(channels={"sim": ChannelConfig(enabled=True)})
    monkeypatch.setattr(orgconfig, "load", lambda org_name=None: org)
    registry._adapters.clear()  # the conftest restores the saved adapters afterwards


def mode(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MIA_AUTH_MODE", value)
    get_settings.cache_clear()


def post_signed(client: TestClient) -> int:
    headers = _hub_sign("sim-secret")(BODY)  # the public default secret
    return client.post("/channels/sim/webhook", content=BODY, headers=headers).status_code


@pytest.mark.usefixtures("branch", "sim_enabled")
def test_required_mode_ignores_sim_and_its_signed_webhook_is_404(
    monkeypatch: pytest.MonkeyPatch, session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    mode(monkeypatch, "required")
    with caplog.at_level(logging.WARNING, logger="mia.channels.setup"), TestClient(app) as client:
        assert post_signed(client) == 404
    assert "sim" not in registry._adapters
    assert session.exec(select(ChannelInbound)).all() == []
    warned = [r for r in caplog.records if r.name == "mia.channels.setup"]
    assert len(warned) == 1 and "MIA_AUTH_MODE=dev" in warned[0].getMessage()


@pytest.mark.usefixtures("branch", "sim_enabled")
def test_dev_mode_still_serves_the_sim_webhook(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    mode(monkeypatch, "dev")
    with TestClient(app) as client:
        assert post_signed(client) == 200
    assert len(session.exec(select(ChannelInbound)).all()) == 1


def test_dev_mode_takes_the_sim_secret_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, sim_enabled: None
) -> None:
    monkeypatch.setenv("MIA_SIM_SECRET", "local-only")
    mode(monkeypatch, "dev")
    from mia.channels.setup import register_configured

    register_configured(get_settings())
    assert registry.get("sim").verify_webhook(_hub_sign("local-only")(BODY), BODY)
    assert not registry.get("sim").verify_webhook(_hub_sign("sim-secret")(BODY), BODY)


def test_cli_sim_refuses_in_required_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    mode(monkeypatch, "required")
    with pytest.raises(SystemExit) as refused:
        main(["channels", "sim", "hei", "--from", "358401234567"])
    assert "MIA_AUTH_MODE=dev" in str(refused.value.code)
