"""Report questions, Task 3 (plan 2026-10-24-report-questions, teach-Mia 4c, D49): the chat
wiring, the reply table, the code-built clarify buttons, save and reuse. Fake Jev, the fake
report model (MIA_REPORT_MODEL=test), English."""

import csv
import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import Session, select

from mia.agents.base import AgentDeps
from mia.agents.sales_supervisor import replies, report_model, tools, turn
from mia.agents.sales_supervisor.report import ReportForm
from mia.agents.sales_supervisor.report_model import Answer, ReportClarify
from mia.agents.sales_supervisor.tools import ReportInput
from mia.chat import phrases
from mia.chat.blocks import ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.route_memory import key_of
from mia.core.models import Actor, Branch, EgressLog, Event, Message, Person, Thread
from mia.core.rbac import Rbac, Resource
from mia.i18n import t
from mia.settings import get_settings
from tests.conftest import RS_TODAY
from tests.evals.cases import FOLDER
from tests.test_sales_chat import _answers, _buttons, _only_sales, _turn
from tests.test_sales_tools import deps_for

Ferinos = tuple[Branch, dict[str, Person]]
WEEK = "benta last week per item"


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch, rs_en: Ferinos) -> Ferinos:
    """Jev mode, the sales supervisor the only agent, the fake report model, English."""
    _only_sales(monkeypatch)
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    monkeypatch.setenv("MIA_SALES_QUESTION", "choice")
    monkeypatch.setenv("MIA_REPORT_MODEL", "test")
    get_settings.cache_clear()
    return rs_en


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The messages the fake report model read."""
    seen: list[str] = []
    real = report_model._fake_answer

    def spy(text: str, kiosks: dict[str, str]) -> Answer:
        seen.append(text)
        return real(text, kiosks)

    monkeypatch.setattr(report_model, "_fake_answer", spy)
    return seen


def _rephrase(monkeypatch: pytest.MonkeyPatch, seen: list[dict[str, Any]] | None = None) -> None:
    """Jev unsure with nothing to offer: today's "rephrase"."""
    _answers(monkeypatch, "sales_today", seen, confidence=0.3, probabilities={"sales_today": 0.03})


def _deps(session: Session, person: Person) -> AgentDeps:
    return dataclasses.replace(deps_for(session, person), today=RS_TODAY)


def _table(session: Session, person: Person, form: ReportForm) -> str:
    out = tools.report(_deps(session, person), ReportInput(form=form), "c")
    (block,) = replies.report_text(out.result, "en")
    assert isinstance(block, TextBlock)
    return block.text


def _report_rows(session: Session) -> list[EgressLog]:
    stmt = select(EgressLog).where(EgressLog.purpose == report_model.PURPOSE)
    return list(session.exec(stmt).all())


def _first(reply: ChatReply) -> str:
    block = reply.blocks[0]
    assert isinstance(block, TextBlock)
    return block.text


def _has_buttons(reply: ChatReply) -> bool:
    return any(isinstance(b, QuickRepliesBlock) for b in reply.blocks)


