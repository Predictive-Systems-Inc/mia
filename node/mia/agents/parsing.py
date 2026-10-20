"""Number, time and date parsing shared by the agents that read counts or days from a message.

Code splits the numbers (and clock times) out of the message (rule 7); the model only maps each
group to an item. Pure functions, no database access.
"""

import datetime as dt
import re
from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

TOTAL_WORDS = ("total", "kabuuan", "tanan", "yhteensä", "sum")
FILLER = {
    "po", "na", "pcs", "pc", "pieces", "piece", "kpl", "ng", "nga", "sa", "ang", "yung", "ka",
    "pa", "lang",
}  # fmt: skip
# A negation word marks the number after it as the old value (sorry 4 special not 3): both go.
NEGATIONS = {
    "not", "hindi", "dili", "diri", "indi", "bako", "ali", "aliwa", "ei", "instead", "saan",
    "haan",
}  # fmt: skip
# The words that mark a whole message as negated (has_negation): a typed keep with one is asked,
# never run. "no" and the "don't" words are not in NEGATIONS: "no, 4 sp" corrects to 4.
NEGATION_WORDS = NEGATIONS | {"no", "stop", "dai", "huwag", "wag", "ayaw"}


@dataclass(frozen=True)
class Group:
    quantity: int | None
    words: str
    raw: str


def menu_tokens(items: Iterable[tuple[str, Sequence[str]]]) -> set[str]:
    """The casefolded words of the item names and the short codes, from (name, codes) pairs,
    and the whole casefolded name of an item whose name carries a digit ("box of 4")."""
    tokens: set[str] = set()
    for name, codes in items:
        folded = name.casefold()
        tokens |= {*folded.split(), *map(str.casefold, codes)}
        if any(c.isdigit() for c in folded):
            tokens.add(folded)  # whole, so pre_parse never reads its digit as a count
    return tokens


def _orient(kept: list[str], words_first: bool) -> list[tuple[int, list[str]]]:
    """(quantity, words) groups: words after each number (words_first=False; words before the
    first number are stray and dropped) or before it (True; words after the last are dropped)."""
    groups: list[tuple[int, list[str]]] = []
    pending: list[str] = []
    for tok in kept:
        if tok.isdigit():
            groups.append((int(tok), pending if words_first else []))
            pending = []
        elif words_first or not groups:
            pending.append(tok)
        else:
            groups[-1][1].append(tok)
    return groups


def _negated(tokens: list[str], numbers: list[int]) -> set[int]:
    """Indexes to drop: each negation word, and the number after it (with the filler and "of"
    in between)."""
    drop: set[int] = set()
    for i, tok in enumerate(tokens):
        if tok not in NEGATIONS:
            continue
        drop.add(i)
        j = i + 1
        while j < len(tokens) and (tokens[j] in FILLER or tokens[j] == "of"):
            j += 1
        if j in numbers:
            drop.update(range(i + 1, j + 1))
    return drop


def _tokens(text: str) -> list[str]:
    text = re.sub(r"(?<!\w)[\u20b1\u20ac$p](?=\d)", "", text.lower())  # a currency symbol
    return re.sub(r"(?<=\d),(?=\d)", "", text).replace(",", " ").split()


def was_corrected(text: str) -> bool:
    """True when a negation word dropped a number (the old value of a correction), the same
    rule pre_parse applies. Pure."""
    tokens = _tokens(text)
    numbers = [i for i, tok in enumerate(tokens) if tok.isdigit()]
    return any(i in numbers for i in _negated(tokens, numbers))


def has_negation(text: str) -> bool:
    """True when a token of the text is a negation word (NEGATION_WORDS). Pure."""
    return any(tok.strip(".!?;:\"'()") in NEGATION_WORDS for tok in _tokens(text))


def _join_names(tokens: list[str], menu_tokens: Collection[str]) -> list[str]:
    """The tokens with each run that spells a multi-word menu token ("box", "of", "4") joined
    into that one token, longest first."""
    phrases = sorted((m.split() for m in menu_tokens if " " in m), key=len, reverse=True)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        hit = next((p for p in phrases if tokens[i : i + len(p)] == p), None)
        out.append(" ".join(hit) if hit else tokens[i])
        i += len(hit) if hit else 1
    return out


