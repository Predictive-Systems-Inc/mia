"""The production planner's readers: the numbers of a plan change, a batch report and a recipe,
taken out of a message by code (rule 7); Jev only picks among the candidates. Every candidate is
a number code read or a value of a fixed list here, never a word of the message. Pure."""

import datetime as dt
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple

from mia.agents.parsing import _DATE, strip_times
from mia.templates.retail.models import RetailIngredient

_COMMON = {
    "one": 1, "two": 2, "three": 3,
    "isa": 1, "isang": 1, "dalawa": 2, "dalawang": 2, "tatlo": 3, "tatlong": 3,
}  # fmt: skip
# The number words per language, en and fil in every one; beyond en and fil machine drafts
# (Q28 to Q35). Per language, so the Pangasinan "talo" (three) is never the Filipino "lost".
NUMBER_WORDS: dict[str, dict[str, int]] = {
    "en": _COMMON,
    "fil": _COMMON,
    "ceb": _COMMON | {"usa": 1, "usang": 1, "duha": 2, "tulo": 3},
    "ilo": _COMMON | {"maysa": 1, "dua": 2, "tallo": 3},
    "hil": _COMMON | {"duha": 2},
    "war": _COMMON | {"usa": 1, "duha": 2, "tulo": 3},
    "bcl": _COMMON | {"saro": 1, "duwa": 2, "tulo": 3},
    "pam": _COMMON | {"metung": 1, "adwa": 2, "atlu": 3},
    "pag": _COMMON | {"sakey": 1, "duara": 2, "talo": 3},
}
_REASONS_EN_FIL = {
    "sunog": "burnt", "burnt": "burnt", "hilaw": "undercooked", "undercooked": "undercooked",
    "nahulog": "dropped", "dropped": "dropped", "iba": "other", "other": "other",
}  # fmt: skip
# The waste reason words per language, en and fil in every one; beyond en and fil machine drafts
# (Q28 to Q35, the stock.reason.* drafts). words.batch reads a reason only right after a count.
REASON_WORDS: dict[str, dict[str, str]] = {
    "en": _REASONS_EN_FIL,
    "fil": _REASONS_EN_FIL,
    "ceb": _REASONS_EN_FIL | {"nasunog": "burnt", "uban": "other"},
    "ilo": _REASONS_EN_FIL | {"napuoran": "burnt", "naata": "undercooked", "natinag": "dropped"},
    "hil": _REASONS_EN_FIL | {"nasunog": "burnt", "iban": "other"},
    "war": _REASONS_EN_FIL | {"nasunog": "burnt"},
    "bcl": _REASONS_EN_FIL | {"nasunog": "burnt"},
    "pam": _REASONS_EN_FIL | {"sinunug": "burnt", "mialag": "dropped", "aliwa": "other"},
    "pag": _REASONS_EN_FIL | {"nasunog": "burnt", "nandugay": "dropped", "arum": "other"},
}
# ponytail: one table of every language's words, since words.batch takes no language; split it
# per language when a reason word of one language means something else in another.
REASONS = {word: reason for words in REASON_WORDS.values() for word, reason in words.items()}
GOOD_WORDS = ("ok", "good", "maayos")
PIECE_WORDS = ("piraso", "pcs", "pc", "pieces", "piece")
MINUTE_WORDS = ("min", "mins", "minutes", "minute", "minuto", "minutos")
# A unit word folded to the ingredient unit it names; "g" is thousandths of a kg.
UNITS = {
    "kg": "kg", "kilo": "kg", "kilos": "kg", "g": "g", "grams": "g", "gram": "g",
    "tray": "tray", "trays": "tray", "pcs": "pcs", "pc": "pcs", "pieces": "pcs",
    "piraso": "pcs", "pack": "pack", "packs": "pack",
}  # fmt: skip

_WORD = re.compile(r"\d+(?:\.\d+)?|[^\W\d_]+", re.UNICODE)
_I_MEAN = re.compile(r"\bi\s+mean\b", re.IGNORECASE)


class _Num(NamedTuple):
    start: int  # the offset in the text
    value: int


def _undated(text: str, lang: str) -> str:
    """The text without clock times and dates (find_dates' patterns; outside en "may 5" stays,
    Filipino "may" is "there is")."""

    def cut(m: re.Match[str]) -> str:
        month = m["m1"] or m["m2"]
        return m[0] if month and month.lower() == "may" and lang != "en" else " "

    return _DATE.sub(cut, strip_times(text))


