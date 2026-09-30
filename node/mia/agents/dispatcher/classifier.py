"""Rules classifier for the dispatcher (manifest `models.classifier: rules`).

Turns one user message into an Intent with extracted slots. It never decides anything: tools
and code do. Messages that try to instruct the agent ("ignore your rules ...") are classified
as `other` with injection=True, so they can never trigger a tool.
"""

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel

IntentName = Literal[
    "report_absence", "absence_scope", "my_visits", "find_cover", "assign", "other"
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
FINNISH_HINT = re.compile(
    r"[äöå]|\b(olen|en|ei|ja|tai|kun|klo|että|mikä|mitä|voin|sinun|huomenna|tänään|kuka|"
    r"voi|näytä|minun|kaikki|vain|aamu|valitse|anna|tuurata|kiitos|moi|hei|parhaat)\b",
    re.I,
)
ENGLISH_HINT = re.compile(
    r"\b(i|i'm|my|me|the|to|at|for|and|is|are|you|your|who|what|show|can|assign|sick|"
    r"tomorrow|today|visits?|all|only|please|hello|hi|hey|thanks|thank|best)\b",
    re.I,
)
ABSENCE = re.compile(
    r"\b(sick|ill|unwell|fever|flu|absent|can'?t (come|make it|work)|cannot (come|work)|"
    r"won'?t make it|running late|be late|leave early|leaving early|"
    r"kipeä|kipeänä|sairas|sairaana|flunssa|kuumetta|poissa|en pääse|en tule|myöhässä|"
    r"myöhästyn|lähden aikaisin)\b",
    re.IGNORECASE,
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
    partial_day: str | None = None
    person_hint: str | None = None
    location_hint: str | None = None
    injection: bool = False


def detect_language(text: str, default: str = "en") -> str:
    """'fi' when the text looks Finnish, 'en' when it looks English, otherwise the default."""
    if FINNISH_HINT.search(text):
        return "fi"
    return "en" if ENGLISH_HINT.search(text) else default


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
    m = TIME.search(text)
    return dt.time(int(m[1]), int(m[2])) if m else None


def _capitalised_words(text: str) -> list[str]:
    words = re.findall(r"[A-ZÄÖÅ][\wäöåÄÖÅ-]+", text)
    return [w for w in words if w.lower() not in STOP_WORDS]


def classify(text: str, today: dt.date, default_lang: str = "en") -> Intent:
    """Classify one message. Deterministic; unit tested in tests/test_classifier.py."""
    lang = detect_language(text, default_lang)
    if INJECTION.search(text):
        return Intent(name="other", lang=lang, injection=True)
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
    if ABSENCE.search(text):
        reason = "late" if LATE.search(text) else "leaving_early" if EARLY.search(text) else "sick"
        return Intent(
            name="report_absence",
            lang=lang,
            date=parse_date(text, today) or today,
            reason=reason,
            partial_day="morning" if reason == "late" else None,
        )
    if VISITS.search(text):
        person = None
        if (m := POSSESSIVE_EN.search(text)) or (m := POSSESSIVE_FI.search(text)):
            person = m[1]
        if person and person.lower() in ("my", "minun", "mina", "minu"):
            person = None
        return Intent(name="my_visits", lang=lang, date=parse_date(text, today), person_hint=person)
    return Intent(name="other", lang=lang)
