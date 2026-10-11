import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic_ai import models

from mia.cli import main
from mia.core.egress import EgressBlocked, current_context
from mia.learning import commands
from mia.learning.generate import Cell, generate, plan_cells
from mia.learning.schema import IntentSpec, Record, RoleSpec, Targets, load_records

ROLE = RoleSpec(
    id="r",
    job_summary="j",
    responsibilities=["x"],
    counterparts=[
        {"role": "cleaner", "share": 3.0},  # type: ignore[list-item]
        {"role": "owner", "share": 1.0},  # type: ignore[list-item]
    ],
    languages=["en", "fi"],
    countries=["FI"],
    styles={"informal": 0.5, "terse": 0.5},
    intents=[
        IntentSpec(
            id="r.a",
            description="reports sickness",
            counterparts=["cleaner", "owner"],
            risk="read",
            label_en="A",
            slots=["when"],
        )
    ],
    targets=Targets(train_min=8, test=4),
)


def _cell(
    lang: str, who: str, style: str, n: int, intent: str = "r.a", kind: str = "normal"
) -> Cell:
    return Cell(intent=intent, lang=lang, counterpart=who, style=style, count=n, kind=kind)  # type: ignore[arg-type]


def test_plan_cells_exact_train() -> None:
    expected: list[Cell] = []
    for lang in ("en", "fi"):
        # quota 8 per language: cleaner share 3/4, owner 1/4, each style 1/2 -> ceil(3), ceil(1)
        expected += [
            _cell(lang, "cleaner", "informal", 3),
            _cell(lang, "cleaner", "terse", 3),
            _cell(lang, "owner", "informal", 1),
            _cell(lang, "owner", "terse", 1),
        ]
    for lang in ("en", "fi"):
        # other: ceil(8 * 0.08 * 0.5) = 1 per style, first counterpart speaks
        expected += [
            _cell(lang, "cleaner", "informal", 1, intent="other", kind="other"),
            _cell(lang, "cleaner", "terse", 1, intent="other", kind="other"),
        ]
    assert plan_cells(ROLE, "train", per_cell=None) == expected


def test_plan_cells_test_split_and_per_cell_override() -> None:
    test_cells = plan_cells(ROLE, "test", per_cell=None)
    assert [c.count for c in test_cells if c.lang == "en"] == [2, 2, 1, 1, 1, 1]
    forced = plan_cells(ROLE, "train", per_cell=2)
    assert len(forced) == 12 and {c.count for c in forced} == {2}


