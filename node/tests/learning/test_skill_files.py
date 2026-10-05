from pathlib import Path

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
    assert "30 minimum" in (SKILL / "guidelines.md").read_text()


def test_no_em_dash_or_tagalog_in_any_skill_file() -> None:
    for path in SKILL.rglob("*.md"):
        body = path.read_text()
        assert "—" not in body, path
        assert "tagalog" not in body.replace('never "Tagalog"', "").lower(), path


def test_commands_generator_prompt_is_the_skill_file() -> None:
    assert GENERATOR_PROMPT.resolve() == (SKILL / "prompts" / "generator.md").resolve()
    assert GENERATOR_PROMPT.exists()
    assert ".claude/skills/mia-train-role/prompts/generator.md" in (SKILL / "SKILL.md").read_text()
