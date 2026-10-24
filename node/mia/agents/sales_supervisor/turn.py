"""The sales supervisor's answer to one chat turn. Jev picks the action (MIA_DECIDER=jev), code
runs the tool and words the reply; there is no LLM agent and no classifier route. The
emergency script runs before this, in chat.service, for every agent."""

import asyncio
import html
import logging
import re
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, AgentSpec, Turn, call_tool
from mia.agents.decider import (
    THRESHOLD,
    Alternative,
    Decision,
    SlotReader,
    ask_slot,
    remember_slot,
    slot_answer,
)
from mia.agents.parsing import (
    RECEIPT_WORDS,
    REFUND_WORDS,
    VOID_WORDS,
    receipt_no_only,
    said,
    tender_only,
)
from mia.agents.sales_supervisor import MANIFEST, actions, decider, due, replies, report_model
from mia.agents.sales_supervisor.report import ReportForm
from mia.agents.sales_supervisor.report_model import Answer
from mia.agents.sales_supervisor.tools import (
    BINDINGS,
    COUNTS,
    RecordCountsOutput,
    RecordReceiptOutput,
    RefundReceiptInput,
    ReportInput,
    ReportOutput,
    at_visit,
    receipt_out,
    refund_lines,
)
from mia.agents.shift_supervisor.classifier import classify
from mia.chat import phrases
from mia.chat.blocks import Block, ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import reply_text, store_reply
from mia.chat.route_memory import key_of
from mia.core import events, sales
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError, JevUnreachable
from mia.core.models import Actor, Approval, Branch, Event, Message, SalesReceipt, Thread
from mia.core.rbac import Resource, get_rbac
from mia.i18n import t
from mia.settings import get_settings
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailItem

log = logging.getLogger(__name__)
_BINDINGS = {b.tool_id: b for b in BINDINGS}
_warned = False  # the no-Jev warning is logged once per process
RECEIPT_TOOLS = ("void_receipt", "refund_receipt")
# Internal actions, never in actions.ACTIONS (Jev never sees them, never teachable): a report
# form run by the report tool, and the Save as a report button (teach-Mia 4c).
REPORT = "report"
REPORT_SAVE = "report_save"
REPORT_RETIRE = "report_retire"
SAVE_RIGHT = Resource(kind="tool", name=f"{MANIFEST.id}.period_report")  # supervisors and up
RETIRE_COMMAND = re.compile(r"^\s*remove report\s+(.+)$", re.IGNORECASE)
REPORT_TOOL = Resource(kind="tool", name=f"{MANIFEST.id}.report")
NAMED_PERIODS = ("today", "yesterday", "this_week", "last_week", "this_month", "last_month")
# a void's or refund's refusal code -> its reply (each takes the receipt number as no)
RECEIPT_REFUSALS = {
    "receipt": "sales.void.no_receipt",
    "status": "sales.void.already",
    "kind": "sales.void.refund_kind",
    "refunded": "sales.void.refunded",
    "session_closed": "sales.void.closed",
    "quantity": "sales.refund.too_much",
    "refunded_line": "sales.refund.too_much",
    "approved_amount": "sales.refund.too_much",
    "counts_kiosk": "sales.receipts.counts_kiosk",
    "refund_of": "sales.refund.not_refundable",
    "needs_drawer": "sales.refund.needs_drawer",
}


def _last_question(session: Session, thread: Thread) -> Message | None:
    """The thread's last Mia message, questions included (chat.service._last_mia)."""
    from mia.chat.service import _last_mia  # chat.service imports the registry, so this module

    return _last_mia(session, thread, questions=True)