def pre_parse(text: str, menu_tokens: Collection[str]) -> tuple[list[Group], int | None]:
    """Groups of (quantity, item words) and the stated total if any. Pure; item words are not
    matched to the menu here (Jev does that). A negation word drops itself and the number after
    it (the old value of a correction). Both orientations are built, number-then-words and
    words-then-number, and the one whose words hold more `menu_tokens` (casefolded item name
    words and short codes) wins; on a tie, words-then-number only when the message ends with a
    number and every number follows words. A menu token with spaces (an item name with a
    digit, from menu_tokens) is kept whole."""
    tokens = _join_names(_tokens(text), menu_tokens)
    numbers = [i for i, tok in enumerate(tokens) if tok.isdigit()]
    drop = _negated(tokens, numbers)
    numbers = [i for i in numbers if i not in drop]
    total: int | None = None
    for i, tok in enumerate(tokens):
        if tok not in TOTAL_WORDS:
            continue
        drop.add(i)
        near = [j for j in (i + 1, i - 1) if j in numbers]
        if near:
            total = int(tokens[near[0]])
            drop.add(near[0])
        elif len(numbers) > 1:  # the last number when it dwarfs the rest
            *rest, last = (int(tokens[j]) for j in numbers)
            if last >= 10 * max(rest):
                total = last
                drop.add(numbers[-1])
    kept = [tok for i, tok in enumerate(tokens) if i not in drop and tok not in FILLER]
    menu = {m.casefold() for m in menu_tokens}
    after, before = _orient(kept, False), _orient(kept, True)

    def score(groups: list[tuple[int, list[str]]]) -> int:
        return sum(w in menu for _, words in groups for w in words)

    ends = bool(kept) and kept[-1].isdigit()
    follows = all(
        k > 0 and not kept[k - 1].isdigit() for k, tok in enumerate(kept) if tok.isdigit()
    )
    if score(before) != score(after):
        groups = before if score(before) > score(after) else after
    else:
        groups = before if ends and follows else after
    return [Group(n, " ".join(w), f"{n} {' '.join(w)}".strip()) for n, w in groups], total


# ponytail: "alas n" is pm for 1 to 6 and 12 (a shop is open in the afternoon, not at 2 am),
# else am.
ALAS = {
    "una": 1, "dos": 2, "tres": 3, "kuwatro": 4, "singko": 5, "sais": 6, "siyete": 7,
    "otso": 8, "nuwebe": 9, "diyes": 10, "onse": 11, "dose": 12,
}  # fmt: skip
_CLOCK = re.compile(
    r"(?<![\d:])(?P<h12>\d{1,2})(?::(?P<m12>\d{2}))?\s*(?P<ap>am|pm)\b"
    r"|\b(?P<h24>[01]?\d|2[0-3]):(?P<m24>[0-5]\d)\b"
    rf"|\balas\s+(?P<alas>\d{{1,2}}|{'|'.join(ALAS)})\b",
    re.IGNORECASE,
)


def _hour(n: int, pm: bool) -> int:
    """The 24-hour hour of a 12-hour clock hour (12 am is 0, 12 pm is 12)."""
    return n % 12 + (12 if pm else 0)


def _clock_matches(text: str) -> list[tuple[re.Match[str], dt.time]]:
    """Each valid clock time in the text with its match, in text order."""
    found: list[tuple[re.Match[str], dt.time]] = []
    for m in _CLOCK.finditer(text):
        if m["h12"]:
            hour, minute = int(m["h12"]), int(m["m12"] or 0)
            if not 1 <= hour <= 12 or minute > 59:
                continue
            at = dt.time(_hour(hour, m["ap"].lower() == "pm"), minute)
        elif m["h24"]:
            at = dt.time(int(m["h24"]), int(m["m24"]))
        else:
            word = m["alas"].lower()
            n = ALAS.get(word) or int(word)
            if not 1 <= n <= 12:
                continue
            at = dt.time(_hour(n, n <= 6 or n == 12))
        found.append((m, at))
    return found


