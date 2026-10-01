"""User-facing strings in Finnish and English. Code uses keys, never literals."""

from mia.i18n.strings import STRINGS

SUPPORTED = ("fi", "en")
DEFAULT = "en"


def t(key: str, lang: str, **params: object) -> str:
    """Translate key into lang (falls back to English, then to the key itself)."""
    lang = lang if lang in SUPPORTED else DEFAULT
    template = STRINGS.get(lang, {}).get(key) or STRINGS[DEFAULT].get(key) or key
    return template.format(**params)