def numbers(text: str, today: dt.date, lang: str) -> dict[str, int]:
    """The counts of the message as {"n0": n, ...} in text order: digits and NUMBER_WORDS of the
    language, after clock times and dates are taken out (so "alas 3" and "Dec 24" are none). A
    second number corrects the first only with "pala" or "I mean": "2 ..., 3 pala" and "2, I
    mean 1" drop the number before the correction. `today` is unused: every date pattern goes,
    whatever day it names."""
    text = _undated(text, lang)
    known = NUMBER_WORDS.get(lang, _COMMON)
    found: list[_Num] = []
    pala: list[int] = []  # the index of the number right before each "pala"
    for m in _WORD.finditer(text):
        word = m[0].casefold()
        if word.isdigit():
            found.append(_Num(m.start(), int(word)))
        elif word in known:
            found.append(_Num(m.start(), known[word]))
        elif word == "pala" and found:
            pala.append(len(found) - 1)
    drop = {i - 1 for i in pala if i > 0}
    for m in _I_MEAN.finditer(text):
        before = [i for i, n in enumerate(found) if n.start < m.start()]
        if before and len(before) < len(found):
            drop.add(before[-1])
    kept = [n.value for i, n in enumerate(found) if i not in drop]
    return {f"n{i}": v for i, v in enumerate(kept)}


@dataclass(frozen=True)
class BatchParse:
    batch_no: int
    good: int
    waste: int = 0
    reason: str | None = None  # a REASONS value


_FILL = r"(?:\s+(?:pcs|pc|piraso|pieces|na|ang|ay))*"
_BATCH_NO = re.compile(r"\bbatch\s*(?:no\.?|#)?\s*(\d+)\b", re.IGNORECASE)
_GOOD = re.compile(rf"\b(\d+){_FILL}\s+(?:{'|'.join(GOOD_WORDS)})\b", re.IGNORECASE)
_WASTE = re.compile(rf"\b(\d+){_FILL}\s+({'|'.join(REASONS)})\b", re.IGNORECASE)


def batch(text: str) -> BatchParse | None:
    """A batch report read by code: the number after "batch", the good pieces before "ok",
    "good" or "maayos", the waste before a REASONS word (its reason). None without a batch
    number or good pieces."""
    no, good = _BATCH_NO.search(text), _GOOD.search(text)
    if no is None or good is None:
        return None
    waste = _WASTE.search(text)
    if waste is None:
        return BatchParse(int(no[1]), int(good[1]))
    return BatchParse(int(no[1]), int(good[1]), int(waste[1]), REASONS[waste[2].casefold()])


@dataclass(frozen=True)
class RecipeParse:
    batch_yield: int | None
    oven_minutes: int | None
    lines: dict[str, int]  # ingredient id -> thousandths of its unit for one batch
    unknown: list[str]  # the parts code could not read (no ingredient, or a unit that differs)


_PART = re.compile(r"(\d+(?:\.\d+)?)\s*([^\W\d_]*)\s*(.*)", re.UNICODE)


def _ingredient(rest: str, ingredients: Sequence[RetailIngredient]) -> RetailIngredient | None:
    """The ingredient the words name, by its name or a short code (whole words), the longest
    name first."""
    said = f" {' '.join(_WORD.findall(rest.casefold()))} "
    names = [(n.casefold(), i) for i in ingredients for n in [i.name, *i.short_codes]]
    for name, ing in sorted(names, key=lambda x: -len(x[0])):
        if f" {name} " in said:
            return ing
    return None


def _milli(amount: Decimal, unit: str | None, ing: RetailIngredient) -> int | None:
    """Thousandths of the ingredient's unit, or None when the unit said is not the
    ingredient's (g only for a kg ingredient)."""
    if unit == "g" and ing.unit == "kg":
        return int(amount.to_integral_value())
    if unit is None or unit == ing.unit:
        return int((amount * 1000).to_integral_value())
    return None


def recipe(text: str, ingredients: Sequence[RetailIngredient]) -> RecipeParse | None:
    """A recipe read by code, part by part (commas, semicolons, new lines): a piece word after
    the first number is the batch yield, a minute word the oven minutes, else an amount, a unit
    and an ingredient by name or short code (kg in thousandths, g as thousandths of a kg
    ingredient, tray, pcs and pack times 1000 of that unit). A part without an ingredient or
    with a unit that is not the ingredient's goes to `unknown`. None without any number."""
    batch_yield = oven_minutes = None
    lines: dict[str, int] = {}
    unknown: list[str] = []
    first = True
    for part in re.split(r"[,;\n]", text):
        m = _PART.search(part)
        if m is None:
            continue
        amount, word, rest = Decimal(m[1]), m[2].casefold(), m[3]
        if first and word in PIECE_WORDS:
            batch_yield = int(amount)
        elif word in MINUTE_WORDS:
            oven_minutes = int(amount)
        else:
            unit = UNITS.get(word)
            ing = _ingredient(rest if unit else f"{word} {rest}", ingredients)
            milli = _milli(amount, unit, ing) if ing else None
            if ing is None or milli is None:
                unknown.append(part.strip())
            else:
                lines[ing.id] = milli
        first = False
    if first:
        return None
    return RecipeParse(batch_yield, oven_minutes, lines, unknown)