def _tapped(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Decision | None:
    """The stored decision behind a tapped button (Did you mean, which item), if
    text is one. A button only counts while its question is the thread's last Mia message and
    was asked today in the branch's time zone."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "decision.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = _last_question(session, thread)
    if asked is None or last is None or (asked.after or {}).get("message_id") != last.id:
        return None
    if asked.timestamp.astimezone(ZoneInfo(deps.branch.timezone)).date() != deps.today:
        return None
    chosen = ((asked.after or {}).get("options") or {}).get(text.strip())
    return Decision.model_validate(chosen) if chosen else None


def _receipt_no(text: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """A void's or refund's receipt number from a typed answer ("2", "#2", "resibo 2"). A
    refund that named no counted item is completed only when its message said nothing but the
    refund word (else an item named without a count could become the whole sale: Jev decides
    with the question as context, and the refund rules ask)."""
    no = receipt_no_only(text)
    words = set(said(str(args.get("reason", "")))) - VOID_WORDS - REFUND_WORDS - RECEIPT_WORDS
    if no is None or ("items" in args and not args["items"] and words):
        return None
    return {**args, "receipt_no": no}


def _tender(text: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """A receipt's tender from a typed answer that names only one ("cash", "GCash")."""
    tender = tender_only(text)
    return None if tender is None else {**args, "tender": tender}


# the missing inputs a typed answer to Mia's question completes (decider.slot_answer)
SLOT_READERS: dict[str, SlotReader] = {"receipt_no": _receipt_no, "tender": _tender}


def _said(session: Session, thread: Thread) -> str | None:
    """The id of the thread's latest user message (this turn's, stored before the turn)."""
    return session.exec(
        select(Message.id)
        .where(Message.thread_id == thread.id)
        .where(Message.role == "user")
        .order_by(col(Message.id).desc())
    ).first()


def _saved_form(session: Session, deps: AgentDeps, text: str) -> dict[str, Any] | None:
    """The saved report form for the message's key, unless a phrase taught for that key at the
    branch outranks it (a saved report counts as a tap, never as a teach)."""
    key = key_of(text)
    if any(p.key == key and p.taught for p in phrases.entries(session, deps.branch.id)):
        return None
    return phrases.saved_report(session, deps.branch.id, key)


def _query(
    session: Session, deps: AgentDeps, thread: Thread, text: str
) -> tuple[Decision | None, actions.Query | None]:
    """A decision already made (a tapped button, an injection, a typed answer that fills the
    missing input Mia asked for), or the query for Jev."""
    tapped = _tapped(session, deps, thread, text)
    if tapped is not None:
        return tapped, None
    if classify(html.unescape(text), deps.today, deps.lang).injection:
        return Decision(action="reply_only", args={"kind": "injection"}, confidence=1), None
    answered = slot_answer(session, deps, thread, text, SLOT_READERS)
    if answered is not None:
        return answered, None
    retire = RETIRE_COMMAND.match(html.unescape(text))
    if retire is not None:
        key = key_of(retire[1])
        return Decision(action=REPORT_RETIRE, args={"key": key}, confidence=1.0), None
    saved = _saved_form(session, deps, text)
    if saved is not None:  # a saved report runs with no Jev and no model request
        return Decision(action=REPORT, args={"form": saved}, confidence=1.0), None
    last = _last_question(session, thread)  # a notification (the why question) counts
    said = _said(session, thread)
    previous, previous_id = (last.text, last.id) if last else ("", None)
    query = actions.build_query(deps, text, previous, message_id=said, previous_id=previous_id)
    return None, query


def _ask(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    blocks: list[Block],
    options: replies.Options,
) -> ChatReply:
    """Store a question with buttons and remember what each button runs."""
    reply = store_reply(session, deps, thread, blocks)
    after = {"options": options, "message_id": reply.message_id}
    events.emit(session, "decision.clarify_asked", ("thread", thread.id), None, after, deps.actor)
    return reply


def _only_ring_up(decision: Decision) -> Alternative | None:
    """The one offerable alternative when it is record_receipt (a complete one), else None."""
    offers = [a for a in decision.alternatives if a.missing is None and a.action in actions.ACTIONS]
    return offers[0] if len(offers) == 1 and offers[0].action == "record_receipt" else None


def _did_you_mean(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply:
    """Ask "Did you mean" with one button per offerable alternative plus Something else; with
    none, ask to rephrase."""
    options: replies.Options = {}
    for alt in decision.alternatives:
        spec = actions.ACTIONS.get(alt.action)
        if spec is None or spec.label_key is None or alt.missing is not None:
            continue
        label = t(spec.label_key, deps.lang)
        if label not in options:
            chosen = Decision(action=alt.action, args=alt.args, confidence=alt.probability)
            options[label] = chosen.model_dump(mode="json")
    if not options:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    other = t("clarify.something_else", deps.lang)
    blocks: list[Block] = [
        TextBlock(text=t("clarify.question", deps.lang)),
        QuickRepliesBlock(options=[*options, other]),
    ]
    asked = {"asked": _said(session, thread)}  # the report step reads it (teach-Mia 4c)
    options[other] = Decision(action="clarify", args=asked, confidence=1.0).model_dump(mode="json")
    return _ask(session, deps, thread, blocks, options)


def _ask_item(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision, index: int
) -> ChatReply:
    """Which item a count is, from the candidates the decider kept."""
    count = decision.args["items"][index] if "items" in decision.args else decision.args
    names = {}
    for item_id in count.get("candidates") or []:
        item = session.get(RetailItem, item_id)
        if item is not None:
            names[item.id] = item.name
    if not names:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    blocks, options = replies.ask_item(decision, index, names, deps.lang)
    return _ask(session, deps, thread, blocks, options)


def _refusal(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision, tool: str, out: Any
) -> ChatReply:
    """The reply to a refused tool call: no count to correct, another branch or a target not
    allowed, else denied or rephrase (a stated day other than today or yesterday too)."""
    status, message = out.get("status"), out.get("message")
    if status == "invalid" and tool in RECEIPT_TOOLS and message in RECEIPT_REFUSALS:
        no = str(decision.args.get("receipt_no", ""))
        return reply_text(session, deps, thread, t(RECEIPT_REFUSALS[message], deps.lang, no=no))
    if status == "invalid" and message == "range":  # sales.SalesRangeError
        return reply_text(session, deps, thread, t("sales.refused.range", deps.lang))
    if status == "invalid" and message == "count":
        item = session.get(RetailItem, str(decision.args.get("item_id")))
        name = item.name if item is not None else ""
        return reply_text(session, deps, thread, t("sales.no_count_today", deps.lang, item=name))
    named = decision.args.get("branch_id")
    if status == "denied" and named is not None and named != deps.branch.id:
        branch = deps.branch.name
        return reply_text(
            session, deps, thread, t("sales.not_allowed.branch", deps.lang, branch=branch)
        )
    if status == "denied" and tool == "set_target":
        return reply_text(session, deps, thread, t("sales.not_allowed", deps.lang))
    if status == "denied":
        return reply_text(session, deps, thread, t("denied.generic", deps.lang))
    return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))


