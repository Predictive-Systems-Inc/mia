from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / ".claude/skills/mia-build-agent"


def test_skill_files_exist_and_name_the_gates() -> None:
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: mia-build-agent")
    for word in ("data standard", "scaffold", "subagent-driven", "gate half", "checklist.md"):
        assert word in text
    for name in ("checklist.md", "prompts/spec.md", "prompts/plan.md", "prompts/reviewer.md"):
        assert (SKILL / name).exists(), name


def test_checklist_covers_the_rules_parts_one_and_two_kept_finding() -> None:
    text = (SKILL / "checklist.md").read_text()
    for phrase in (
        "MANIFEST.id",
        "pseudonymised",
        "minor units",
        "read_all",
        "midnight",
        "negation",
        "fresh gate half",
        "Tagalog",
    ):
        assert phrase in text, phrase
    assert "—" not in text
