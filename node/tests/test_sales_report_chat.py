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
from tests.conftest import RS_TODAY, single_kiosks
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
    """D49 and round 1: Pao at the Street stall gets her own kiosk, named in the head, with no
    Save button (M1); the model reads only her kiosk (L4), so the Mall kiosk is not among the
    choices and the reply says which kiosk it read (M2); a form naming the Mall kiosk anyway is
    refused by the report tool's rbac."""
    pao = chat[1]["Pao"]
    _rephrase(monkeypatch)
    reply = _turn(session, pao, WEEK)
    form = ReportForm(measure="amount", period="last_week", group_by="item")
    assert _first(reply) == _table(session, pao, form)
    assert "(Street stall)" in _first(reply).split("\n")[0]
    assert not _has_buttons(reply)  # a clerk gets the answer without Save
    street = session.exec(select(Branch).where(Branch.name == "Street stall")).one()
    assert pao.branch_id == street.id
    named = _turn(session, pao, "benta last week Mall kiosk", reply.thread_id)
    assert "(Street stall)" in _first(named) and "Mall" not in _first(named)
    mall = chat[0]
    forged = ReportForm(measure="amount", period="last_week", kiosks=[mall.id])
    monkeypatch.setattr(report_model, "_fake_answer", lambda text, kiosks: Answer(form=forged))
    refused = _turn(session, pao, "benta last week sa kabila", reply.thread_id)
    assert refused.text() == t("denied.generic", "en")


def test_the_model_reads_only_the_kiosks_the_person_may_read(
    session: Session, chat: Ferinos
) -> None:
    """Round 1 (L4, spec 4c): a clerk's context names her kiosk only; the owner's every shop."""
    people = chat[1]
    pao = turn._report_context(_deps(session, people["Pao"]))
    assert list(pao.kiosks.values()) == ["Street stall"]
    rosa = dataclasses.replace(
        _deps(session, people["Rosa"]),
        actor=Actor.person(people["Rosa"]).as_agent("agent.sales_supervisor"),
    )
    assert set(turn._report_context(rosa).kiosks.values()) == {"Mall kiosk", "Street stall"}