def _act(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """Log the decision, then ask what is missing or run its tool through the guard and word
    the reply. A count without an item asks which item; nothing is recorded until each count
    has one."""
    events.emit(
        session,
        "decision.made",
        ("thread", thread.id),
        None,
        decision.model_dump(mode="json"),
        deps.actor,
    )
    if decision.action == REPORT:
        return _report(session, deps, thread, decision)
    if decision.action == REPORT_SAVE:
        return _save_report(session, deps, thread, decision)
    if decision.action == REPORT_RETIRE:
        return _retire_report(session, deps, thread, str(decision.args.get("key", "")))
    action = decision.action
    item_missing = (decision.missing or "").startswith("item_")
    if action == "clarify" and item_missing and decision.confidence >= THRESHOLD:
        action = decision.raw_action  # the action is clear, one count's item is not
    if (
        action == "clarify"
        and decision.missing in ("receipt_no", "items")
        and decision.raw_action in actions.ACTIONS
        and actions.ACTIONS[decision.raw_action].tool in RECEIPT_TOOLS
        and decision.confidence >= THRESHOLD
    ):
        action = decision.raw_action or action  # the action is clear, its receipt number is not
    if action == "clarify" and decision.missing == "tender":
        if "typed_total" not in decision.args:  # a count: two tenders are sent apart
            return reply_text(session, deps, thread, t("sales.ask.tender", deps.lang))
        if decision.confidence >= THRESHOLD:
            action = decision.raw_action  # a clear receipt: the tender buttons below
    if action == "clarify":
        ring = _only_ring_up(decision)
        if ring is None:
            return _did_you_mean(session, deps, thread, decision)
        # one offer, ringing a sale: ask with its lines, total and tender, not "Did you mean"
        decision = decision.model_copy(update={"args": {**ring.args, "confirm": True}})
        action = ring.action
    spec = actions.ACTIONS.get(action)
    if spec is None:  # a tapped decision of another agent
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    tool = spec.tool
    if tool is None:  # reply_only
        kind = str(decision.args.get("kind", "other"))
        return store_reply(session, deps, thread, replies.conversation_reply(kind, deps.lang))
    on_counts = sales.source_of(deps.branch, deps.today) == "counts"
    if tool in (*RECEIPT_TOOLS, "receipts") and on_counts:
        return reply_text(session, deps, thread, t("sales.receipts.counts_kiosk", deps.lang))
    if tool in RECEIPT_TOOLS and not decision.args.get("receipt_no"):
        which = t("sales.receipt.which_no", deps.lang)
        return ask_slot(session, deps, thread, which, action, decision.args, "receipt_no")
    if tool == "refund_receipt" and decision.missing == "items":  # an item named, no count
        no = str(decision.args["receipt_no"])
        return reply_text(session, deps, thread, t("sales.refund.which_items", deps.lang, no=no))
    index = replies.unknown_item(decision.args)
    if index is not None:
        return _ask_item(session, deps, thread, decision, index)
    if tool == "record_receipt" and decision.args.get("tender") is None:
        blocks, options = replies.ask_tender(decision, deps.lang)
        asked = _ask(session, deps, thread, blocks, options)  # a typed tender answers it too
        remember_slot(session, deps, thread, asked.message_id, action, decision.args, "tender")
        return asked
    binding = _BINDINGS[f"{MANIFEST.id}.{tool}"]
    try:
        args = binding.input_type.model_validate(decision.args)
    except ValidationError:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    out = call_tool(deps, binding, args, new_id())
    if out.get("status") == "approval_required" and tool in RECEIPT_TOOLS:
        return store_reply(session, deps, thread, _asked(session, deps, str(out["approval_id"])))
    if "status" in out and "message" in out:  # a ToolRefusal
        return _refusal(session, deps, thread, decision, tool, out)
    if tool == "record_receipt" and out["status"] == "no_session":
        return reply_text(session, deps, thread, t("sales.receipt.no_session", deps.lang))
    if tool == "record_receipt" and out["status"] in ("total_differs", "confirm"):
        receipt = RecordReceiptOutput.model_validate(out)
        ask = replies.ask_total if out["status"] == "total_differs" else replies.ask_confirm
        blocks, options = ask(decision, receipt, deps.lang)
        return _ask(session, deps, thread, blocks, options)
    if tool == "record_counts" and out["status"] == "total_differs":
        blocks, options = replies.ask_total(
            decision, RecordCountsOutput.model_validate(out), deps.lang
        )
        return _ask(session, deps, thread, blocks, options)
    blocks = replies.tool_reply(tool, out, decision.args, deps.lang)
    if tool == "record_counts" and decision.args.get("as_count"):
        blocks = _as_count(session, deps, str(out["business_date"])) + blocks
    return store_reply(session, deps, thread, blocks)


def _asked(session: Session, deps: AgentDeps, approval_id: str) -> list[Block]:
    """The reply to a void or refund sent for approval, from the approval: the receipt it
    names (its lines and total) for a void, the computed amount for a refund."""
    approval = session.get(Approval, approval_id)
    receipt = session.get(SalesReceipt, approval.subject_id) if approval else None
    assert approval is not None and receipt is not None  # the binding's request wrote both
    if approval.type == sales.VOID:
        return replies.void_asked(receipt_out(session, deps.branch, receipt), deps.lang)
    amount = int(approval.evidence["amount"])
    items = RefundReceiptInput.model_validate(approval.evidence["input"]).items
    lines = refund_lines(session, receipt, items)
    names = {i.id: i.name for i in session.exec(select(RetailItem))}
    shown = [(-x.quantity, names[x.item_id]) for x in lines]
    return replies.refund_asked(receipt.receipt_no, amount, shown, receipt.currency, deps.lang)


AS_COUNT = "sales.as_count_noted"  # marker: the counts-kiosk notice was said (person, date)


def _as_count(session: Session, deps: AgentDeps, day: str) -> list[Block]:
    """The counts-kiosk notice, once per person and business date (an AS_COUNT marker)."""
    events.write_lock(session)  # read the marker and write it in one transaction (rule 11)
    said = session.exec(
        select(Event).where(Event.action == AS_COUNT).where(Event.entity_id == deps.person.id)
    )
    if any((e.after or {}).get("date") == day for e in said):
        return []
    events.emit(session, AS_COUNT, deps.person, None, {"date": day}, deps.actor)
    return [TextBlock(text=t("sales.receipt.as_count", deps.lang))]


# ---- report questions (teach-Mia 4c) ------------------------------------------------------


def _offerable(decision: Decision) -> bool:
    """True when a Did you mean would offer a button (an alternative with a label and all its
    inputs) or the one ring-up question asks instead."""
    for alt in decision.alternatives:
        spec = actions.ACTIONS.get(alt.action)
        if spec is not None and spec.label_key is not None and alt.missing is None:
            return True
    return _only_ring_up(decision) is not None


def _wants_report(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    decision: Decision,
    query: actions.Query | None,
) -> tuple[str, str | None] | None:
    """(the message text, its id) when the report step should run, else None: a route is set,
    the person holds the report tool (checked before any model request), and either Jev's
    decision is today's rephrase (clarify with nothing to offer and no missing input) or a
    reply_only of kind other or capabilities on a report-like message, or the decision is a
    tapped Something else whose asked message is report-like."""
    if report_model.route() is None:
        return None
    if not get_rbac().check(deps.actor, REPORT_TOOL, "execute", session=session):
        return None
    if query is not None:
        rephrase = decision.action == "clarify" and decision.missing is None
        rephrase = rephrase and not _offerable(decision)
        kind = decision.args.get("kind")
        chat = decision.action == "reply_only" and kind in ("other", "capabilities")
        if (rephrase or chat) and actions.report_like(query.message, query.counts_only):
            return query.message, query.message_id
        return None
    asked = decision.args.get("asked") if decision.action == "clarify" else None
    message = session.get(Message, str(asked)) if asked else None
    if message is None or message.thread_id != thread.id:
        return None
    counts = actions.count_shaped(session, deps.branch.id, message.text)
    return (message.text, message.id) if actions.report_like(message.text, counts) else None


def _readable(session: Session, deps: AgentDeps) -> tuple[list[Branch], bool]:
    """The shops the person may read (her own and the kiosks she is assigned to, D50; every
    shop with read_all on sales_counts) and whether All kiosks is offered (read_all, or two or
    more kiosks of her own: "all" is then hers)."""
    wide = get_rbac().check(deps.actor, COUNTS, "read_all", session=session)
    kiosks = deps.kiosks()
    others = [b for b in retail_hours.shops(session, deps.organisation_id) if b != deps.branch]
    shops = [deps.branch, *(b for b in others if wide or b.id in kiosks)]
    return shops, wide or len(shops) > 1


def _report_context(deps: AgentDeps) -> report_model.Context:
    """What the report model reads beside the message (spec 4c): the business date, the menu,
    the kiosks the person may read and the period ids."""
    session = deps.session
    return report_model.Context(
        today=deps.today,
        items={i.id: i.name for i in actions._menu(session, deps.branch.id)},
        kiosks={b.id: b.name for b in _readable(session, deps)[0]},
        periods=actions._periods(deps.lang),
    )


def _reported(session: Session, thread: Thread, message_id: str | None) -> bool:
    """True when a report clarifying question was already asked about the message."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "decision.clarify_asked")
        .where(Event.entity_id == thread.id)
    )
    for ev in asked:
        for option in ((ev.after or {}).get("options") or {}).values():
            if not isinstance(option, dict) or option.get("action") != REPORT:
                continue
            if (option.get("args") or {}).get("message_id") == message_id:
                return True
    return False


def _clarify_options(
    session: Session, deps: AgentDeps, question: str, partial: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """The buttons of a report question, built by code (never the model's words): label to
    the completed form. which_kiosk: the person's kiosk, every shop and All kiosks for one who
    may read every kiosk; which_period: the named periods; which_measure: pieces or amount.
    A completion that is no valid form is left out."""
    lang = deps.lang
    choices: dict[str, dict[str, Any]]
    if question == "which_kiosk":
        shops, wide = _readable(session, deps)
        choices = {b.name: {"kiosks": [b.id]} for b in shops}
        if wide:
            choices[t("sales.report.all_kiosks", lang)] = {"kiosks": ["all"]}
    elif question == "which_period":
        choices = {
            t(f"sales.report.period.{p}", lang): {"period": p, "start": None, "end": None}
            for p in NAMED_PERIODS
        }
    else:
        choices = {
            t(f"sales.report.measure.{m}", lang): {"measure": m} for m in ("pieces", "amount")
        }
    out = {}
    for label, field in choices.items():
        try:
            out[label] = ReportForm.model_validate({**partial, **field}).model_dump(mode="json")
        except ValidationError:
            continue
    return out


def _report_reply(
    session: Session, deps: AgentDeps, thread: Thread, answer: Answer, message_id: str | None
) -> ChatReply:
    """The model's answer worded by code: a form runs through the report tool (_act); a
    clarifying question asks with code-built buttons, once per message (a second one, or one
    with no valid button, gets today's rephrase)."""
    if answer.form is not None:
        form = answer.form.model_dump(mode="json")
        decision = Decision(action=REPORT, args={"form": form, "message_id": message_id},
                            confidence=1.0)  # fmt: skip
        return _act(session, deps, thread, decision)
    assert answer.clarify is not None
    options = _clarify_options(session, deps, answer.clarify.question, answer.clarify.partial)
    if not options or _reported(session, thread, message_id):
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    stored = {
        label: Decision(
            action=REPORT, args={"form": form, "message_id": message_id}, confidence=1.0
        ).model_dump(mode="json")
        for label, form in options.items()
    }
    question = t(f"sales.report.ask.{answer.clarify.question}", deps.lang)
    blocks: list[Block] = [TextBlock(text=question), QuickRepliesBlock(options=list(stored))]
    return _ask(session, deps, thread, blocks, stored)


def _report(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """Run a report form through the report tool (the guard, rule 4) and word the table; a
    named period on a message with a word offers Save as a report. An invalid form gets
    today's rephrase and a decision.failed."""
    try:
        args = ReportInput.model_validate(decision.args)
    except ValidationError:
        return _report_failed(session, deps, thread, "form")
    session.commit()  # rule 11: no write lock held while the report reads (L2)
    out = call_tool(deps, _BINDINGS[f"{MANIFEST.id}.report"], args, new_id())
    if "status" in out and "message" in out:  # a ToolRefusal
        if out["status"] == "invalid":
            error = {"error": f"report: {out['message']}"}
            events.emit(session, "decision.failed", ("thread", thread.id), None, error, deps.actor)
        return _refusal(session, deps, thread, decision, "report", out)
    blocks = replies.report_text(ReportOutput.model_validate(out).result, deps.lang)
    message_id = decision.args.get("message_id")
    message = session.get(Message, str(message_id)) if message_id else None
    savable = args.form.period is not None and message is not None
    savable = savable and phrases.has_letter(key_of(message.text if message else ""))
    if not savable or message is None or not _may_save(session, deps):
        return store_reply(session, deps, thread, blocks)
    label = t("sales.report.save", deps.lang)
    save = {"form": args.form.model_dump(mode="json"), "message_id": message.id}
    options = {
        label: Decision(action=REPORT_SAVE, args=save, confidence=1.0).model_dump(mode="json")
    }
    return _ask(session, deps, thread, [*blocks, QuickRepliesBlock(options=[label])], options)


def _report_failed(session: Session, deps: AgentDeps, thread: Thread, error: str) -> ChatReply:
    after = {"error": f"report: {error}"}
    events.emit(session, "decision.failed", ("thread", thread.id), None, after, deps.actor)
    return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))


def _may_save(session: Session, deps: AgentDeps) -> bool:
    """Supervisors, the owner and admins may save a report (they hold period_report)."""
    return get_rbac().check(deps.actor, SAVE_RIGHT, "execute", session=session)


def _retire_report(session: Session, deps: AgentDeps, thread: Thread, key: str) -> ChatReply:
    """ "remove report <words>": an owner or admin (read_all on sales_counts) withdraws the
    saved report of that key at the branch (report.retired)."""
    if not get_rbac().check(deps.actor, COUNTS, "read_all", session=session):
        return reply_text(session, deps, thread, t("denied.generic", deps.lang))
    if phrases.saved_report(session, deps.branch.id, key) is None:
        return reply_text(session, deps, thread, t("sales.report.not_found", deps.lang))
    phrases.retire_report(session, Actor.person(deps.person), deps.branch.id, key)
    return reply_text(session, deps, thread, t("sales.report.retired", deps.lang))


def _save_report(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply:
    """Save the answered form for its message key (report.saved); anyone who got the answer
    may (it only reads, and rbac is checked again on every run)."""
    message = session.get(Message, str(decision.args.get("message_id")))
    if not _may_save(session, deps):
        return reply_text(session, deps, thread, t("denied.generic", deps.lang))
    if message is None or message.thread_id != thread.id:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    try:
        form = ReportForm.model_validate(decision.args.get("form")).model_dump(mode="json")
        phrases.save_report(session, Actor.person(deps.person), deps.branch.id, message, form)
    except (ValidationError, phrases.TeachError):
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    return reply_text(session, deps, thread, t("sales.report.saved", deps.lang))


def _failed(session: Session, deps: AgentDeps, thread: Thread, error: str) -> ChatReply:
    events.emit(
        session, "decision.failed", ("thread", thread.id), None, {"error": error}, deps.actor
    )
    return reply_text(session, deps, thread, t("reply.unavailable", deps.lang))


async def _jev_turn(
    session: Session, deps: AgentDeps, thread: Thread, text: str, ctx: EgressContext
) -> ChatReply:
    """DB work runs in worker threads; the Jev request runs with no write lock held (the
    query step only reads, and the user message was committed by the chat)."""
    decision, query = await asyncio.to_thread(_query, session, deps, thread, text)
    if decision is None and query is not None:
        await asyncio.to_thread(session.commit)
        try:
            with egress_context(replace(ctx, provider="typesafe", purpose=f"{MANIFEST.id}.decide")):
                decision = await decider.decide(query)
        except JevUnreachable:
            raise  # an outage: the chat defers the turn
        except JevError as exc:
            return await asyncio.to_thread(_failed, session, deps, thread, str(exc))
    assert decision is not None
    wanted = await asyncio.to_thread(_wants_report, session, deps, thread, decision, query)
    if wanted is not None:  # the report step (teach-Mia 4c); None keeps today's reply
        rctx = await asyncio.to_thread(_report_context, deps)
        await asyncio.to_thread(session.commit)
        with egress_context(replace(ctx, purpose=report_model.PURPOSE)):
            answer = await report_model.ask(wanted[0], rctx)
        if answer is not None:
            return await asyncio.to_thread(_report_reply, session, deps, thread, answer, wanted[1])
    return await asyncio.to_thread(_act, session, deps, thread, decision)


def _unavailable(session: Session, deps: AgentDeps, thread: Thread) -> ChatReply:
    global _warned
    if not _warned:
        log.warning("%s answers only with MIA_DECIDER=jev", MANIFEST.id)
        _warned = True
    return reply_text(session, deps, thread, t("reply.unavailable", deps.lang))


async def handle_turn(turn: Turn) -> ChatReply:
    """The sales supervisor's answer to one stored message: a tapped button, Jev's decision
    run through the tool guard, or reply.unavailable without Jev. The caller commits."""
    session, thread = turn.session, turn.thread
    deps = await asyncio.to_thread(at_visit, turn.deps)  # a cover sells at the visit's shop
    if get_settings().MIA_DECIDER != "jev":
        return await asyncio.to_thread(_unavailable, session, deps, thread)
    return await _jev_turn(session, deps, thread, turn.text, turn.ctx)


SPEC = AgentSpec(
    manifest=MANIFEST,
    label_key=f"agent.{MANIFEST.id}.label",
    router_description=(
        "Sales: clerks reporting how many of each item they sold and for how much, corrections to a"
        " reported count (sorry, 4 special not 3), daily, morning and mid-day sales totals, sales"
        " for a past day, week or month, per item or per kiosk (benta kahapon, last week per item,"
        " bawat item, per kiosk), sales"
        " targets, how today compares, the best day, why sales went well, the list of item codes"
        " (the short codes clerks text) with today's prices, and receipts: ringing up a sale (resibo,"
        " r), voiding or refunding a receipt (void, cancel, refund, ibalik) and reading receipts"
        " (receipts today, huling resibo, last receipt); not how much stock is"
        " left, not what to bake, not how a clerk is doing and not advice on how to sell more."
    ),
    handle_turn=handle_turn,
    run_due=due.run_due,
    stream_agent=None,
)
