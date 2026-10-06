import argparse
import re
from pathlib import Path

from mia.cli import build_parser
from mia.learning.commands import GENERATOR_PROMPT

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / ".claude" / "skills" / "mia-train-role"
FRONTMATTER = (
    "---\nname: mia-train-role\ndescription: Build, measure and promote a multilingual intent "
    "classifier for one Mia agent role. Use when adding a new agent role, retraining a role's "
    "model, or topping up its data. Follows "
    "docs/superpowers/specs/2026-10-06-skill-models-design.md.\n---\n"
)
PROMPTS = ("planner", "generator", "reviewer", "public-research")


def test_skill_has_steps_gates_and_prompts() -> None:
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith(FRONTMATTER)
    for marker in (
        "Gate 1",
        "Gate 2",
        "mia skills validate",
        "mia skills split",
        "mia skills train",
        "mia skills promote",
        "mia skills harvest",
        "mia skills generate",
        "--signed-by",
        "--split test",
        "dedupe by id",
        "HF_HUB_DISABLE_IMPLICIT_TOKEN=1",
        "public.yaml",
    ):
        assert marker in text, marker
    for prompt in PROMPTS:
        assert (SKILL / "prompts" / f"{prompt}.md").read_text().strip(), prompt
    guidelines = (SKILL / "guidelines.md").read_text()
    assert "30 minimum" in guidelines
    assert "Overlap review" in text
    assert "One message, one label" in guidelines
    assert "## How many intents one model can hold" in guidelines
    assert "up to about 150 labels per role model" in guidelines
    assert '("How many intents one model can hold")' in text
    for rule in ("1. Questions about rules", "2. Doing something", "3. A message that differs"):
        assert rule in guidelines, rule


def test_no_em_dash_or_tagalog_in_any_skill_file() -> None:
    for path in SKILL.rglob("*.md"):
        body = path.read_text()
        assert "—" not in body, path
        assert "tagalog" not in body.replace('never "Tagalog"', "").lower(), path


def test_commands_generator_prompt_is_the_skill_file() -> None:
    assert GENERATOR_PROMPT.resolve() == (SKILL / "prompts" / "generator.md").resolve()
    assert GENERATOR_PROMPT.exists()
    assert ".claude/skills/mia-train-role/prompts/generator.md" in (SKILL / "SKILL.md").read_text()


def _skills_parsers() -> dict[str, argparse.ArgumentParser]:
    top = build_parser()
    (root,) = (a for a in top._actions if isinstance(a, argparse._SubParsersAction))
    skills = root.choices["skills"]
    (sub,) = (a for a in skills._actions if isinstance(a, argparse._SubParsersAction))
    return dict(sub.choices)


def test_every_command_and_flag_in_skill_exists_in_the_cli() -> None:
    parsers = _skills_parsers()
    text = (SKILL / "SKILL.md").read_text()
    spans = [m for m in re.findall(r"`([^`]*mia skills [^`]*)`", text, re.DOTALL)]
    seen: set[str] = set()
    for span in spans:
        cmd = re.search(r"mia skills (\w+)", span).group(1)  # type: ignore[union-attr]
        assert cmd in parsers, cmd
        seen.add(cmd)
        known = {o for a in parsers[cmd]._actions for o in a.option_strings}
        for flag in re.findall(r"(--[a-z-]+)", span):
            assert flag in known, (cmd, flag)
    assert seen == set(parsers)
    assert "candidates.jsonl" in text
    assert "--with-real" in text
