"""The `mia` command on a fresh database: migrate, seed, chat, decide."""

import re

import pytest

from mia.cli import main


def test_migrate_seed_chat_assign_confirm(capsys: pytest.CaptureFixture[str]) -> None:
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
    assert "Mikael Nieminen" in capsys.readouterr().out

    assert main(["inbox", "--as", "Mikael"]) == 0
    assert main(["chat", "Hyväksyn", "--as", "Mikael"]) == 0
    assert "on nyt sinun" in capsys.readouterr().out
    assert main(["inbox", "--as", "Sanna"]) == 0
    assert "hyväksyi" in capsys.readouterr().out
    assert main(["tick"]) == 0
    assert "advanced 0" in capsys.readouterr().out

    # An override approval (Liisa is not available at 09:00) goes to admin or owner.
    assert main(["chat", "Who can cover Kamppi tomorrow at 9:00?", "--as", "Sanna"]) == 0
    thread = re.search(r"--thread (\w+)", capsys.readouterr().out)
    assert thread
    assert main(["chat", "Assign Liisa", "--as", "Sanna", "--thread", thread[1]]) == 0
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


def test_person_add(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["migrate"]) == 0
    assert main(["seed"]) == 0
    capsys.readouterr()
    assert main(["person", "add", "Aada Koski", "--role", "staff", "--lang", "fi"]) == 0
    assert re.search(r"added Aada Koski \(\w{26}\)", capsys.readouterr().out)
    with pytest.raises(SystemExit, match="roles must be"):
        main(["person", "add", "Bea", "--role", "janitor"])