def find_times(text: str) -> list[tuple[str, dt.time]]:
    """Clock times in the message in text order as (id "t0", "t1", ..., time): 12-hour with
    am/pm, 24-hour HH:MM, and Filipino "alas <n>". A bare number is never a time. Pure."""
    return [(f"t{i}", at) for i, (_, at) in enumerate(_clock_matches(text))]


def strip_times(text: str) -> str:
    """The text with every clock time find_times finds replaced by a space, so a time ("3 pm",
    "alas 2") never becomes a count group in pre_parse. Pure."""
    for m, _ in reversed(_clock_matches(text)):
        text = f"{text[: m.start()]} {text[m.end() :]}"
    return text


# Words that say the sender wants to buy, per language (machine drafts beyond en and fi, Q28 to
# Q35). Code reads them like NEGATIONS: a place_order decision without one is asked first.
BUY_WORDS = {
    "en": ("order", "buy", "purchase", "restock"),
    "fi": ("tilaa", "tilata", "tilaus", "tilataan", "osta", "ostaa", "ostetaan"),
    "fil": ("bili", "bumili", "bibili", "bilhin", "pabili", "umorder", "kumuha", "kuha"),
    "ceb": ("palit", "mopalit", "paliton", "pagpalit", "kuha", "pakuha"),
    "ilo": ("gatang", "gumatang", "aggatang", "gatangen"),
    "hil": ("bakal", "magbakal", "baklon", "bakla"),
    "war": ("palit", "pumalit", "paliton", "kua"),
    "bcl": ("bakal", "magbakal", "bakalon", "kua"),
    "pam": ("sali", "manali", "salian"),
    "pag": ("saliw", "manaliw", "saliwen"),
}
_BUY = {w for words in BUY_WORDS.values() for w in words}


def has_buy_word(text: str) -> bool:
    """True when a token of the text is a buy word of any language, or contains "order" (so
    mag-order, pag-order, i-order and reorder count). Pure."""
    return any(tok.strip(".!?;:") in _BUY or "order" in tok for tok in _tokens(text))


# Weekday names per language (0 is Monday), shared by the agents that read or say a weekday.
EN_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
FI_WEEKDAYS = [
    "maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai",
]  # fmt: skip
FIL_WEEKDAYS = ["lunes", "martes", "miyerkules", "huwebes", "biyernes", "sabado", "linggo"]
CEB_WEEKDAYS = ["lunes", "martes", "miyerkules", "huwebes", "biyernes", "sabado", "dominggo"]
# Hiligaynon, Waray and Bikol share the Spanish-derived names, Sunday "Domingo".
VISAYAN_WEEKDAYS = [
    "lunes", "martes", "miyerkoles", "huwebes", "biyernes", "sabado", "domingo",
]  # fmt: skip
DAY_NAMES = {
    "en": EN_WEEKDAYS,
    "fi": FI_WEEKDAYS,
    "fil": FIL_WEEKDAYS,
    "ceb": CEB_WEEKDAYS,
    "hil": VISAYAN_WEEKDAYS,
    "war": VISAYAN_WEEKDAYS,
    "bcl": VISAYAN_WEEKDAYS,
}
# Finnish "on a Monday" (essive), as the due messages use it: "kuin viime maanantaina".
FI_WEEKDAYS_ESSIVE = [
    "maanantaina", "tiistaina", "keskiviikkona", "torstaina", "perjantaina", "lauantaina",
    "sunnuntaina",
]  # fmt: skip

