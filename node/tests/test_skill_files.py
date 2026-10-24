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


ROOT = SKILL.parents[2]
BASES = (
    SKILL,
    ROOT,
    ROOT / "node",
    ROOT / "node/mia",
    ROOT / "node/mia/agents",
    ROOT / "node/tests",
)
EXTS = (".py", ".md", ".yaml", ".csv")


def _resolve(path: str) -> Path | None:
    return next((b / path for b in BASES if (b / path).exists()), None)


def test_every_path_and_test_name_the_skill_cites_exists() -> None:
    import re

    problems: list[str] = []
    for doc in [SKILL / "SKILL.md", SKILL / "checklist.md", *(SKILL / "prompts").glob("*.md")]:
        for token in re.findall(r"`([^`\n]+)`", doc.read_text()):
            path, _, name = token.partition("::")
            if re.search(r"[\s<>*]", path) or path.startswith("/"):
                continue
            if not (path.endswith(EXTS) or "/" in path):
                continue
            found = _resolve(path)
            if found is None:
                problems.append(f"{doc.name}: {token}")
            elif name and f"def {name}(" not in found.read_text():
                problems.append(f"{doc.name}: {token} (no such test)")
    assert not problems, "\n".join(problems)
