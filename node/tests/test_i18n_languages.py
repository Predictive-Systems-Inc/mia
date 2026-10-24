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


# Every agent's keys (and every intent label): a number in a string is a placeholder.
AGENT_PREFIXES = (
    "bm.", "bk.", "pp.", "retail.", "shift.", "cs.", "hr.", "sales.", "stock.", "cover.",
    "absence.", "intent.",
)  # fmt: skip
# ponytail: keys whose digit is a name or an example, not a number code could change: "13th
# month" is a pay's name, "3 sp 5 cl" an example and "100%" the holiday rule's own words. The
# "4-week" of sales.report.compare is the average's window (a placeholder when it is tunable).
NAMED_DIGITS = {
    "hr.thirteenth", "intent.hr_officer.thirteenth", "hr.capabilities", "hr.holiday.regular",
    "sales.capabilities", "sales.report.compare",
}  # fmt: skip


def test_the_branch_managers_numbers_come_only_through_placeholders() -> None:
    """The guard's and the windows' fixed numbers are constants fed to t() (tools.WORDED), so a
    string never carries a number the code could change without it. The bookkeeper's strings
    too: every amount, date and rate is a placeholder, and so is every agent's (AGENT_PREFIXES,
    the named digits aside)."""
    import re

    from mia.agents.branch_manager import tools

    assert set(i18n.STRINGS) == set(i18n.SUPPORTED)
    for lang, strings in i18n.STRINGS.items():
        for key, value in strings.items():
            if not key.startswith(AGENT_PREFIXES) or key in NAMED_DIGITS:
                continue
            for text in [value] if isinstance(value, str) else value:
                assert not re.search(r"\d", re.sub(r"\{[^}]*\}", "", text)), (lang, key)
    assert "20%" in i18n.t("bm.refused.too_far", "en", **tools.WORDED)
