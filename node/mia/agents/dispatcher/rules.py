"""The dispatcher's rules model: a Pydantic AI FunctionModel driven by the rules classifier.

Used when MIA_MODEL=test and by the evaluation suite, so every flow runs with no API key and
tool selection is deterministic. It reads only the conversation (user text inside
<user_message> tags, earlier tool calls and results) and the task context lines; it never sees
the database. Replies are composed from tool results only, so it cannot claim work that no
tool reported.
"""

import datetime as dt
import re
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel

from mia.agents.dispatcher.classifier import Intent, classify, detect_language
from mia.chat.blocks import (
    AgentReply,
    ApprovalCardBlock,
    Block,
    CardBlock,
    CardField,
    QuickRepliesBlock,
    TextBlock,
)
from mia.i18n import t

USER_MESSAGE = re.compile(r"<user_message[^>]*>\n?(.*?)\n?</user_message>", re.DOTALL)


def _context(info: AgentInfo) -> tuple[dt.date, str]:
    text = info.instructions or ""
    today = dt.datetime.now(dt.UTC).date()
    lang = "en"
    if m := re.search(r"^Today: (\d{4}-\d{2}-\d{2})$", text, re.MULTILINE):
        today = dt.date.fromisoformat(m[1])
    if m := re.search(r"^Language: (\w+)$", text, re.MULTILINE):
        lang = m[1]
    return today, lang


def _last_user_text(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    m = USER_MESSAGE.search(part.content)
                    return m[1] if m else part.content
    return ""


def _last_call(messages: list[ModelMessage], tool: str) -> ToolCallPart | None:
    for message in reversed(messages):
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == tool:
                    return part
    return None


def _last_return(messages: list[ModelMessage], tool: str) -> dict[str, Any] | None:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolReturnPart) and part.tool_name == tool:
                    content = part.content
                    if isinstance(content, dict) and "status" not in content:
                        return content
    return None


def _fmt_date(value: str, lang: str) -> str:
    d = dt.date.fromisoformat(value)
    return f"{d.day}.{d.month}." if lang == "fi" else d.strftime("%a %-d %b")


def _visit_card(visits: list[dict[str, Any]], title: str, lang: str) -> CardBlock:
    fields = [
        CardField(
            label=f"{_fmt_date(v['date'], lang)} {v['start']}-{v['end']}",
            value=f"{v['location']} ({v['job']})",
        )
        for v in visits
    ]
    return CardBlock(title=title, fields=fields)


def _call(tool: str, args: dict[str, Any]) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=tool, args=args)])


def _final(info: AgentInfo, blocks: list[Block]) -> ModelResponse:
    reply = AgentReply(blocks=blocks).model_dump(mode="json")
    if not info.output_tools:
        raise RuntimeError("the dispatcher agent must use a structured output type")
    return _call(info.output_tools[0].name, reply)


def _help(lang: str) -> list[Block]:
    return [
        TextBlock(text=t("fallback.help", lang)),
        QuickRepliesBlock(
            options=[t("fallback.quick_sick", lang), t("fallback.quick_visits", lang)]
        ),
    ]


