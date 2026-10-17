"""User-facing strings in Finnish and English. Code uses keys, never literals."""

import random
from collections.abc import Callable, Sequence

from mia.i18n.strings import STRINGS

SUPPORTED = ("fi", "en")
DEFAULT = "en"

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
