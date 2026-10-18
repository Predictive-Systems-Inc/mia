"""User-facing strings in every supported language. Code uses keys, never literals; a key
missing in a language falls back to English, then to the key itself."""

import random
from collections.abc import Callable, Sequence

from mia.i18n import bcl, ceb, fil, hil, ilo, pag, pam, war
from mia.i18n.strings import STRINGS

SUPPORTED = ("fi", "en", "fil", "ceb", "ilo", "hil", "war", "bcl", "pam", "pag")
DEFAULT = "en"
for _module in (fil, ceb, ilo, hil, war, bcl, pam, pag):
    STRINGS[_module.__name__.rsplit(".", 1)[-1]] = _module.STRINGS

# Keys every language must have (the rest fall back to English): what a person reads in the
# routing, language and busy replies.
NEW_KEYS = (
    "agent.shift_supervisor.label",
    "agent.sales_supervisor.label",
    "agent.inventory_manager.label",
    "agent.bookkeeper.label",
    "agent.hr_officer.label",
    "agent.branch_manager.label",
    "chat.switched",
    "route.question",
    "reply.busy",
    "reply.no_agent",
    "reply.unavailable",
    "language.set",
)

# A key may hold several wordings of one reply; one is picked per use so replies do not read
# the same every time. tests/conftest.py pins the first variant, so pinned texts stay stable.
_pick: Callable[[Sequence[str]], str] = random.choice


def t(key: str, lang: str, **params: object) -> str:
    """Translate key into lang (falls back to English, then to the key itself). A key with
    several variants gives one of them."""
    lang = lang if lang in SUPPORTED else DEFAULT
    template = STRINGS.get(lang, {}).get(key) or STRINGS[DEFAULT].get(key) or key
    if not isinstance(template, str):
        template = _pick(template)
    return template.format(**params)
