"""What Mia can do: a help request is answered by code, never by a rephrase and never by a Jev
request (the owner's test, 23 Oct: "commands?" and "ano kaya mo gawin?" got two rephrases).
A help request is a whole message, casefolded and without punctuation, on a fixed list; "menu"
alone is not on it (the customer service's price list)."""

import re

from mia.agents.base import AgentSpec
from mia.i18n import t

PHRASES: dict[str, frozenset[str]] = {
    "en": frozenset({
        "help", "commands", "command list", "menu of commands", "what can you do",
        "what can i ask", "what can i say", "options",
    }),
    "fil": frozenset({
        "tulong", "ano kaya mo", "ano kaya mo gawin", "ano kaya mong gawin", "ano pwede",
        "ano pwede kong itanong", "mga command",
    }),
    "fi": frozenset({"apua", "ohje", "mitä osaat", "mitä osaat tehdä", "komennot"}),
}  # fmt: skip
ALL = frozenset().union(*PHRASES.values())
_PUNCT = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")


def is_help(text: str) -> bool:
    """True when the whole message, casefolded and without punctuation, is a help phrase."""
    return _SPACES.sub(" ", _PUNCT.sub(" ", text.casefold())).strip() in ALL


def help_text(agents: list[AgentSpec], lang: str, dev: bool) -> str:
    """help.title, then one line per agent (its label and `help.<agent id>` examples), then
    the footer (with the phones page's Teach in dev mode)."""
    lines = [t("help.title", lang)]
    lines += [f"{t(a.label_key, lang)}: {t(f'help.{a.manifest.id}', lang)}" for a in agents]
    lines.append(t("help.footer.dev" if dev else "help.footer", lang))
    return "\n".join(lines)
