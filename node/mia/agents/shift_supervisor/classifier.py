"""Rules classifier for the shift supervisor (manifest `models.classifier: rules`).

Turns one user message into an Intent with extracted slots. It never decides anything: tools
and code do. Messages that try to instruct the agent ("ignore your rules ...") are classified
as `other` with injection=True, so they can never trigger a tool.
"""

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel

IntentName = Literal[
    "report_absence",
    "absence_scope",
    "my_visits",
    "find_cover",
    "assign",
    "cover_reply",
    "check_in",
    "check_out",
    "visit_details",
    "cannot_access_site",
    "site_problem",
    "checklist",
    "other",
]

FI_WEEKDAYS = [
    "maanantai",
    "tiistai",
    "keskiviikko",
    "torstai",
    "perjantai",
    "lauantai",
    "sunnuntai",
]
EN_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

INJECTION = re.compile(
    r"ignore (all |your |the |previous |any )*(rules|instructions|policies)|"
    r"disregard (your|the|all) |system prompt|you are now|"
    r"unohda (kaikki |aiemmat )?(ohjeet|säännöt)|älä välitä (ohjeista|säännöistä)",
    re.IGNORECASE,
)
ABSENCE = re.compile(
    r"\b(sick|ill|unwell|fever|flu|absent|can'?t (come|make it|work)|cannot (come|work)|"
    r"won'?t make it|running late|be late|leave early|leaving early|"
    r"kipeä|kipeänä|sairas|sairaana|flunssa|kuumetta|poissa|en pääse|en tule|myöhässä|"
    r"myöhästyn|lähden aikaisin)\b",
    re.IGNORECASE,
)
ACCEPT = re.compile(
    r"^\W*(hyväksyn|kyllä|käy|joo|ok|okei|accept|yes|sure|i can)\W*$", re.IGNORECASE
)
DECLINE = re.compile(
    r"^\W*(en pysty|en voi|ei käy|kieltäydyn|decline|no|i can'?t|cannot)\W*$", re.IGNORECASE
)
SCOPE_ALL = re.compile(r"^\W*(kaikki|all|all of them|whole day|koko päivä[n]?)\W*$", re.IGNORECASE)
SCOPE_MORNING = re.compile(
    r"\b(vain aamu|only (the )?morning|morning only|aamulla vain)\b", re.IGNORECASE
)
SCOPE_AFTERNOON = re.compile(
    r"\b(vain iltapäivä|only (the )?afternoon|afternoon only)\b", re.IGNORECASE
)
COVER = re.compile(
    r"\b(cover|replacement|replace|substitute|stand in|tuura\w*|sijai\w*|korvaa\w*)\b",
    re.IGNORECASE,
)
ASSIGN = re.compile(
    r"^\W*(assign|give it to|valitse|anna|laita)\s+(?P<name>[\wÄÖÅäöå-]+)", re.IGNORECASE
)
# Check-in and check-out are writes: only an anchored phrase triggers them, never a bare word
# ("finished the kitchen", "the delivery arrived", "olen paikalla huomenna" do not).
CHECK_IN = re.compile(
    r"^\W*(?:(?:i'?ve |i have )?arrived|i'?m here|i am here|i'?m at the site|"
    r"check(?:ing|ed)? in)\W*(?:(?:at|in) \S+|now)?\W*$|"
    r"^\W*(?:olen |ollaan )?(?:perillä|paikalla)\b(?!.*\b(?:huomenna|ylihuomenna|klo)\b)|"
    r"^\W*saavuin\b",
    re.IGNORECASE,
)
CHECK_OUT = re.compile(
    r"^\W*(?:(?:i'?m |i am )?(?:all done|done here|finished here|done|finished)|"
    r"check(?:ing|ed)? out|leaving now)\W*(?:here|now|(?:at|in) \S+)?\W*$|"
    r"^\W*(?:valmis|valmista|lopetin)\b|\blähden nyt\b",
    re.IGNORECASE,
)
# A problem report pages the supervisors: only a phrase at the start of the message counts,
# and anything about home, lateness or tomorrow is an absence, not a site problem.
NOT_AT_SITE = (
    r"(?!.*\b(?:home|kotona|kotoa|late|myöhäs\w*|tomorrow|huomenna|next week|ensi viikolla)\b)"
)
CANNOT_ACCESS = re.compile(
    r"^\W*(?:en pääse sisään|ovi on lukossa|ovikoodi ei toimi|koodi ei toimi|väärä koodi|"
    r"hälytin laukesi|i can'?t get in|i cannot get in|the door is locked|"
    r"the (?:door )?code (?:is wrong|doesn'?t work|does not work)|the alarm went off)\b"
    + NOT_AT_SITE,
    re.IGNORECASE,
)
SITE_PROBLEM = re.compile(
    r"^\W*(?:täällä )?(?:ei (?:ole )?(?:vettä|sähköä|lämpöä)|asiakas on (?:vielä|yhä) paikalla|"
    r"no (?:water|power|electricity|heating)\b|the (?:power|water) is (?:out|off)|"
    r"the (?:client|customer) is still (?:here|there))" + NOT_AT_SITE,
    re.IGNORECASE,
)
CHECKLIST = re.compile(
    r"\b(checklist|check list|tarkistuslista\w*|tehtävälista\w*|what do i need to do|"
    r"mitä (pitää|täytyy) tehdä)\b",
    re.IGNORECASE,
)
TICK = re.compile(r"^\W*(?P<word>done|tehty|valmis)\s*:\s*(?P<item>\w.*?)\W*$", re.IGNORECASE)
EMPTY_TICK = re.compile(r"^\W*(?:done|tehty|valmis)\s*:\W*$", re.IGNORECASE)
DETAILS = re.compile(
    r"\b(door code|address|instructions|where is|how do i get in|ovikoodi|osoite|ohjeet|"
    r"ohje|missä on|miten pääsen)\b",
    re.IGNORECASE,
)
VISITS = re.compile(
    r"\b(visits?|schedule|shifts?|rota|käyn\w*|vuor\w*|työvuor\w*|aikataulu\w*)\b",
    re.IGNORECASE,
)
POSSESSIVE_EN = re.compile(r"\b([A-ZÄÖÅ][\wäöå]+)'s\b")
POSSESSIVE_FI = re.compile(r"\b([A-ZÄÖÅ][\wäöå]+n)\s+(käyn\w*|vuor\w*)", re.IGNORECASE)
TIME = re.compile(r"\b(?:at |klo )?([01]?\d|2[0-3])[:.]([0-5]\d)\b")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
FI_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})?")
LATE = re.compile(r"\b(late|myöhässä|myöhästyn)\b", re.IGNORECASE)
EARLY = re.compile(r"\b(leave early|leaving early|lähden aikaisin)\b", re.IGNORECASE)
STOP_WORDS = {
    "who",
    "can",
    "cover",
    "kuka",
    "voi",
    "tuurata",
    "i",
    "show",
    "me",
    "näytä",
    "assign",
    "valitse",
    "olen",
    "tomorrow",
    "today",
    "huomenna",
    "tänään",
    "what",
    "mia",
    "hei",
    "hi",
}


