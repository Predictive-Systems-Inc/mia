"""The rows `mia phrases export` adds to the cases files (extra "taught": true): kept out of
every set's own rows (so the short half's counts hold) and held to the no-wrong-write rule
here, once for every agent: a phrase picks an action for the decider only when it reads, so a
taught row never decides a write (spec teach-mia, section 6)."""

import json
import shutil
from pathlib import Path

import pytest

from mia.agents.decider import Alternative, Decision, honour
from mia.chat import phrases
from tests.evals import cases, gate

AGENTS = sorted(
    p.stem
    for p in cases.FOLDER.glob("*.csv")
    if p.stem != "router" and p.name != phrases.REPORTS_CSV  # saved reports are not cases
)


def _decided(agent: str, action: str) -> dict[str, object]:
    """What the decider does with a taught row when Jev is unsure: honour over a clarify
    that offers the row's action, with the phrase passed only for a read (decider._phrasebook)."""
    unsure = Decision(
        action="clarify",
        confidence=0.4,
        raw_action=action,
        alternatives=[Alternative(action=action, probability=0.4)],
    )
    d = honour(unsure, action if action in phrases.reads(agent) else None)
    return {"action": d.action, "missing": d.missing, "error": None}


@pytest.mark.parametrize("agent", AGENTS)
def test_taught_rows_name_an_action_and_never_write(agent: str) -> None:
    taught = [r for r in cases.read(agent, taught=True) if r.extra.get("taught") is True]
    for r in taught:
        assert r.intent in gate.actions(agent), r
    results = [
        {"half": "short", "expected_action": r.intent, **_decided(agent, r.intent)} for r in taught
    ]
    assert gate.wrong_writes(results, agent) == []


def test_a_taught_write_row_is_skipped_and_held_to_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copy(cases.path("sales_supervisor"), tmp_path / "sales_supervisor.csv")
    before = len(cases.read("sales_supervisor"))
    extra = json.dumps({"scenario": "taught", "taught": True}).replace('"', '""')
    with (tmp_path / "sales_supervisor.csv").open("a", encoding="utf-8") as f:
        f.write(f'report_sales,Ube Lima,fil,short,owner,,,,,,,,,,,"{extra}"\n')
    monkeypatch.setattr(cases, "FOLDER", tmp_path)
    assert len(cases.read("sales_supervisor")) == before
    (row,) = [r for r in cases.read("sales_supervisor", taught=True) if r.extra.get("taught")]
    assert _decided("sales_supervisor", row.intent)["action"] == "clarify"
    assert _decided("sales_supervisor", "sales_today")["action"] == "sales_today"
