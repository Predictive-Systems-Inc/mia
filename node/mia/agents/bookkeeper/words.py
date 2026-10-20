"""The bookkeeper's fixed lists and the readers that take receipts, VAT amounts, money amounts,
periods and banks out of a message. Code reads them (rule 7); Jev only picks among the
candidates. Every candidate is a value of a fixed list here, never a word of the message. Pure."""

import datetime as dt
import re

from mia.agents.parsing import FILLER, NEGATION_WORDS, NEGATIONS, find_prices
from mia.core import models

TENDERS = models.TENDERS  # the code list of the standard
SETTLERS = ("gcash", "maya")
PLATFORMS = ("grab", "foodpanda")
CATEGORIES = ("utilities", "rent", "supplies", "transport", "repairs", "other")
BANKS = (
    "bdo", "bpi", "metrobank", "landbank", "unionbank", "security_bank", "chinabank", "pnb",
    "rcbc", "petty",
)  # fmt: skip
PERIODS = (
    "today", "yesterday", "this_week", "last_week", "this_month", "last_month", "this_quarter",
    "last_quarter",
)  # fmt: skip

# The words that name a bank, folded to its BANKS value. "petty" is the petty box (a refill is a
# deposit into it).
BANK_WORDS = {
    "bdo": "bdo", "banco de oro": "bdo", "bpi": "bpi", "metrobank": "metrobank",
    "metro bank": "metrobank", "landbank": "landbank", "land bank": "landbank", "lbp": "landbank",
    "unionbank": "unionbank", "union bank": "unionbank", "security bank": "security_bank",
    "secbank": "security_bank", "chinabank": "chinabank", "china bank": "chinabank",
    "pnb": "pnb", "rcbc": "rcbc", "petty": "petty",
}  # fmt: skip
_BANK = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, BANK_WORDS), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
# A receipt number: after "official receipt", "receipt", "resibo", "rcpt", an upper case "OR"
# (a lower case "or" is the conjunction) or "no.", with an optional "no.", "#" or ":" between.
_RECEIPT = re.compile(
    r"(?:(?i:\bofficial\s+receipt|\breceipt|\bresibo|\brcpt)\b\.?|\bOR\b\.?|(?i:\bno\.))"
    r"\s*(?i:(?:no\.?|number|blg\.?)\s*)?[:#]?\s*(?P<n>\d[\w-]{0,31})"
)
_AMOUNT = r"(?:₱\s?|php\s?|p)?(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d{1,2})?"
_VAT = re.compile(rf"\bvat\b\s*(?:of\s+)?[:=]?\s*(?P<a>{_AMOUNT})(?![\d.,]*\s*%)", re.IGNORECASE)
_NEGATED = re.compile(
    rf"\b(?:{'|'.join(NEGATIONS)})\b[\s,:]*(?:(?:{'|'.join(FILLER)})\s+)*{_AMOUNT}",
    re.IGNORECASE,
)


def _cut(text: str, m: re.Match[str]) -> str:
    return f"{text[: m.start()]} {text[m.end() :]}"


def find_receipt(text: str) -> tuple[str | None, str]:
    """The first receipt number in the text and the text without it (None and the text when
    there is none)."""
    m = _RECEIPT.search(text)
    return (m["n"], _cut(text, m)) if m else (None, text)


def find_vat(text: str, lang: str) -> tuple[int | None, str]:
    """The amount right after "VAT" in minor units (read by parsing.find_prices) and the text
    without it; None and the text when there is none."""
    m = _VAT.search(text)
    if m is None:
        return None, text
    found = find_prices(m["a"], lang)
    return (found[0][1] if found else None), _cut(text, m)


def _drop_negated(text: str) -> tuple[str, bool]:
    """The text without each amount right after a NEGATIONS word (the old value of a
    correction), and whether one was dropped."""
    kept, n = _NEGATED.subn(" ", text)
    return kept, n > 0


def amounts(text: str, lang: str) -> dict[str, int]:
    """The money amounts of the message as {"p0": minor units, ...}: parsing.find_prices after
    the receipt number, the VAT amount and every negated amount are taken out, so none of them,
    no date and no clock time is an amount."""
    text = find_vat(find_receipt(text)[1], lang)[1]
    return dict(find_prices(_drop_negated(text)[0], lang))


def corrected(text: str) -> bool:
    """True when the message corrects an amount: a negated amount was dropped ("hindi 12,450,
    12,540") or the message opens with a negation word ("wag, 2,500 pala", "no, 12,540")."""
    first = text.strip().split(maxsplit=1)[:1]
    opens = bool(first) and first[0].strip(".,!?;:").casefold() in NEGATION_WORDS
    return opens or _drop_negated(text)[1]


def banks_in(text: str) -> list[str]:
    """The BANKS values the text names, in text order, each once."""
    return list(dict.fromkeys(BANK_WORDS[m.casefold()] for m in _BANK.findall(text)))


def _quarter(day: dt.date) -> dt.date:
    return dt.date(day.year, (day.month - 1) // 3 * 3 + 1, 1)


def _months_later(first: dt.date, n: int) -> dt.date:
    """The first day of the month n months after the first day `first`."""
    years, month = divmod(first.month - 1 + n, 12)
    return dt.date(first.year + years, month + 1, 1)


def period_of(key: str, today: dt.date) -> tuple[dt.date, dt.date]:
    """The first and last day (inclusive) of a PERIODS key as of today; weeks run Monday to
    Sunday, months and quarters are whole calendar ones. Raises KeyError for another key."""
    day = dt.timedelta(days=1)
    monday = today - dt.timedelta(days=today.weekday())
    month, quarter = today.replace(day=1), _quarter(today)
    spans = {
        "today": (today, today),
        "yesterday": (today - day, today - day),
        "this_week": (monday, monday + 6 * day),
        "last_week": (monday - 7 * day, monday - day),
        "this_month": (month, _months_later(month, 1) - day),
        "last_month": (_months_later(month, -1), month - day),
        "this_quarter": (quarter, _months_later(quarter, 3) - day),
        "last_quarter": (_months_later(quarter, -3), quarter - day),
    }
    return spans[key]
