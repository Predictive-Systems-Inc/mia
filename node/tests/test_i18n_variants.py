import string

import pytest

from mia import i18n
from mia.i18n.strings import STRINGS


def _fields(text: str) -> frozenset[str]:
    return frozenset(f for _, f, _, _ in string.Formatter().parse(text) if f)


def test_a_single_string_is_unchanged() -> None:
    assert i18n.t("clarify.question", "en") == "Did you mean:"


def test_tests_get_the_first_variant() -> None:
    variants = STRINGS["en"]["conversation.greeting"]
    assert isinstance(variants, list)
    assert i18n.t("conversation.greeting", "en") == variants[0]


def test_a_variant_is_picked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(i18n, "_pick", lambda v: v[-1])
    assert i18n.t("conversation.greeting", "fi") == STRINGS["fi"]["conversation.greeting"][-1]


def test_variants_share_their_placeholders_across_languages() -> None:
    for key, en in STRINGS["en"].items():
        values = [*(en if isinstance(en, list) else [en])]
        fi = STRINGS["fi"].get(key)
        if fi is not None:
            values += fi if isinstance(fi, list) else [fi]
        if isinstance(en, list) or isinstance(fi, list):
            assert len({_fields(v) for v in values}) == 1, key


def test_variant_lists_have_at_least_two_wordings() -> None:
    for lang, table in STRINGS.items():
        for key, value in table.items():
            if isinstance(value, list):
                assert len(value) >= 2 and len(set(value)) == len(value), (lang, key)


def test_every_override_variant_names_admin_or_owner() -> None:
    # The eval scenario assign_breaking_a_rule_needs_override checks this fragment.
    for v in STRINGS["en"]["assign.override"]:
        assert "admin or owner" in v