def test_the_step_is_off_without_a_route(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIA_REPORT_MODEL", "")
    get_settings.cache_clear()
    _rephrase(monkeypatch)
    reply = _turn(session, chat[1]["Rosa"], WEEK)
    assert reply.text() == t("clarify.rephrase", "en") and model == []


def test_a_report_question_gets_the_table(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rosa = chat[1]["Rosa"]
    _rephrase(monkeypatch)
    reply = _turn(session, rosa, WEEK)
    form = ReportForm(measure="amount", period="last_week", group_by="item")
    assert _first(reply) == _table(session, rosa, form)
    assert _buttons(reply) == [t("sales.report.save", "en")]
    assert model == [WEEK]
    made = session.exec(select(Event).where(Event.action == "tool.called")).all()
    assert any(e.entity_id == "sales_supervisor.report" for e in made)  # through the guard


def test_a_reply_only_other_on_a_report_question_runs_the_step(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(monkeypatch, "reply_only", conversation="other")
    reply = _turn(session, chat[1]["Rosa"], "how much gcash this month")
    form = ReportForm(measure="amount", period="this_month", tenders=["gcash"])
    assert _first(reply) == _table(session, chat[1]["Rosa"], form)


def test_a_clerk_gets_her_own_kiosk_and_never_another(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D49: Pao at the Street stall asks about her own kiosk; naming the Mall kiosk is
    refused by the report tool's rbac."""
    pao = chat[1]["Pao"]
    _rephrase(monkeypatch)
    reply = _turn(session, pao, WEEK)
    form = ReportForm(measure="amount", period="last_week", group_by="item")
    assert _first(reply) == _table(session, pao, form)
    street = session.exec(select(Branch).where(Branch.name == "Street stall")).one()
    assert pao.branch_id == street.id
    refused = _turn(session, pao, "benta last week Mall kiosk", reply.thread_id)
    assert refused.text() == t("denied.generic", "en") and len(model) == 2


def test_the_owner_asks_across_kiosks_and_a_supervisor_is_refused(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    people = chat[1]
    _rephrase(monkeypatch)
    reply = _turn(session, people["Rosa"], "benta last week per kiosk")
    form = ReportForm(measure="amount", period="last_week", group_by="kiosk")
    assert _first(reply) == _table(session, people["Rosa"], form)
    assert "Street stall" in _first(reply) and "Mall kiosk" in _first(reply)
    denied = _turn(session, people["Marites"], "benta last week per kiosk")
    assert denied.text() == t("denied.generic", "en")


def test_a_person_without_the_report_tool_calls_no_model(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = Rbac.check

    def check(self: Rbac, actor: Actor, resource: Resource, action: str, **kw: Any) -> bool:
        if resource.name == "sales_supervisor.report":
            return False
        return real(self, actor, resource, action, **kw)

    monkeypatch.setattr(Rbac, "check", check)
    _rephrase(monkeypatch)
    reply = _turn(session, chat[1]["Ana"], WEEK)
    assert reply.text() == t("clarify.rephrase", "en")
    assert model == [] and _report_rows(session) == []


def test_a_counts_message_never_reaches_the_step(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _rephrase(monkeypatch)
    _turn(session, chat[1]["Ana"], "3 ube 2 classic cash")
    assert model == []


def test_something_else_after_a_report_like_message_runs_the_step(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rosa = chat[1]["Rosa"]
    split = {"sales_today": 0.5, "sales_period": 0.45}
    _answers(monkeypatch, "sales_today", confidence=0.5, probabilities=split)
    asked = _turn(session, rosa, WEEK)
    assert model == []  # a Did you mean has buttons: no report step yet
    other = t("clarify.something_else", "en")
    assert _buttons(asked)[-1] == other
    reply = _turn(session, rosa, other, asked.thread_id)
    form = ReportForm(measure="amount", period="last_week", group_by="item")
    assert _first(reply) == _table(session, rosa, form) and model == [WEEK]


def test_egress_none_keeps_todays_reply(
    session: Session, chat: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tapped Something else needs no Jev request, so only the report step meets egress."""
    rosa = chat[1]["Rosa"]
    split = {"sales_today": 0.5, "sales_period": 0.45}
    _answers(monkeypatch, "sales_today", confidence=0.5, probabilities=split)
    asked = _turn(session, rosa, WEEK)
    monkeypatch.setenv("MIA_REPORT_MODEL", "gateway/report")
    monkeypatch.setenv("MIA_EGRESS_LEVEL", "none")
    get_settings.cache_clear()
    reply = _turn(session, rosa, t("clarify.something_else", "en"), asked.thread_id)
    assert reply.text() == t("clarify.rephrase", "en") and _report_rows(session) == []


def test_a_clarify_answer_gets_code_built_buttons(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rosa = chat[1]["Rosa"]
    _rephrase(monkeypatch)
    asked = _turn(session, rosa, "benta per item")
    assert _first(asked) == t("sales.report.ask.which_period", "en")
    labels = [t(f"sales.report.period.{p}", "en") for p in turn.NAMED_PERIODS]
    assert _buttons(asked) == labels
    reply = _turn(session, rosa, t("sales.report.period.last_week", "en"), asked.thread_id)
    form = ReportForm(measure="amount", period="last_week", group_by="item")
    assert _first(reply) == _table(session, rosa, form) and len(model) == 1


def test_a_second_clarify_is_a_rephrase(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rosa = chat[1]["Rosa"]
    _rephrase(monkeypatch)
    asked = _turn(session, rosa, "benta per item")
    said = session.exec(select(Message).where(Message.text == "benta per item")).one()
    thread = session.get(Thread, asked.thread_id)
    assert thread is not None
    deps = dataclasses.replace(
        _deps(session, rosa), actor=Actor.person(rosa).as_agent("agent.sales_supervisor")
    )
    again = Answer(clarify=ReportClarify(question="which_measure", partial={"period": "today"}))
    reply = turn._report_reply(session, deps, thread, again, said.id)
    assert reply.text() == t("clarify.rephrase", "en")


def test_a_saved_report_runs_with_no_model_call(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rosa = chat[1]["Rosa"]
    jev: list[dict[str, Any]] = []
    _rephrase(monkeypatch, jev)
    first = _turn(session, rosa, WEEK)
    saved = _turn(session, rosa, t("sales.report.save", "en"), first.thread_id)
    assert saved.text() == t("sales.report.saved", "en")
    (ev,) = session.exec(select(Event).where(Event.action == phrases.REPORT_SAVED)).all()
    assert (ev.after or {})["key"] == key_of(WEEK)
    rows, asked = len(_report_rows(session)), len(jev)
    again = _turn(session, rosa, "Benta last week per item!")
    assert _first(again) == _first(first)
    assert not _has_buttons(again)  # already saved
    assert len(model) == 1 and len(jev) == asked and len(_report_rows(session)) == rows


def test_a_saved_report_checks_the_new_askers_rights(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    people = chat[1]
    _rephrase(monkeypatch)
    first = _turn(session, people["Rosa"], "benta last week per kiosk")
    _turn(session, people["Rosa"], t("sales.report.save", "en"), first.thread_id)
    reply = _turn(session, people["Marites"], "benta last week per kiosk")
    assert reply.text() == t("denied.generic", "en") and len(model) == 1


def test_explicit_dates_offer_no_save(
    session: Session, chat: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    dated = ReportForm(measure="amount", start=RS_TODAY.replace(day=1), end=RS_TODAY)
    monkeypatch.setattr(report_model, "_fake_answer", lambda text, kiosks: Answer(form=dated))
    _rephrase(monkeypatch)
    reply = _turn(session, chat[1]["Rosa"], "benta since the first")
    assert _first(reply) == _table(session, chat[1]["Rosa"], dated)
    assert not _has_buttons(reply)


def test_a_bad_form_is_a_rephrase_and_a_failed_decision(
    session: Session, chat: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    long = ReportForm(measure="pieces", period="today", group_by="tender")  # combo
    monkeypatch.setattr(report_model, "_fake_answer", lambda text, kiosks: Answer(form=long))
    _rephrase(monkeypatch)
    reply = _turn(session, chat[1]["Rosa"], "ilan per tender today")
    assert reply.text() == t("clarify.rephrase", "en")
    failed = session.exec(select(Event).where(Event.action == "decision.failed")).all()
    assert [(e.after or {})["error"] for e in failed] == ["report: combo"]


def test_saved_report_rows_are_valid_forms() -> None:
    with (FOLDER / phrases.REPORTS_CSV).open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["text", "key", "form"]
        for row in reader:
            assert key_of(row["text"]) == row["key"], row
            form = ReportForm.model_validate(json.loads(row["form"]))
            assert form.period is not None, row  # only a named period is saved


def test_saved_reports_export_and_import(session: Session, chat: Ferinos, tmp_path: Path) -> None:
    rosa = chat[1]["Rosa"]
    form = ReportForm(measure="pieces", period="last_week").model_dump(mode="json")
    message = Message(thread_id="t", role="user", text="Ilan last week?")
    before = phrases.version(session, rosa.branch_id)
    phrases.save_report(session, Actor.person(rosa), rosa.branch_id, message, form)
    session.commit()
    assert phrases.version(session, rosa.branch_id) == before + 1
    assert phrases.export_rows(session, tmp_path) == 1
    assert phrases.export_rows(session, tmp_path) == 0  # already there
    (row,) = list(csv.DictReader((tmp_path / phrases.REPORTS_CSV).open(encoding="utf-8")))
    assert (row["text"], row["key"], json.loads(row["form"])) == (
        "Ilan last week?",
        "ilan last week",
        form,
    )
    phrases.retire_report(session, Actor.person(rosa), rosa.branch_id, "ilan last week")
    assert phrases.saved_report(session, rosa.branch_id, "ilan last week") is None
    assert phrases.import_rows(session, tmp_path, rosa.branch_id) == 1
    assert phrases.import_rows(session, tmp_path, rosa.branch_id) == 0
    assert phrases.saved_report(session, rosa.branch_id, "ilan last week") == form
    last = session.exec(select(Event).where(Event.action == phrases.REPORT_SAVED)).all()[-1]
    assert last.actor_type == "system"
    assert phrases.entries(session, rosa.branch_id) == []  # a saved report is no phrase