class Intent(BaseModel):
    name: IntentName
    lang: str = "en"
    date: dt.date | None = None
    time: dt.time | None = None
    reason: str | None = None
    accept: bool | None = None
    partial_day: str | None = None
    person_hint: str | None = None
    location_hint: str | None = None
    item: str | None = None  # a checklist item the user ticks off
    injection: bool = False


def parse_date(text: str, today: dt.date) -> dt.date | None:
    """Relative and absolute dates in Finnish and English."""
    low = text.lower()
    if m := ISO_DATE.search(text):
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    if m := FI_DATE.search(text):
        year = int(m[3]) if m[3] else today.year
        try:
            return dt.date(year, int(m[2]), int(m[1]))
        except ValueError:
            return None
    if "ylihuomenna" in low or "day after tomorrow" in low:
        return today + dt.timedelta(days=2)
    if "huomenna" in low or "tomorrow" in low:
        return today + dt.timedelta(days=1)
    if "tänään" in low or "today" in low or "tonight" in low:
        return today
    for names in (FI_WEEKDAYS, EN_WEEKDAYS):
        for index, name in enumerate(names):
            if re.search(rf"\b{name}", low):
                ahead = (index - today.weekday()) % 7
                return today + dt.timedelta(days=ahead)
    return None


def parse_time(text: str) -> dt.time | None:
    """First HH:MM or HH.MM time in the text (24 hour clock), or None."""
    m = TIME.search(text)
    return dt.time(int(m[1]), int(m[2])) if m else None


