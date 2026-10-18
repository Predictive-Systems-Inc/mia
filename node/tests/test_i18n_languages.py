from mia import i18n
from mia.core import people
from mia.i18n.strings import STRINGS


def test_ten_languages_are_supported() -> None:
    assert i18n.SUPPORTED == ("fi", "en", "fil", "ceb", "ilo", "hil", "war", "bcl", "pam", "pag")
    assert people.LANGUAGES == i18n.SUPPORTED


def test_new_keys_are_every_key_of_the_new_languages() -> None:
    from mia.i18n import fil

    assert set(fil.STRINGS) <= set(i18n.NEW_KEYS)


def test_every_new_key_exists_in_every_language() -> None:
    missing = [
        (lang, k) for lang in i18n.SUPPORTED for k in i18n.NEW_KEYS if k not in STRINGS[lang]
    ]
    assert missing == []


def test_a_missing_key_falls_back_to_english() -> None:
    assert i18n.t("conversation.apology", "pag") == i18n.t("conversation.apology", "en")


def test_the_shift_supervisor_is_vuoropaallikko_in_finnish() -> None:
    assert i18n.t("agent.shift_supervisor.label", "fi") == "Vuoropäällikkö"
    assert i18n.t("agent.shift_supervisor.label", "en") == "Shift Supervisor"


def test_every_language_has_its_own_name_for_the_buttons() -> None:
    names = {code: i18n.t(f"language.name.{code}", "en") for code in i18n.SUPPORTED}
    assert names["fil"] == "Filipino" and names["fi"] == "Suomi"
    assert len(set(names.values())) == len(names)


def test_clerk_is_a_human_role() -> None:
    assert "clerk" in people.HUMAN_ROLES


def test_the_importer_accepts_a_clerk_and_checks_the_language() -> None:
    import pytest
    from pydantic import ValidationError

    from mia.templates.cleaning.importer import OrganisationIn, PersonIn

    assert PersonIn(name="Aino", roles=["clerk"], language="fil").language == "fil"
    assert OrganisationIn(name="Hype", default_language="fil").default_language == "fil"
    with pytest.raises(ValidationError):
        PersonIn(name="Aino", roles=["staff"], language="xx")
    with pytest.raises(ValidationError):
        OrganisationIn(name="Hype", default_language="xx")