def _reply(items: list[dict[str, object]], seen: list[str] | None = None) -> httpx.MockTransport:
    args = json.dumps({"response": items})

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request.content.decode())
        call = {
            "id": "c",
            "type": "function",
            "function": {"name": "final_result", "arguments": args},
        }
        message = {"role": "assistant", "content": None, "tool_calls": [call]}
        body = {
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": message}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def _run(cells: list[Cell], transport: httpx.MockTransport, drops: dict[str, int]) -> list[Record]:
    with models.override_allow_model_requests(True):
        return asyncio.run(
            generate(
                ROLE, cells, "local/m", "Write.", split="train", transport=transport, drops=drops
            )
        )


def test_generate_ids_source_and_drops() -> None:
    items: list[dict[str, object]] = [
        {"text": "sick today", "context": "", "slots": {"when": "today"}},
        {"text": "   ", "context": "", "slots": {}},
        {"text": "hurt", "context": "", "slots": {"colour": "red"}},
        {"text": "flu", "context": "c", "slots": {}},
        {"text": "extra beyond count", "context": "", "slots": {}},
    ]
    cells = [_cell("en", "cleaner", "informal", 4), _cell("fi", "owner", "terse", 4)]
    drops: dict[str, int] = {}
    recs = _run(cells, _reply(items), drops)
    assert [r.id for r in recs] == [
        "r.a/en/local-m/0000",
        "r.a/en/local-m/0001",
        "r.a/fi/local-m/0002",
        "r.a/fi/local-m/0003",
    ]
    assert {r.source for r in recs} == {"teacher:local/m"}
    assert [r.text for r in recs] == ["sick today", "flu", "sick today", "flu"]
    assert recs[0].slots == {"when": "today"} and recs[1].context == "c"
    assert drops == {"empty text": 2, "unknown slot": 2}
    assert (recs[2].lang, recs[2].counterpart, recs[2].style) == ("fi", "owner", "terse")


def test_other_cell_gets_other_kind_and_label_and_rejects_slots() -> None:
    cell = _cell("en", "cleaner", "informal", 2, intent="other", kind="other")
    items: list[dict[str, object]] = [
        {"text": "weather?", "context": "", "slots": {}},
        {"text": "x", "context": "", "slots": {"when": "now"}},
    ]
    drops: dict[str, int] = {}
    recs = _run([cell], _reply(items), drops)
    assert [(r.intent, r.kind) for r in recs] == [("other", "other")]
    assert drops == {"unknown slot": 1}


def test_prompt_never_contains_harvested_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIA_LEARNING_DIR", str(tmp_path))
    from mia.settings import get_settings

    get_settings.cache_clear()
    (tmp_path / "r").mkdir()
    secret = "REAL-CUSTOMER-MESSAGE-48213"
    (tmp_path / "r" / "candidates.jsonl").write_text(json.dumps({"text": secret}) + "\n")
    seen: list[str] = []
    _run([_cell("en", "cleaner", "informal", 1)], _reply([], seen), {})
    assert len(seen) == 1 and secret not in seen[0]
    assert "reports sickness" in seen[0] and "Write." in seen[0]
    get_settings.cache_clear()


ROLE_YAML = """
id: tr
job_summary: j
responsibilities: [x]
counterparts: [{role: c, share: 1.0}]
languages: [en, fi]
countries: [FI]
styles: {informal: 1.0}
intents:
  - {id: tr.a, description: d, counterparts: [c], risk: read, label_en: A}
  - {id: tr.b, description: e, counterparts: [c], risk: read, label_en: B}
targets: {train_min: 2, test: 2}
"""


@pytest.fixture
def skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(commands, "AGENTS", tmp_path / "agents")
    folder = tmp_path / "agents" / "tr" / "skill"
    (folder / "data").mkdir(parents=True)
    (folder / "role.yaml").write_text(ROLE_YAML, encoding="utf-8")
    prompt = tmp_path / "gen.md"
    prompt.write_text("Write.", encoding="utf-8")
    monkeypatch.setattr(commands, "GENERATOR_PROMPT", prompt)

    async def fake(
        role: RoleSpec, cells: list[Cell], model: str, prompt: str, **kw: object
    ) -> list[Record]:
        drops = kw["drops"]
        assert isinstance(drops, dict)
        drops["empty text"] = 1
        return [
            Record(
                id=f"{c.intent}/{c.lang}/{i}",
                role="tr",
                intent=c.intent,
                lang=c.lang,
                text="hi",
                counterpart=c.counterpart,
                style=c.style,
                kind=c.kind,
                split=kw["split"],  # type: ignore[arg-type]
                source=f"teacher:{model}",
            )
            for i, c in enumerate(cells)
        ]

    monkeypatch.setattr(commands, "generate", fake)
    return folder


def test_command_writes_generated_jsonl_and_reports(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["skills", "generate", "tr", "--model", "local/m", "--only", "tr.a,fi"])
    out = capsys.readouterr().out
    path = skill / "data" / "generated.jsonl"
    assert code == 0
    assert out == f"1 records in 1 cells written to {path}; dropped: 1 empty text\n"
    assert [r.intent for r in load_records(path)] == ["tr.a"]
    assert load_records(path)[0].lang == "fi"


def test_command_does_not_truncate_existing_data(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    existing = skill / "data" / "test.jsonl"
    existing.write_text("reviewed\n", encoding="utf-8")
    assert main(["skills", "generate", "tr", "--model", "local/m", "--split", "test"]) == 0
    assert existing.read_text(encoding="utf-8") == "reviewed\n"
    written = [p for p in (skill / "data").glob("generated-test-*.jsonl")]
    assert len(written) == 1
    assert str(written[0]) in capsys.readouterr().out


def test_command_error_paths(skill: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skills", "generate", "nobody", "--model", "local/m"]) == 1
    assert "role.yaml not found" in capsys.readouterr().out
    assert main(["skills", "generate", "tr", "--model", "local/m", "--only", "tr.zzz"]) == 1
    assert capsys.readouterr().out == (
        "--only: unknown value(s) ['tr.zzz']; use intent ids or languages\n"
    )
    assert main(["skills", "generate", "tr", "--model", "local/m", "--only", ","]) == 1
    assert "--only: unknown value(s) [',']" in capsys.readouterr().out
    assert main(["migrate"]) == 0  # no seed: zero branches, and a gateway route needs one
    capsys.readouterr()
    assert main(["skills", "generate", "tr", "--model", "gateway/x"]) == 1
    assert capsys.readouterr().out == (
        "the database has 0 branches; run `mia seed` or fix the data\n"
    )


def test_command_missing_prompt_and_model_failure(
    skill: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert main(["skills", "generate", "tr", "--model", "local/m", "--prompt", "/nope.md"]) == 1
    assert capsys.readouterr().out == "generator prompt not found: /nope.md\n"

    async def boom(*a: object, **k: object) -> list[Record]:
        raise RuntimeError("route down")

    monkeypatch.setattr(commands, "generate", boom)
    assert main(["skills", "generate", "tr", "--model", "local/m"]) == 1
    assert capsys.readouterr().out == "generation failed: RuntimeError: route down\n"
    assert not (skill / "data" / "generated.jsonl").exists()


def test_gateway_route_runs_in_an_egress_context_and_local_does_not(
    skill: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str | None] = {}

    async def spy(
        role: RoleSpec, cells: list[Cell], model: str, prompt: str, **kw: object
    ) -> list[Record]:
        try:
            ctx = current_context()
            seen[model] = f"{ctx.agent_id}/{ctx.purpose}/{ctx.actor.principal.type}"
        except EgressBlocked:
            seen[model] = None
        return []

    monkeypatch.setattr(commands, "generate", spy)
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    assert main(["skills", "generate", "tr", "--model", "gateway/x", "--only", "tr.a,fi"]) == 0
    assert main(["skills", "generate", "tr", "--model", "local/m", "--only", "tr.a,fi"]) == 0
    assert seen == {"gateway/x": "learning.generate/skill-generation/system", "local/m": None}