def decide(intent: Intent, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Pick the tool call for an intent, or answer directly."""
    lang = intent.lang
    if intent.name == "report_absence":
        args: dict[str, Any] = {"date": (intent.date or dt.datetime.now(dt.UTC).date()).isoformat()}
        args["reason"] = intent.reason or "sick"
        if intent.partial_day:
            args["partial_day"] = intent.partial_day
        return _call("record_absence", args)
    if intent.name == "absence_scope":
        previous = _last_call(messages, "record_absence")
        if previous is None:
            return _final(info, [TextBlock(text=t("absence.no_previous", lang))])
        args = dict(previous.args_as_dict())
        args["partial_day"] = intent.partial_day
        return _call("record_absence", args)
    if intent.name == "my_visits":
        args = {}
        if intent.date:
            args = {"start": intent.date.isoformat(), "end": intent.date.isoformat()}
        if intent.person_hint:
            args["person_name"] = intent.person_hint
        return _call("get_my_visits", args)
    if intent.name == "find_cover":
        args = {"location_name": intent.location_hint}
        if intent.date:
            args["date"] = intent.date.isoformat()
        if intent.time:
            args["time"] = intent.time.strftime("%H:%M")
        return _call("find_replacements", args)
    if intent.name == "assign":
        found = _last_return(messages, "find_replacements")
        if not found:
            return _final(info, [TextBlock(text=t("assign.need_candidates", lang))])
        hint = (intent.person_hint or "").lower()
        visit_id = found["visit"]["visit_id"]
        for c in found.get("candidates", []):
            first = c["name"].split()[0].lower()
            if hint.startswith(first) or first.startswith(hint):
                return _call("assign_cover", {"visit_id": visit_id, "candidate_id": c["person_id"]})
        return _call("assign_cover", {"visit_id": visit_id, "candidate_name": intent.person_hint})
    if intent.name == "cover_reply":
        return _call("respond_to_cover", {"accept": bool(intent.accept)})
    return _final(info, _help(lang))


def compose(part: ToolReturnPart, lang: str) -> list[Block]:
    """Turn one tool result into reply blocks."""
    out = part.content if isinstance(part.content, dict) else {}
    status = out.get("status")
    if status == "denied":
        key = "denied.visits" if part.tool_name == "get_my_visits" else "denied.generic"
        return [TextBlock(text=t(key, lang))]
    if status == "invalid" and part.tool_name == "find_replacements":
        return [TextBlock(text=t("cover.visit_not_found", lang))]
    if status == "invalid" and part.tool_name == "respond_to_cover":
        return [TextBlock(text=t("respond.none", lang))]
    if status == "invalid":
        return [TextBlock(text=out.get("message", ""))]
    if part.tool_name == "record_absence":
        date = _fmt_date(out["date"], lang)
        visits = out["affected_visits"]
        if out["updated"]:
            key = {None: "absence.updated_all", "morning": "absence.updated_morning"}.get(
                out["partial_day"], "absence.updated_afternoon"
            )
            blocks: list[Block] = [TextBlock(text=t(key, lang, date=date))]
            if out["partial_day"] and visits:
                blocks.append(_visit_card(visits, t("visits.title", lang), lang))
            return blocks
        if not visits:
            return [TextBlock(text=t("absence.recorded_none", lang, date=date))]
        return [
            TextBlock(text=t("absence.recorded", lang, date=date)),
            _visit_card(visits, t("visits.title", lang), lang),
            TextBlock(text=t("absence.scope_question", lang)),
            QuickRepliesBlock(
                options=[t("absence.scope_all", lang), t("absence.scope_morning", lang)]
            ),
        ]
    if part.tool_name == "get_my_visits":
        if not out["visits"]:
            return [TextBlock(text=t("visits.none", lang))]
        title = t("visits.title", lang)
        return [
            TextBlock(text=t("visits.of", lang, name=out["person"])),
            _visit_card(out["visits"], title, lang),
        ]
    if part.tool_name == "find_replacements":
        v = out["visit"]
        params = {"location": v["location"], "date": _fmt_date(v["date"], lang), "time": v["start"]}
        if not out["candidates"]:
            return [TextBlock(text=t("cover.none", lang, **params))]
        fields = [
            CardField(label=c["name"], value="; ".join(c["reasons"])) for c in out["candidates"]
        ]
        options = [t("cover.assign", lang, name=c["name"].split()[0]) for c in out["candidates"]]
        return [
            TextBlock(text=t("cover.intro", lang, **params)),
            CardBlock(title=t("cover.title", lang, **params), fields=fields),
            QuickRepliesBlock(options=options),
        ]
    if part.tool_name == "assign_cover":
        v = out["visit"]
        params = {
            "name": out["candidate"],
            "location": v["location"],
            "date": _fmt_date(v["date"], lang),
            "time": v["start"],
        }
        if out["status"] == "awaiting_approval":
            return [
                TextBlock(text=t("assign.override", lang, **params)),
                ApprovalCardBlock(
                    approval_id=out["approval_id"],
                    title=t("approval.card_title", lang),
                    summary=t("assign.override", lang, **params),
                    fields=[CardField(label=t("field.person", lang), value=out["candidate"])],
                    status="pending",
                ),
            ]
        key = "assign.waiting_quiet" if out["stage"] == "waiting_quiet" else "assign.asking"
        return [TextBlock(text=t(key, lang, **params))]
    if part.tool_name == "respond_to_cover":
        if not out["accepted"]:
            return [TextBlock(text=t("respond.declined", lang))]
        v = out["visit"]
        params = {"location": v["location"], "date": _fmt_date(v["date"], lang), "time": v["start"]}
        return [TextBlock(text=t("respond.accepted", lang, **params))]
    return [TextBlock(text=t("fallback.help", lang))]


def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """FunctionModel entry point."""
    today, default_lang = _context(info)
    text = _last_user_text(messages)
    lang = detect_language(text, default_lang)
    last = messages[-1]
    output_tools = {tool.name for tool in info.output_tools}
    if isinstance(last, ModelRequest) and not any(
        isinstance(p, UserPromptPart) for p in last.parts
    ):
        returns = [
            p
            for p in last.parts
            if isinstance(p, ToolReturnPart) and p.tool_name not in output_tools
        ]
        if returns:
            blocks: list[Block] = []
            for part in returns:
                blocks.extend(compose(part, lang))
            return _final(info, blocks)
    return decide(classify(text, today, default_lang), messages, info)


async def respond_stream(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[DeltaToolCalls]:
    """Streaming entry point (AG-UI): the same decision, delivered as tool call deltas."""
    response = respond(messages, info)
    for index, part in enumerate(response.parts):
        if isinstance(part, ToolCallPart):
            yield {index: DeltaToolCall(name=part.tool_name, json_args=part.args_as_json_str())}


def rules_model() -> FunctionModel:
    return FunctionModel(respond, stream_function=respond_stream, model_name="dispatcher-rules")
