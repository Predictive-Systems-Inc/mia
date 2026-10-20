"""Reply blocks for the Jev decider. Tool results are worded by rules.compose(), the same fi and
en wordings (and variants) as the rules model, so the two paths never drift; reply_only uses
the shared conversation strings. In a retail organisation (D39) the kiosk tools are worded by
retail_reply and every other reply through word_key, so cleaning keeps its words byte for byte."""

import re
from typing import Any

from pydantic_ai.messages import ToolReturnPart

from mia.agents.shift_supervisor.roster import REASON_KEYS
from mia.agents.shift_supervisor.rules import compose, fmt_date, is_retail, word_key
from mia.chat.blocks import Block, CardBlock, CardField, TextBlock
from mia.i18n import t
from mia.i18n.strings import STRINGS

__all__ = ["conversation_reply", "retail_reply", "tool_reply", "word_key"]

CONVERSATION_KEYS = {
    "greeting": "conversation.greeting",
    "thanks": "conversation.thanks",
    "goodbye": "conversation.goodbye",
    "capabilities": "conversation.capabilities",
    "send_photos": "reply.send_photos",
    "injection": "fallback.help",  # an instruction in a message is data: offer help, act on nothing
    "other": "fallback.help",
}
RETAIL_TOOLS = ("set_roster", "roster", "swap_shifts", "correct_timesheet", "close_day")
# Tools whose refusal compose words with the exception's own (English) text.
_RAW_INVALID = ("record_absence", "get_my_visits", "assign_cover")
# cover.answer_swap's CoverError texts to their keys; any other refusal of an answer is "gone".
_SWAP_ERRORS = {"no open swap ask for you": "shift.swap.none"}
_KNOWS = re.compile(r"knows the site \((\d+) ")
_HOURS = re.compile(r"([\d.]+) h booked this week")


def tool_reply(tool: str, out: dict[str, Any], lang: str) -> list[Block]:
    """The reply to one tool result (tool is the name without the agent prefix)."""
    if is_retail():
        if tool in RETAIL_TOOLS:
            return retail_reply(tool, out, lang)
        if out.get("reason") == "past":  # record_absence for a day gone by
            return _text("shift.swap.past", lang)
        if out.get("status") == "invalid" and tool in _RAW_INVALID:
            return _text("retail.not_found", lang)
        if tool == "find_replacements" and out.get("candidates"):
            return _cover_card(out, lang)
    return compose(ToolReturnPart(tool_name=tool, content=out, tool_call_id="jev"), lang)


def conversation_reply(kind: str, lang: str) -> list[Block]:
    """The reply to a message that needs no action."""
    return [TextBlock(text=t(word_key(CONVERSATION_KEYS.get(kind, "fallback.help")), lang))]


def _text(key: str, lang: str, **params: object) -> list[Block]:
    return [TextBlock(text=t(key, lang, **params))]


def _first(name: str | None) -> str:
    return (name or "").split()[0] if name else ""


def _date(value: str | None, lang: str) -> str:
    return fmt_date(value, lang) if value else ""


def _cover_card(out: dict[str, Any], lang: str) -> list[Block]:
    """compose's cover card with each candidate's reasons worded by key (no skills, no travel):
    the kiosk shifts they have worked and their hours this week, read from scoring's reasons."""
    blocks = compose(
        ToolReturnPart(tool_name="find_replacements", content=out, tool_call_id="j"), lang
    )
    fields = []
    for c in out["candidates"]:
        text = " ".join(c["reasons"])  # ponytail: reads scoring's own literals, keep in step
        knows, hours = _KNOWS.search(text), _HOURS.search(text)
        params = {"hours": hours[1] if hours else "0"}
        key = "retail.cover.reason" if knows else "retail.cover.new"
        fields.append(
            CardField(
                label=c["name"], value=t(key, lang, visits=knows[1] if knows else 0, **params)
            )
        )
    return [
        CardBlock(title=b.title, fields=fields) if isinstance(b, CardBlock) else b for b in blocks
    ]


def retail_reply(tool: str, out: dict[str, Any], lang: str) -> list[Block]:
    """The reply to one of the kiosk tools (set_roster, roster, swap_shifts, correct_timesheet,
    close_day): every word through a key, every number from the tool's result."""
    status = out.get("status")
    if status == "denied":
        return _text(word_key("denied.generic"), lang)
    if status == "invalid" and not out.get("reason"):
        return _text("retail.not_found", lang)  # a LookupError: no single kiosk or person
    if tool == "set_roster":
        return _roster_set(out, lang)
    if tool == "roster":
        return _week(out, lang)
    if tool == "swap_shifts":
        return _swap(out, lang)
    if tool == "correct_timesheet":
        if status == "ok":
            params = {"date": _date(out["date"], lang), "start": out["start"], "end": out["end"]}
            return _text("shift.time.corrected", lang, **params)
        return _text(f"shift.time.{out['reason']}", lang, date=_date(out.get("date"), lang))
    params = {"location": out.get("branch", ""), "date": _date(out.get("date"), lang)}
    if status == "ok":  # close_day
        return _text("shift.closed.done", lang, count=out["cancelled"], **params)
    return _text(f"shift.closed.{out['reason']}", lang, **params)


def _roster_set(out: dict[str, Any], lang: str) -> list[Block]:
    """The roster saved, then one line per clash (person, how many shifts left open, why)."""
    if out["status"] == "invalid":
        return _text("shift.roster.outside", lang, shifts=", ".join(out["outside"]))
    lines = [t("shift.roster.done", lang, jobs=", ".join(out["jobs"]), count=out["planned"])]
    for c in out["clashes"]:
        reason = t(REASON_KEYS.get(c["reason"], "shift.reason.other"), lang)
        name = _first(c["person"])
        lines.append(t("shift.roster.clash", lang, name=name, count=len(c["dates"]), reason=reason))
    return [TextBlock(text="\n".join(lines))]


def _week(out: dict[str, Any], lang: str) -> list[Block]:
    """The week's shifts as one card, a field per person."""
    if not out["people"]:
        return _text(word_key("visits.none"), lang)
    fields = [
        CardField(
            label=name,
            value="; ".join(
                f"{fmt_date(v['date'], lang)} {v['start']}-{v['end']} {v['location']}"
                for v in visits
            ),
        )
        for name, visits in out["people"].items()
    ]
    title = t("shift.roster.week_title", lang, date=fmt_date(out["start"], lang))
    return [CardBlock(title=title, fields=fields)]


def _swap(out: dict[str, Any], lang: str) -> list[Block]:
    status, reason = out["status"], out.get("reason")
    params = {"name": _first(out.get("other")), "date": _date(out.get("date"), lang)}
    if status in ("asked", "confirming", "override"):
        return _text(f"shift.swap.{status}", lang, **params)
    if status == "declined":
        return _text("shift.swap.no", lang)
    key = f"shift.swap.{reason}"
    if key not in STRINGS["en"]:
        key = _SWAP_ERRORS.get(str(reason), "shift.swap.gone")
    return _text(key, lang, **params)