# Today: hil "subong", war "yana", bcl "ngunyan"; tomorrow: hil and war "buwas", bcl "sa aga".
DAY_WORDS = {
    "today": 0, "tänään": 0, "ngayon": 0, "karon": 0, "subong": 0, "yana": 0, "ngunyan": 0,
    "ngonyan": 0,
    "tomorrow": 1, "huomenna": 1, "bukas": 1, "ugma": 1, "buwas": 1, "sa aga": 1,
}  # fmt: skip
# ceb "sunod semana", hil "masunod nga semana", war "sunod nga semana", bcl "sunod na semana".
NEXT_WEEK = (
    "next week", "sa susunod na linggo", "susunod na linggo", "ensi viikon",
    "sa sunod semana", "sunod semana", "sa sunod nga semana", "ha sunod nga semana",
    "sunod nga semana", "sa masunod nga semana", "masunod nga semana", "sa sunod na semana",
    "sunod na semana",
)  # fmt: skip
_MONTH_NAMES = (
    ("january", "jan", "enero"), ("february", "feb", "pebrero"), ("march", "mar", "marso"),
    ("april", "apr", "abril"), ("may", "mayo"), ("june", "jun", "hunyo"),
    ("july", "jul", "hulyo"), ("august", "aug", "agosto"),
    ("september", "sept", "sep", "setyembre"), ("october", "oct", "oktubre"),
    ("november", "nov", "nobyembre"), ("december", "dec", "disyembre"),
)  # fmt: skip
MONTHS = {name: i for i, names in enumerate(_MONTH_NAMES, 1) for name in names}


def _alt(words: Iterable[str]) -> str:
    return "|".join(sorted({re.escape(w) for w in words}, key=len, reverse=True))


_WEEKDAY_INDEX = {n: i for names in DAY_NAMES.values() for i, n in enumerate(names)}
_WD = _alt(_WEEKDAY_INDEX)
_MON = _alt(MONTHS)
_DATE = re.compile(
    r"\b(?P<iso>\d{4}-\d{2}-\d{2})\b"
    rf"|\b(?:{_alt(NEXT_WEEK)}),?\s+(?:on\s+)?(?P<nw>{_WD})\w*"
    # The weekday before it: ceb "Biyernes sa sunod semana", bcl "an Biyernes sa sunod na semana".
    rf"|\b(?P<wn>{_WD})\w*\s+(?:{_alt(NEXT_WEEK)})\b"
    rf"|\b(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<m1>{_MON})\b\.?"
    rf"|\b(?P<m2>{_MON})\.?\s+(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\b(?!:)"
    # hil "subong nga bulan", war "yana nga semana", bcl "ngunyan na cutoff" name a period, not
    # today (ponytail: any word after but "adlaw", the day; list the periods if one misreads).
    r"|\b(?P<this>(?:subong|yana|ngunyan|ngonyan)\s+ng?a\s+(?!adlaw\b)\w+)"
    rf"|\b(?P<rel>{_alt(DAY_WORDS)})\b"
    # "(sa) susunod na linggo" and "ngayong linggo" name a week: consumed, never a Sunday.
    r"|\b(?P<week>(?:sa\s+)?susunod\s+na\s+linggo|ngayong\s+linggo)\b"
    rf"|\b(?P<wd>{_WD})\w*",
    re.IGNORECASE,
)


def _month_day(month: int, day: int, today: dt.date) -> dt.date | None:
    """The valid date of that month and day nearest to today (last, this or next year)."""
    found = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            found.append(dt.date(year, month, day))
        except ValueError:
            continue
    return min(found, key=lambda d: abs(d - today), default=None)


def _after(weekday: int, anchor: dt.date) -> dt.date:
    """The first such weekday strictly after the anchor."""
    return anchor + dt.timedelta(days=(weekday - anchor.weekday() - 1) % 7 + 1)


