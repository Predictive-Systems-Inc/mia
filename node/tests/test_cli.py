"""The `mia` command on a fresh database: migrate, seed, chat, decide."""

import logging
import re
from pathlib import Path

import pytest
from sqlmodel import Session, select

from mia.agents.production_planner.models import Plan
from mia.cli import main
from mia.core.models import Event
from mia.core.rbac import get_rbac
from tests.conftest import PP_TODAY, PP_TOMORROW, Pin, Shop
from tests.test_production_planner_tools import at


def test_migrate_seed_chat_assign_confirm(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
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
    from mia.agents.shift_supervisor import alerts

    monkeypatch.setattr(alerts, "run_due", lambda _session, _now: 0)  # the clock decides alerts
    assert main(["tick"]) == 0
    assert "advanced 0 cover request(s), sent 0" in capsys.readouterr().out

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
    assert "näet vain omat käyntisi" in capsys.readouterr().out  # Juha: fi


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


def test_person_add_ask_language(capsys: pytest.CaptureFixture[str]) -> None:
    """--ask-language leaves the language unchosen (the channel asks first); --lang takes any
    supported language."""
    from sqlmodel import select

    from mia.core.db import session_scope
    from mia.core.models import Event, Person

    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    assert main(["person", "add", "Bea Cruz", "--role", "clerk", "--ask-language"]) == 0
    assert main(["person", "add", "Lito Reyes", "--role", "clerk", "--lang", "fil"]) == 0
    with session_scope() as session:
        rows = {p.name: p for p in session.exec(select(Person)).all()}
        chosen = session.exec(select(Event).where(Event.action == "person.language_chosen"))
        ids = {e.entity_id for e in chosen}
        assert rows["Bea Cruz"].id not in ids
        assert rows["Lito Reyes"].id in ids and rows["Lito Reyes"].language == "fil"


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


def test_keys_init(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "k.key"
    assert main(["keys", "init", str(path)]) == 0
    assert "master key written" in capsys.readouterr().out and len(path.read_bytes()) == 32
    with pytest.raises(SystemExit, match="exists"):
        main(["keys", "init", str(path)])


def test_learned_and_forget(capsys: pytest.CaptureFixture[str]) -> None:
    """Two taps are seeded as chat.route_chosen events (events.emit, same after fields as
    route_memory.remember)."""
    from sqlmodel import select

    from mia.chat import route_memory
    from mia.core import events
    from mia.core.db import session_scope
    from mia.core.models import Actor, Branch, Event

    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    with session_scope() as session:
        branch_id = session.exec(select(Branch)).one().id
        for _ in range(2):
            after = {"agent_id": "some_agent", "key": "# sp # cl"}
            events.emit(
                session, route_memory.CHOSEN, ("thread", "t1"), None, after, Actor.system(branch_id)
            )
    capsys.readouterr()
    assert main(["learned"]) == 0
    assert capsys.readouterr().out.strip() == "some_agent\t# sp # cl\t2"
    assert main(["forget", "3 SP 2 cl"]) == 0  # typed as the clerk wrote it: normalised
    assert "Forgotten: # sp # cl" in capsys.readouterr().out
    with session_scope() as session:
        forgotten = session.exec(select(Event).where(Event.action == route_memory.FORGOTTEN)).one()
        assert (forgotten.after or {})["agent_id"] == "some_agent"
    assert main(["learned"]) == 0
    assert "no routes" in capsys.readouterr().out


def test_forget_an_unknown_key_says_so_and_emits_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from sqlmodel import select

    from mia.chat import route_memory
    from mia.core.db import session_scope
    from mia.core.models import Event

    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    capsys.readouterr()
    assert main(["forget", "never learned"]) == 0
    assert "no routes" in capsys.readouterr().out
    with session_scope() as session:
        assert not session.exec(select(Event).where(Event.action == route_memory.FORGOTTEN)).all()


def test_tick_loads_the_agent_roles_first(monkeypatch: pytest.MonkeyPatch) -> None:
    from mia.agents import registry
    from mia.api import main as api_main

    calls: list[str] = []

    async def due() -> tuple[int, int]:
        calls.append("due")
        return 0, 0

    monkeypatch.setattr(registry, "load_roles", lambda: calls.append("roles"))
    monkeypatch.setattr(api_main, "run_due_work", due)
    assert main(["tick"]) == 0
    assert calls == ["roles", "due"]


def test_tick_runs_the_planners_due_draft_with_the_real_roles(
    session: Session,
    pp_shop: Shop,
    pp_pin: Pin,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`mia tick` on the Ferino's seed at the draft hour: the production planner's due draft
    runs under its own agent role (loaded by tick, not by the test fixtures), with no
    PermissionDenied, and its event is emitted."""
    pp_pin(at(PP_TODAY, 14, 5))
    get_rbac.cache_clear()  # drop the roles the conftest fixtures loaded: tick loads its own
    caplog.set_level(logging.ERROR)
    assert main(["tick"]) == 0
    assert "PermissionDenied" not in caplog.text and "failed" not in caplog.text
    session.expire_all()
    plan = session.exec(select(Plan).where(Plan.production_date == PP_TOMORROW)).one()
    assert session.exec(select(Event).where(Event.entity_id == plan.id)).first() is not None
