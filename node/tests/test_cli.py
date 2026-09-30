"""The `mia` command on a fresh database: migrate, seed, chat, decide."""

import re

import pytest

from mia.cli import main


def test_migrate_seed_chat_decide(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["migrate"]) == 0
    assert main(["seed"]) == 0
    assert main(["seed"]) == 0
    assert "already seeded" in capsys.readouterr().out

    assert main(["chat", "Olen kipeä huomenna.", "--as", "Juha"]) == 0
    out = capsys.readouterr().out
    assert "Kirjasin poissaolosi" in out and "[Kaikki] [Vain aamu]" in out

    assert main(["chat", "Who can cover Kalasatama tomorrow at 6:30?", "--as", "Sanna"]) == 0
    thread = re.search(r"--thread (\w+)", capsys.readouterr().out)
    assert thread
    assert main(["chat", "Assign Mikael.", "--as", "Sanna", "--thread", thread[1]]) == 0
    approval = re.search(r"approval (\w+), pending", capsys.readouterr().out)
    assert approval

    assert main(["decide", approval[1], "approved", "--as", "Sanna"]) == 1
    assert "refused" in capsys.readouterr().out
    assert main(["decide", approval[1], "approved", "--as", "Helena"]) == 0
    assert "approved by Helena" in capsys.readouterr().out

    assert main(["chat", "Show me Maria's visits.", "--as", "Juha"]) == 0
    assert "only see your own visits" in capsys.readouterr().out


def test_unknown_person(capsys: pytest.CaptureFixture[str]) -> None:
    main(["migrate"])
    main(["seed"])
    with pytest.raises(SystemExit, match="no person matches"):
        main(["chat", "hi", "--as", "Nobody"])