def find_dates(text: str, today: dt.date, lang: str) -> list[tuple[str, dt.date]]:
    """Dates in the message in text order as (id "d0", "d1", ..., date). Pure. Finds the
    today and tomorrow words (en, fi, fil, ceb, hil, war, bcl), weekday names (en, fi, fil,
    ceb, hil, war, bcl: the next such day after today, or after the date before it in the
    message, so "next week Monday to Wednesday" is one week), "next week <weekday>" and
    "<weekday> next week"
    (that weekday of the following week, also in ceb, hil, war and bcl), "<d> <month>" and
    "<month> <d>" with English or Filipino month names (the year nearest to today), and ISO
    dates. A bare number is never a date; an invalid date is skipped; "(sa) susunod na linggo"
    and "ngayong linggo" without a weekday after them are a week, not a date; "subong nga bulan"
    and the like (this month, this week) are a period, not today."""
    found: list[dt.date] = []
    for m in _DATE.finditer(text):
        day: dt.date | None
        if m["iso"]:
            try:
                day = dt.date.fromisoformat(m["iso"])
            except ValueError:
                continue
        elif m["nw"] or m["wn"]:
            monday = today + dt.timedelta(days=7 - today.weekday())
            day = monday + dt.timedelta(days=_WEEKDAY_INDEX[(m["nw"] or m["wn"]).lower()])
        elif m["m1"] or m["m2"]:
            month = (m["m1"] or m["m2"]).lower()
            # ponytail: "may" is "there is" in Filipino and Cebuano; only English reads it.
            if month == "may" and lang != "en":
                continue
            day = _month_day(MONTHS[month], int(m["d1"] or m["d2"]), today)
        elif m["week"] or m["this"]:
            continue
        elif m["rel"]:
            day = today + dt.timedelta(days=DAY_WORDS[m["rel"].lower()])
        else:
            anchor = max([today, *found[-1:]])
            day = _after(_WEEKDAY_INDEX[m["wd"].lower()], anchor)
        if day is not None:
            found.append(day)
    return [(f"d{i}", d) for i, d in enumerate(found)]


# An amount in pesos: an optional currency mark (peso sign, "php", "p" right before the digits),
# the whole pesos (a comma before exactly three digits groups thousands), then centavos after a
# point or comma ("49.50", "49,5"). "50 pesos" and "50 piso" read as 50: the word is not needed.
_PRICE = re.compile(
    r"(?<![\w.,])(?:₱\s?|php\s?|p)?(?P<whole>\d{1,3}(?:,\d{3})+(?!\d)|\d+)"
    r"(?:[.,](?P<cents>\d{1,2}))?(?![.,]\d)(?=pesos?\b|piso\b|\W|$)",
    re.IGNORECASE,
)


def find_prices(text: str, lang: str, menu_tokens: Collection[str] = ()) -> list[tuple[str, int]]:
    """Amounts in the message in text order as (id "p0", "p1", ..., integer minor units):
    "50", "₱50", "P50", "50 pesos", "50piso", "49.50" (4950). Clock times (strip_times) and
    dates (find_dates' patterns, read as find_dates reads them in lang) are removed first, so
    "Nov 2", "alas 3" and an English "May 5" are never prices; outside en "may 5" stays (Filipino
    "may" is "there is"). A number right before a menu token (filler words aside, as pre_parse
    reads them) is a count ("3 kape for 65": only 65), unless no other amount is left
    ("subukan natin 50 ang classic": 50); the digit of a menu name ("Box of 4") is no amount. Pure; the model only picks among these candidates,
    never computes one."""

    def undated(m: re.Match[str]) -> str:
        month = m["m1"] or m["m2"]
        return m[0] if month and month.lower() == "may" and lang != "en" else " "

    text = _DATE.sub(undated, strip_times(text))
    menu = {m.casefold() for m in menu_tokens}
    kept_tokens = [tok for tok in _join_names(_tokens(text), menu) if tok not in FILLER]
    counts = Counter(
        int(a) for a, b in pairwise(kept_tokens) if a.isdigit() and b.strip(".,:;!?") in menu
    )
    for name in (m for m in menu if " " in m):  # "Box of 4": its digit is no amount
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ", text, flags=re.IGNORECASE)
    found = []
    for m in _PRICE.finditer(text):
        pesos = int(m["whole"].replace(",", ""))
        found.append(pesos * 100 + int((m["cents"] or "0").ljust(2, "0")))
    # ponytail: a count is dropped by its value (the first amount equal to it, whole pesos);
    # token positions if a count and a price ever share a value.
    kept = []
    for amount in found:
        whole, cents = divmod(amount, 100)
        if not cents and counts[whole] > 0:
            counts[whole] -= 1
            continue
        kept.append(amount)
    return [(f"p{i}", amount) for i, amount in enumerate(kept or found)]
