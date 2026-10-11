"""Schedule over the API and the CLI; daily generation on the ticker."""

import asyncio

import pytest
from sqlmodel import Session, select

from mia.cli import main
from mia.core.models import Visit


def test_cli_generate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    assert main(["schedule", "generate", "--days", "14"]) == 0
    assert "generated" in capsys.readouterr().out
    assert main(["schedule", "generate", "--days", "14"]) == 0
    assert "generated 0" in capsys.readouterr().out


def test_ticker_generates_once_a_day(session: Session, branch: object) -> None:
    from mia.api.main import run_due_work

    before = len(session.exec(select(Visit)).all())
    asyncio.run(run_due_work())
    session.expire_all()
    after = len(session.exec(select(Visit)).all())
    assert after > before
    asyncio.run(run_due_work())
    session.expire_all()
    assert len(session.exec(select(Visit)).all()) == after