def _capitalised_words(text: str) -> list[str]:
    words = re.findall(r"[A-ZÄÖÅ][\wäöåÄÖÅ-]+", text)
    return [w for w in words if w.lower() not in STOP_WORDS]


def _place(text: str) -> str | None:
    """A capitalised site name in the message (not the first word of the sentence)."""
    words = _capitalised_words(text[1:]) if text[:1].isupper() else _capitalised_words(text)
    return words[-1] if words else None


def classify(text: str, today: dt.date, default_lang: str = "en") -> Intent:
    """Classify one message. Deterministic; unit tested in tests/test_classifier.py. The
    intent's lang is default_lang (the person's language; nothing detects it)."""
    lang = default_lang
    if INJECTION.search(text):
        return Intent(name="other", lang=lang, injection=True)
    if EMPTY_TICK.search(text):  # "Done:" with nothing after it: an aborted tick, not a check-out
        return Intent(name="other", lang=lang)
    if m := TICK.search(text):
        # The bot's own quick reply ("Tehty: Korvaa pyyhkeet"): before every other intent, so
        # a cover or absence word inside the item never routes it elsewhere.
        return Intent(name="checklist", lang=lang, item=m["item"][:200])
    if ACCEPT.search(text):
        return Intent(name="cover_reply", lang=lang, accept=True)
    if DECLINE.search(text):
        return Intent(name="cover_reply", lang=lang, accept=False)
    if SCOPE_ALL.search(text):
        return Intent(name="absence_scope", lang=lang, partial_day=None)
    if SCOPE_MORNING.search(text):
        return Intent(name="absence_scope", lang=lang, partial_day="morning")
    if SCOPE_AFTERNOON.search(text):
        return Intent(name="absence_scope", lang=lang, partial_day="afternoon")
    if m := ASSIGN.search(text):
        return Intent(name="assign", lang=lang, person_hint=m["name"])
    if COVER.search(text):
        words = _capitalised_words(text)
        return Intent(
            name="find_cover",
            lang=lang,
            date=parse_date(text, today),
            time=parse_time(text),
            location_hint=words[0] if words else None,
        )
    if CANNOT_ACCESS.search(text):  # before absence: "en pääse sisään" is not "en pääse"
        return Intent(name="cannot_access_site", lang=lang, location_hint=_place(text))
    if SITE_PROBLEM.search(text):
        return Intent(name="site_problem", lang=lang, location_hint=_place(text))
    if ABSENCE.search(text):
        reason = "late" if LATE.search(text) else "leaving_early" if EARLY.search(text) else "sick"
        return Intent(
            name="report_absence",
            lang=lang,
            date=parse_date(text, today) or today,
            reason=reason,
            partial_day="morning" if reason == "late" else None,
        )
    if CHECKLIST.search(text):
        return Intent(name="checklist", lang=lang, location_hint=_place(text))
    if CHECK_OUT.search(text):
        return Intent(name="check_out", lang=lang, location_hint=_place(text))
    if CHECK_IN.search(text):
        return Intent(name="check_in", lang=lang, location_hint=_place(text))
    if DETAILS.search(text):
        return Intent(name="visit_details", lang=lang, location_hint=_place(text))
    if VISITS.search(text):
        person = None
        if (m := POSSESSIVE_EN.search(text)) or (m := POSSESSIVE_FI.search(text)):
            person = m[1]
        if person and person.lower() in ("my", "minun", "mina", "minu", *STOP_WORDS):
            person = None
        return Intent(name="my_visits", lang=lang, date=parse_date(text, today), person_hint=person)
    return Intent(name="other", lang=lang)