def test_the_owner_asks_across_kiosks_and_a_supervisor_is_refused(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    single_kiosks(session)  # D50: no supervisor is assigned to the other kiosk here
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
    single_kiosks(session)  # D50: no supervisor is assigned to the other kiosk here
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


def test_a_saved_report_never_outranks_a_taught_phrase(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 1 (M1): a phrase the owner taught for the same key wins over a saved report."""
    rosa = chat[1]["Rosa"]
    jev: list[dict[str, Any]] = []
    _rephrase(monkeypatch, jev)
    first = _turn(session, rosa, WEEK)
    _turn(session, rosa, t("sales.report.save", "en"), first.thread_id)
    phrases.teach(session, Actor.person(rosa), None, WEEK, "sales_supervisor", "sales_today",
                  roles=["owner"])  # fmt: skip
    asked = len(jev)
    _answers(monkeypatch, "sales_today", jev, period="today")
    again = _turn(session, rosa, WEEK)
    assert len(jev) == asked + 1  # Jev decided; the saved form did not run first
    assert _first(again) != _first(first)


def test_a_saved_report_routes_as_a_tap_never_a_switch(session: Session, chat: Ferinos) -> None:
    """Round 1 (M1): with another agent active a saved report key never switches to sales;
    with none active it is chosen, as a learned tap is."""
    from mia.agents.registry import AGENTS
    from mia.chat import service

    rosa = chat[1]["Rosa"]
    form = ReportForm(measure="amount", period="last_week").model_dump(mode="json")
    message = Message(thread_id="t", role="user", text=WEEK)
    phrases.save_report(session, Actor.person(rosa), rosa.branch_id, message, form)
    session.commit()
    deps = _deps(session, rosa)
    agents = [AGENTS["sales_supervisor"], AGENTS["inventory_manager"]]
    assert service._taught(session, deps, WEEK, agents, "inventory_manager") is None
    chosen = service._taught(session, deps, WEEK, agents, None)
    assert chosen is not None and (chosen.kind, chosen.agent_id) == ("chosen", "sales_supervisor")


def test_owners_and_admins_retire_a_saved_report_in_the_chat(
    session: Session, chat: Ferinos, model: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 1 (L3): "remove report <words>" by the owner; a supervisor or clerk is denied."""
    people = chat[1]
    _rephrase(monkeypatch)
    first = _turn(session, people["Rosa"], WEEK)
    _turn(session, people["Rosa"], t("sales.report.save", "en"), first.thread_id)
    command = "remove report Benta last week per item"
    assert _turn(session, people["Marites"], command).text() == t("denied.generic", "en")
    assert _turn(session, people["Ana"], command).text() == t("denied.generic", "en")
    assert phrases.saved_report(session, people["Rosa"].branch_id, key_of(WEEK)) is not None
    done = _turn(session, people["Rosa"], command)
    assert done.text() == t("sales.report.retired", "en")
    assert phrases.saved_report(session, people["Rosa"].branch_id, key_of(WEEK)) is None
    again = _turn(session, people["Rosa"], command)
    assert again.text() == t("sales.report.not_found", "en")


def test_owners_and_admins_retire_a_saved_report_in_the_app(
    session: Session, chat: Ferinos
) -> None:
    """Round 1 (L3): GET /reports and POST /reports/retire, owner and admin only."""
    from fastapi.testclient import TestClient

    from mia.api.main import app

    people = chat[1]
    rosa = people["Rosa"]
    form = ReportForm(measure="amount", period="last_week").model_dump(mode="json")
    message = Message(thread_id="t", role="user", text=WEEK)
    phrases.save_report(session, Actor.person(rosa), rosa.branch_id, message, form)
    session.commit()
    client = TestClient(app)
    owner = {"x-mia-actor": rosa.id}
    supervisor = {"x-mia-actor": people["Marites"].id}
    assert client.get("/reports", headers=supervisor).status_code == 403
    (row,) = client.get("/reports", headers=owner).json()
    assert row["key"] == key_of(WEEK) and row["form"] == form
    body = {"key": "Benta last week per item"}
    assert client.post("/reports/retire", json=body, headers=supervisor).status_code == 403
    assert client.post("/reports/retire", json=body, headers=owner).status_code == 200
    assert client.post("/reports/retire", json=body, headers=owner).status_code == 404
    session.expire_all()
    assert phrases.saved_report(session, rosa.branch_id, key_of(WEEK)) is None


def test_import_skips_an_invalid_report_row(
    session: Session, chat: Ferinos, tmp_path: Path
) -> None:
    """Round 1 (L3): `mia phrases import` validates each form and skips a bad row."""
    rosa = chat[1]["Rosa"]
    good = json.dumps({"measure": "amount", "period": "last_week"})
    bad = json.dumps({"measure": "amount", "period": "last_week", "total": 999})
    with (tmp_path / phrases.REPORTS_CSV).open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerows([["text", "key", "form"], ["Benta last week", "benta last week", good],
                          ["Total!", "total", bad], ["Broken", "broken", "{not json"]])  # fmt: skip
    assert phrases.import_rows(session, tmp_path, rosa.branch_id) == 1
    assert phrases.saved_report(session, rosa.branch_id, "total") is None


def test_no_write_lock_is_held_while_the_report_reads(
    session: Session, chat: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 1 (L2, rule 11): the report read runs with every write committed."""
    import sqlite3

    from mia.agents.sales_supervisor import report as report_form

    free: list[bool] = []
    real = report_form.run

    def probe(*args: Any, **kw: Any) -> Any:
        other = sqlite3.connect(get_settings().MIA_DB_PATH, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
            free.append(True)
        except sqlite3.OperationalError:
            free.append(False)
        finally:
            other.close()
        return real(*args, **kw)

    monkeypatch.setattr(report_form, "run", probe)
    _rephrase(monkeypatch)
    _turn(session, chat[1]["Rosa"], "benta last week per kiosk")
    assert free == [True]
