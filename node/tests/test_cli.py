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


def test_channels_sim_links_and_chats(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    assert main(["invite", "Juha"]) == 0
    code = re.search(r"LINK (\d{6})", capsys.readouterr().out)
    assert code
    assert main(["channels", "sim", f"LINK {code[1]}", "--from", "358400000002"]) == 0
    assert "Juha" in capsys.readouterr().out
    assert main(["channels", "sim", "Olen kipeä huomenna.", "--from", "358400000002"]) == 0
    assert "Kirjasin poissaolosi" in capsys.readouterr().out


def test_invite_without_whatsapp_number_prints_code_not_a_broken_link(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia.settings import get_settings

    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    monkeypatch.setenv("MIA_WA_NUMBER", "")
    get_settings.cache_clear()
    capsys.readouterr()
    assert main(["invite", "Juha"]) == 0
    out = capsys.readouterr().out
    assert "wa.me/?" not in out and "MIA_WA_NUMBER" in out and re.search(r"LINK \d{6}", out)


@pytest.mark.usefixtures("daytime")
def test_cover_ask_from_the_cli_reaches_the_simulated_channel(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every entry point queues channel messages, not only `mia serve`."""
    from mia.channels import registry

    def run(*argv: str) -> int:
        registry._adapters.clear()  # each `mia` command is a new process
        return main(list(argv))

    assert run("migrate") == 0 and run("seed") == 0
    assert run("invite", "Mikael", "--as", "Sanna") == 0
    code = re.search(r"LINK (\d{6})", capsys.readouterr().out)
    assert code
    assert run("channels", "sim", f"LINK {code[1]}", "--from", "358400000003") == 0
    assert run("chat", "Who can cover Kalasatama tomorrow at 6:30?", "--as", "Sanna") == 0
    thread = re.search(r"--thread (\w+)", capsys.readouterr().out)
    assert thread
    assert run("chat", "Assign Mikael.", "--as", "Sanna", "--thread", thread[1]) == 0
    capsys.readouterr()
    assert run("channels", "sim", "Hyväksyn", "--from", "358400000003") == 0
    out = capsys.readouterr().out
    ask, thanks = out.find("[Hyväksyn]"), out.find("Kiitos")
    assert 0 <= ask < thanks  # the ask is shown, before the reply to accepting it
