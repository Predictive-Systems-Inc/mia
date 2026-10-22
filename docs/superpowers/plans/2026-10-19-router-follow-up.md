# Router Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A clerk rarely sees "Is this about" buttons: small talk is answered, the retail case set gates the router, two colliding descriptions are told apart, and Mia remembers what people chose when she asked.

**Architecture:** Three small changes in the chat layer (`chat/agent_router.decide`, a new `chat/route_memory.py` consulted before Jev in `chat/service.route_turn`, one new event emitted on a route tap in `chat/service._choose`), one harvest source in `learning/harvest.py`, two CLI commands, and a rebuilt eval case set. Events are the only memory (rule 2); no schema change.

**Tech Stack:** Python 3.12, SQLModel, Jev through `core/jev.ask` behind `core/egress`, pytest with `tests/jev_fake.py`.

**Spec:** docs/superpowers/specs/2026-10-18-router-follow-up-design.md

## Global Constraints

- All writes through `mia/core` or `mia/templates` services that emit events (rule 1); events are append-only (rule 2). `events.emit(session, action, entity, before, after, actor)` inside the caller's transaction.
- Nothing leaves the node except through `core/egress.py` (rule 6); the learned route makes no request at all.
- User text is data (rule 8): only the chosen agent id is learned, never the text as a rule.
- Rule 11: commit before awaiting any network call. Rule 12: sync DB work in async code via `asyncio.to_thread`; one Session is never used by two threads at once.
- Rule 4: a learned agent must still be in `agents_for(person)`; otherwise the memory is ignored.
- Rule 15: no agent id literal outside manifests, `mia/agents/stubs.py` and test files; `tests/test_architecture.py` enforces it.
- Threshold `THRESHOLD` (0.6) from `mia/agents/shift_supervisor/actions.py`; never a second literal.
- User-facing strings through `mia/i18n` keys in every language of `SUPPORTED = ("fi", "en", "fil", "ceb", "ilo", "hil", "war", "bcl", "pam", "pag")`. New-language modules are machine drafts; `docs/questions.md` Q28 to Q35 cover their review. English and Finnish go in `i18n/strings.py`; the eight others each in their module.
- The language is called Filipino (`fil`), never Tagalog. No em-dashes in code, comments or docs. Docstrings state what a function guarantees.
- Checks before every commit, from the repo root: `uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest`. Use `ruff format node`, never `ruff format .`.
- Tests run offline with `MIA_MODEL=test`; Jev is faked with `tests/jev_fake.py` (`fake_jev`, `choice`, `answers_for`). Router tests set `MIA_DECIDER=jev` and `MIA_TYPESAFE_KEY` as `tests/test_agent_router.py::two_agents` does. The real-Jev eval runs only with `uv run pytest node/tests/evals/test_router_eval.py -m evals` and a key; never in CI.
- Commit messages in the branch's style (`git log -5`): area, colon, what changed for a person, in one or two sentences.

## Review Focus

Behaviour the spec implies but no task's tests cover by default, each pinned to a task below:

1. A learned route for an agent the person can no longer use must be ignored, not raise (Task 4, test `test_a_learned_agent_the_person_lost_is_ignored`).
2. A confident `unclear` with an agent active keeps that agent and does not switch to the lead (Task 1, test `test_a_confident_unclear_keeps_the_active_agent`).
3. Two taps for different agents on the same key never learn either (Task 3, test `test_conflicting_taps_learn_nothing`).
4. `mia forget` must not erase history: a third and fourth tap after a forget learn again (Task 5, test `test_two_new_taps_after_forget_learn_again`).
5. The exact-repeat key must not merge different items: "3 special" and "3 classic" are different keys (Task 3, test `test_digits_normalise_but_words_do_not`).

---

### Task 1: A confident "no agent" is small talk

**Files:**
- Modify: `node/mia/chat/agent_router.py` (`Route.kind`, `decide`)
- Modify: `node/mia/chat/service.py` (`_settle`)
- Test: `node/tests/test_agent_router.py`

**Interfaces:**
- Consumes: `Route(kind, agent_id, confidence)`; `decide(answers, agents, active)`.
- Produces: `Route.kind` gains `"small_talk"`; `decide` returns `Route("small_talk", agents[0].id, confidence)` for a confident `unclear` with no active agent. `_settle` treats `small_talk` like `chosen` (no notice, no switch event).

- [ ] **Step 1: Write the failing tests**

Add to the parametrised decision table in `node/tests/test_agent_router.py` (the `("answer", "p", "active", "expected")` list) these rows:

```python
(("unclear", 0.9, None, ("small_talk", "shift_supervisor")),)
(("unclear", 0.4, None, ("ask", None)),)
(("unclear", 0.9, "sales_supervisor", ("keep", "sales_supervisor")),)
```

and two chat tests next to `test_the_router_is_gated_like_the_decider` (reuse `two_agents`, `_router_answers`, `_turn`; `people["sanna"]` is the person the fixture gives two agents):

```python
def test_small_talk_is_answered_by_the_lead_agent_without_buttons(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch, two_agents: list
) -> None:
    _router_answers(monkeypatch, two_agents, "unclear", 0.9)
    reply = _turn(session, people["sanna"], "good morning!")
    assert not any(isinstance(b, QuickRepliesBlock) for b in reply.blocks)
    assert reply.agent_id == TWO[0]
    assert not session.exec(select(Event).where(Event.action == "chat.agent_switched")).all()
    assert not session.exec(select(Event).where(Event.action == "chat.route_asked")).all()


def test_a_confident_unclear_keeps_the_active_agent(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch, two_agents: list
) -> None:
    _router_answers(monkeypatch, two_agents, TWO[1], 0.95)
    first = _turn(session, people["sanna"], "we sold 12 classic today")
    _router_answers(monkeypatch, two_agents, "unclear", 0.9)
    reply = _turn(session, people["sanna"], "thanks!", first.thread_id)
    assert reply.agent_id == TWO[1]
```

Check `ChatReply` has `agent_id` and `thread_id` (`node/mia/chat/blocks.py`); if the field is named differently, use that name.

- [ ] **Step 2: Run them, expect failure**

`uv run pytest node/tests/test_agent_router.py -k "small_talk or confident_unclear or decision" --no-cov`
Expected: the table rows fail (`ask` instead of `small_talk`), the chat tests fail on the buttons.

- [ ] **Step 3: Implement**

In `agent_router.py`:

```python
class Route:
    kind: Literal["keep", "switch", "chosen", "ask", "small_talk"]
```

In `decide`, replace the final line:

```python
    if active is not None:
        if picked == active or not sure:
            return Route("keep", active, confidence)
        return Route("switch", picked, confidence)
    if picked == UNCLEAR and confidence >= THRESHOLD:
        # a confident "for no agent" is small talk: the lead agent greets back, no buttons
        return Route("small_talk", agents[0].id, confidence)
    return Route("chosen", picked, confidence) if sure else Route("ask", None, confidence)
```

Update the docstring: "The spec's router table plus the follow-up's small-talk row: a confident `unclear` with no active agent goes to the lead agent (agents[0]) with kind small_talk."

In `service._settle` nothing changes if it already branches on `picked.kind == "ask"` and `picked.kind == "switch"` only; confirm `small_talk` falls through to the `chosen` handling (no notice, no event). If `_settle` matches kinds exhaustively, add `small_talk` beside `chosen`.

- [ ] **Step 4: Run the tests, expect pass**

`uv run pytest node/tests/test_agent_router.py --no-cov`

- [ ] **Step 5: Full checks and commit**

```bash
uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest
git add node/mia/chat/agent_router.py node/mia/chat/service.py node/tests/test_agent_router.py
git commit -m "chat: a confident 'for no agent' answer is small talk for the lead agent, not an 'Is this about' question"
```

---

### Task 2: Descriptions that do not collide

**Files:**
- Modify: `node/mia/agents/stubs.py` (`DESCRIPTIONS`)
- Modify: `node/mia/agents/shift_supervisor/turn.py` (`SPEC.router_description`, around line 389)
- Test: `node/tests/test_agent_router.py`

**Interfaces:**
- Produces: the texts below, verbatim. Task 6's eval reads them from the specs.

- [ ] **Step 1: Write the failing test**

```python
def test_router_descriptions_carry_a_contrast_line() -> None:
    """Each description says what it is not, so sales, stock and shifts stay apart."""
    for spec in AGENTS.values():
        assert "; not " in spec.router_description, spec.id
```

- [ ] **Step 2: Run it, expect failure**

`uv run pytest node/tests/test_agent_router.py -k contrast --no-cov`

- [ ] **Step 3: Write the descriptions**

`stubs.py` `DESCRIPTIONS`:

```python
DESCRIPTIONS = {
    "sales_supervisor": (
        "Sales: clerks reporting how many of each item they sold and for how much, daily and"
        " mid-day totals, sales targets, how today compares, why sales went well; not how much"
        " stock is left and not what to bake."
    ),
    "inventory_manager": (
        "Stock: items sold out or running low, how many are left, leftovers and waste at"
        " closing, what to prepare or bake tomorrow, ingredient and supplier orders; not how"
        " many were sold. A sell-out message is stock."
    ),
    "bookkeeper": (
        "Money: the cash count against sales, expenses and receipts, bank deposits, GCash and"
        " Maya settlements, VAT and BIR records; not sales counts and not pay."
    ),
    "hr_officer": (
        "Employment: hours worked, payroll and payslips, 13th month pay, leave balances, SSS,"
        " PhilHealth and Pag-IBIG contributions, hiring; not who works which shift."
    ),
    "branch_manager": (
        "Running the shop: branches, the menu, prices and item short codes, people and their"
        " roles, permits, the weekly summary, coaching and tips for staff; not a day's"
        " counts and not a shift change."
    ),
}
```

`turn.py` `router_description`:

```python
router_description = (
    (
        "Shifts and attendance: rosters and who works when, being sick, late or absent,"
        " finding and answering cover, checking in and out, the day's plan, problems at a"
        " site or the shop, cleaning checklists; not what was sold and not pay."
    ),
)
```

- [ ] **Step 4: Run the tests, expect pass**

`uv run pytest node/tests/test_agent_router.py node/tests/test_architecture.py --no-cov`

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest
git add node/mia/agents/stubs.py node/mia/agents/shift_supervisor/turn.py node/tests/test_agent_router.py
git commit -m "agents: router descriptions say what each agent is not, so sales, stock and shifts stay apart"
```

---

### Task 3: Route memory, the pure part

**Files:**
- Create: `node/mia/chat/route_memory.py`
- Test: `node/tests/test_route_memory.py`

**Interfaces:**
- Produces:
  - `CHOSEN = "chat.route_chosen"`, `FORGOTTEN = "chat.route_forgotten"`, `WINDOW = dt.timedelta(days=90)`, `UNDO_WINDOW = dt.timedelta(hours=1)`, `MIN_TAPS = 2`.
  - `key_of(text: str) -> str`: casefold, whitespace collapsed to one space, trailing `.!?,;:` stripped, every run of digits replaced by `#`.
  - `@dataclass(frozen=True) class Tap: key: str; agent_id: str; at: dt.datetime; thread_id: str; event_id: str` (what a `chat.route_chosen` event gives).
  - `@dataclass(frozen=True) class Switch: key: str; from_agent: str; at: dt.datetime; thread_id: str`.
  - `learned(taps: Sequence[Tap], switches: Sequence[Switch], forgotten: Mapping[str, dt.datetime], now: dt.datetime) -> dict[str, str]`: key to agent id. Pure.
- Rules of `learned`: only taps within `WINDOW` of `now` count; a tap whose key was forgotten at a time after the tap does not count; a tap is undone when a `Switch` with the same key and thread, `from_agent == tap.agent_id`, happens within `UNDO_WINDOW` after it; a key is learned for an agent when at least `MIN_TAPS` counted taps name that agent and no counted tap names another.

- [ ] **Step 1: Write the failing tests**

```python
import datetime as dt

from mia.chat.route_memory import Switch, Tap, key_of, learned

NOW = dt.datetime(2026, 10, 19, 9, tzinfo=dt.UTC)
A, B = "agent_a", "agent_b"  # ids are opaque to the memory


def _tap(key: str, agent: str, days_ago: float = 1, thread: str = "t1", eid: str = "e") -> Tap:
    return Tap(key, agent, NOW - dt.timedelta(days=days_ago), thread, eid)


def test_key_normalises_case_space_punctuation_and_digits() -> None:
    assert key_of("  3 Special,  5 classic!! ") == "# special, # classic"
    assert key_of("Sold 12 Overload") == key_of("sold 7 overload")


def test_digits_normalise_but_words_do_not() -> None:
    assert key_of("3 special") != key_of("3 classic")


def test_one_tap_learns_nothing() -> None:
    assert learned([_tap("k", A)], [], {}, NOW) == {}


def test_two_taps_for_the_same_agent_learn_the_key() -> None:
    assert learned([_tap("k", A), _tap("k", A, 2)], [], {}, NOW) == {"k": A}


def test_conflicting_taps_learn_nothing() -> None:
    taps = [_tap("k", A), _tap("k", A, 2), _tap("k", B, 3)]
    assert learned(taps, [], {}, NOW) == {}


def test_taps_older_than_the_window_do_not_count() -> None:
    assert learned([_tap("k", A, 1), _tap("k", A, 91)], [], {}, NOW) == {}


def test_a_switch_away_within_an_hour_undoes_the_tap() -> None:
    tap = _tap("k", A)
    undo = Switch("k", A, tap.at + dt.timedelta(minutes=30), "t1")
    assert learned([tap, _tap("k", A, 2)], [undo], {}, NOW) == {}


def test_a_switch_after_an_hour_or_in_another_thread_does_not_undo() -> None:
    tap = _tap("k", A)
    late = Switch("k", A, tap.at + dt.timedelta(hours=2), "t1")
    elsewhere = Switch("k", A, tap.at + dt.timedelta(minutes=5), "t2")
    assert learned([tap, _tap("k", A, 2)], [late, elsewhere], {}, NOW) == {"k": A}


def test_forget_discards_taps_before_it_only() -> None:
    old = [_tap("k", A, 5), _tap("k", A, 4)]
    forgotten = {"k": NOW - dt.timedelta(days=3)}
    assert learned(old, [], forgotten, NOW) == {}
    new = [*old, _tap("k", A, 2), _tap("k", A, 1)]
    assert learned(new, [], forgotten, NOW) == {"k": A}
```

- [ ] **Step 2: Run them, expect failure**

`uv run pytest node/tests/test_route_memory.py --no-cov`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
"""What people chose when Mia asked "Is this about": exact repeats are routed by code before
any Jev call (spec 2026-10-18-router-follow-up, decision 4b). This module is pure; the chat
reads the events and applies the result. Only agent ids are learned, never text as a rule
(rule 8)."""

import datetime as dt
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

CHOSEN = "chat.route_chosen"
FORGOTTEN = "chat.route_forgotten"
WINDOW = dt.timedelta(days=90)
UNDO_WINDOW = dt.timedelta(hours=1)
MIN_TAPS = 2

_SPACES = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")


def key_of(text: str) -> str:
    """The memory key of a message: casefolded, one space between words, trailing punctuation
    dropped, every number replaced by # (so each day's counts share one key)."""
    key = _SPACES.sub(" ", text.casefold()).strip().rstrip(".!?,;:").strip()
    return _DIGITS.sub("#", key)


@dataclass(frozen=True)
class Tap:
    key: str
    agent_id: str
    at: dt.datetime
    thread_id: str
    event_id: str


@dataclass(frozen=True)
class Switch:
    key: str
    from_agent: str
    at: dt.datetime
    thread_id: str


def _undone(tap: Tap, switches: Sequence[Switch]) -> bool:
    return any(
        s.key == tap.key
        and s.thread_id == tap.thread_id
        and s.from_agent == tap.agent_id
        and dt.timedelta(0) <= s.at - tap.at <= UNDO_WINDOW
        for s in switches
    )


def learned(
    taps: Sequence[Tap],
    switches: Sequence[Switch],
    forgotten: Mapping[str, dt.datetime],
    now: dt.datetime,
) -> dict[str, str]:
    """Key to agent id for every key with at least MIN_TAPS taps for one agent and none for
    another, counting only taps inside WINDOW, after the key's last forget, and not undone by
    a switch away within UNDO_WINDOW in the same thread."""
    votes: dict[str, Counter[str]] = {}
    for tap in taps:
        if now - tap.at > WINDOW or tap.at <= forgotten.get(tap.key, tap.at - dt.timedelta(1)):
            continue
        if _undone(tap, switches):
            continue
        votes.setdefault(tap.key, Counter())[tap.agent_id] += 1
    return {
        key: next(iter(c))
        for key, c in votes.items()
        if len(c) == 1 and next(iter(c.values())) >= MIN_TAPS
    }
```

- [ ] **Step 4: Run the tests, expect pass**

`uv run pytest node/tests/test_route_memory.py --no-cov`

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest
git add node/mia/chat/route_memory.py node/tests/test_route_memory.py
git commit -m "chat: route memory rules (key of a message, two taps learn, a switch within the hour undoes, forget restarts) as pure code"
```

---

### Task 4: The tap event and the learned route in the chat

**Files:**
- Modify: `node/mia/chat/route_memory.py` (add the query and the apply step)
- Modify: `node/mia/chat/service.py` (`_choose`, `route_turn`)
- Modify: `docs/layout.md` (chat/ line: add `route_memory.py`)
- Test: `node/tests/test_agent_router.py`

**Interfaces:**
- Consumes: Task 3's `learned`, `key_of`, `CHOSEN`, `FORGOTTEN`; `events.emit`; `agents_for`; `active_agent`; `_route_tapped(session, thread, text) -> (agent_id, original_message_id) | None`; `ROUTE_ASKED` events carry `message_id`, `original_message_id`, `options`.
- Produces in `route_memory.py`:
  - `recall(session: Session, branch_id: str, now: dt.datetime) -> dict[str, str]`: reads `chat.route_chosen`, `chat.agent_switched` (joined to the user message's key through the switch's thread and the latest user message before the switch) and `chat.route_forgotten` events of the branch and returns `learned(...)`. One function, sync, called via `asyncio.to_thread`. ponytail comment: a scan of the branch's events per message; cache or index when a branch passes thousands of taps.
  - `remember(session, deps, thread, original_message_id, agent_id, picked, confidence, options, lang)` emits `chat.route_chosen` on the thread with after `{"original_message_id", "agent_id", "picked", "confidence", "options", "lang", "key"}` where `key = key_of(original text)`. Storing the key in the event keeps `recall` free of message reads. (The key is derived data, not the text; the text stays in `chat_messages`.)
- `_choose` gains, after the tap branch returns its agent: a call to `remember`. To know `picked` and `confidence`, `_ask_route` stores them in the `chat.route_asked` event's `after` (`"picked"`, `"confidence"`), passed in from `_settle` (which has `picked`). When the ask came from a fallback (no Jev), both are `None`.
- `route_turn`: after `_choose` returns `spec is None` (the router would decide), and before the gate and the Jev call: `memory = await asyncio.to_thread(route_memory.recall, session, deps.branch.id, deps.now)`; `hit = memory.get(key_of(text))`; if `hit` is in `{a.id for a in agents}` (rule 4) and `hit != active`: `picked = Route("switch" if active else "chosen", hit, 1.0)` and go to `_settle` (which emits the switch notice and event as for Jev); if `hit == active`, keep (no change); otherwise fall through to Jev. Use the `deps` time field the service already uses (`deps.today` exists; check for a datetime; if none, `utcnow()` from `mia.core.time` or wherever the service takes it).

- [ ] **Step 1: Write the failing tests**

In `node/tests/test_agent_router.py` (reuse fixtures; `_tap(session, person, reply, label)` means sending the button label as the next message in the same thread):

```python
def _ask_then_tap(session, people, monkeypatch, two_agents, text: str, agent: str) -> ChatReply:
    _router_answers(monkeypatch, two_agents, "unclear", 0.4)  # unsure: buttons
    asked = _turn(session, people["sanna"], text)
    label = next(b for b in asked.blocks if isinstance(b, QuickRepliesBlock)).options
    chosen_label = next(
        o for o in label if AGENTS[agent].label_key.split(".")[1] in o.casefold() or True
    )
    # simpler: the options are in agents_for order, TWO order; pick by index
    index = TWO.index(agent)
    return _turn(session, people["sanna"], label[index], asked.thread_id)


def test_a_route_tap_is_remembered(session, people, monkeypatch, two_agents) -> None:
    _ask_then_tap(session, people, monkeypatch, two_agents, "3 sp 2 cl", TWO[1])
    ev = session.exec(select(Event).where(Event.action == "chat.route_chosen")).one()
    assert ev.after["agent_id"] == TWO[1]
    assert ev.after["picked"] == "unclear" and ev.after["confidence"] == 0.4
    assert ev.after["key"] == "# sp # cl"
    assert set(ev.after["options"]) == set(TWO)


def test_the_third_repeat_is_routed_without_jev(session, people, monkeypatch, two_agents) -> None:
    _ask_then_tap(session, people, monkeypatch, two_agents, "3 sp 2 cl", TWO[1])
    _ask_then_tap(session, people, monkeypatch, two_agents, "5 sp 1 cl", TWO[1])
    requests_before = len(two_agents)
    _router_answers(monkeypatch, two_agents, "unclear", 0.4)
    reply = _turn(session, people["sanna"], "4 sp 4 cl")
    assert reply.agent_id == TWO[1]
    assert not any(isinstance(b, QuickRepliesBlock) for b in reply.blocks)
    assert len(two_agents) == requests_before  # no Jev request


def test_a_learned_route_with_another_agent_active_is_a_switch(
    session, people, monkeypatch, two_agents
) -> None:
    _ask_then_tap(session, people, monkeypatch, two_agents, "3 sp 2 cl", TWO[1])
    _ask_then_tap(session, people, monkeypatch, two_agents, "5 sp 1 cl", TWO[1])
    _router_answers(monkeypatch, two_agents, TWO[0], 0.95)
    first = _turn(session, people["sanna"], SHIFT)
    reply = _turn(session, people["sanna"], "2 sp 2 cl", first.thread_id)
    assert reply.agent_id == TWO[1]
    switched = session.exec(select(Event).where(Event.action == "chat.agent_switched")).all()
    assert switched[-1].after == {"from": TWO[0], "to": TWO[1]}


def test_a_learned_agent_the_person_lost_is_ignored(
    session, people, monkeypatch, two_agents
) -> None:
    _ask_then_tap(session, people, monkeypatch, two_agents, "3 sp 2 cl", TWO[1])
    _ask_then_tap(session, people, monkeypatch, two_agents, "5 sp 1 cl", TWO[1])
    monkeypatch.setattr(orgconfig, "load", lambda org=None: orgconfig.OrgSettings(agents=[TWO[0]]))
    reply = _turn(session, people["sanna"], "4 sp 4 cl")
    assert reply.agent_id == TWO[0]  # the only agent left; no error, no memory hit


def test_a_switch_away_within_the_hour_unlearns(session, people, monkeypatch, two_agents) -> None:
    _ask_then_tap(session, people, monkeypatch, two_agents, "3 sp 2 cl", TWO[1])
    second = _ask_then_tap(session, people, monkeypatch, two_agents, "5 sp 1 cl", TWO[1])
    _router_answers(monkeypatch, two_agents, TWO[0], 0.95)  # the person moves on at once
    _turn(session, people["sanna"], "5 sp 1 cl", second.thread_id)
    requests_before = len(two_agents)
    _router_answers(monkeypatch, two_agents, "unclear", 0.4)
    _turn(session, people["sanna"], "6 sp 1 cl")
    assert len(two_agents) == requests_before + 1  # Jev was asked: nothing learned
```

Tidy `_ask_then_tap` while writing it (drop the dead `chosen_label` line; the index pick is the intent). The options list is in `agents_for` order, which is the org's order, `TWO`.

- [ ] **Step 2: Run them, expect failure**

`uv run pytest node/tests/test_agent_router.py -k "remembered or third_repeat or learned or unlearns" --no-cov`

- [ ] **Step 3: Implement**

`route_memory.py` additions:

```python
from sqlmodel import Session, col, select

from mia.core import events
from mia.core.models import Event, Message, Thread


def remember(
    session: Session,
    deps: "AgentDeps",
    thread: Thread,
    original_message_id: str | None,
    agent_id: str,
    picked: str | None,
    confidence: float | None,
    options: list[str],
) -> None:
    """Emits chat.route_chosen for a tap, in the caller's transaction; no event when the
    original message is unknown (nothing to learn from)."""
    message = session.get(Message, original_message_id) if original_message_id else None
    if message is None:
        return
    events.emit(
        session,
        CHOSEN,
        ("thread", thread.id),
        None,
        {
            "original_message_id": message.id,
            "agent_id": agent_id,
            "picked": picked,
            "confidence": confidence,
            "options": options,
            "lang": deps.lang,
            "key": key_of(message.text),
        },
        deps.actor,
    )


def _switches(session: Session, branch_id: str) -> list[Switch]:
    """chat.agent_switched events as Switch rows: the key is that of the thread's latest user
    message before the switch."""
    rows = session.exec(
        select(Event)
        .where(Event.action == "chat.agent_switched")
        .where(Event.branch_id == branch_id)
    ).all()
    out: list[Switch] = []
    for ev in rows:
        message = session.exec(
            select(Message)
            .where(Message.thread_id == ev.entity_id)
            .where(Message.role == "user")
            .where(Message.created_at <= ev.timestamp)
            .order_by(col(Message.id).desc())
        ).first()
        if message is not None and (ev.after or {}).get("from"):
            out.append(
                Switch(key_of(message.text), str(ev.after["from"]), ev.timestamp, ev.entity_id)
            )
    return out


def recall(session: Session, branch_id: str, now: dt.datetime) -> dict[str, str]:
    """The branch's learned keys (key to agent id). Reads events only."""
    # ponytail: a scan of the branch's route events per message; cache or index when a branch
    # passes thousands of taps.
    taps = [
        Tap(str(a["key"]), str(a["agent_id"]), ev.timestamp, ev.entity_id, ev.id)
        for ev in session.exec(
            select(Event).where(Event.action == CHOSEN).where(Event.branch_id == branch_id)
        )
        if (a := ev.after or {}).get("key") and a.get("agent_id")
    ]
    forgotten: dict[str, dt.datetime] = {}
    for ev in session.exec(
        select(Event).where(Event.action == FORGOTTEN).where(Event.branch_id == branch_id)
    ):
        key = str((ev.after or {}).get("key"))
        forgotten[key] = max(forgotten.get(key, ev.timestamp), ev.timestamp)
    return learned(taps, _switches(session, branch_id), forgotten, now)
```

Check the `Message` timestamp column name in `core/models.py` (`BranchScoped` likely has `created_at`); use the real one. `AgentDeps` import under `TYPE_CHECKING` to avoid a cycle (`mia.agents.base` imports chat modules? check; if not, import directly).

`service.py`:

- `_ask_route(..., picked: str | None = None, confidence: float | None = None)` adds `"picked"` and `"confidence"` to the `chat.route_asked` after. `_settle` passes `picked.agent_id if picked.kind != "ask" else None`... simpler: give `Route` the raw pick: in `decide`, `Route("ask", None, confidence)` cannot carry `picked`; add a field `raw: str | None = None` to `Route` set to Jev's pick in every branch of `decide`, and `_settle` passes `picked.raw, picked.confidence` to `_ask_route`. `fallback` leaves `raw=None`.
- `_route_tapped` returns the tap; in `_choose`, right before `return ids[tap[0]], agents, active, original or text, True`, read the `chat.route_asked` event's `after` (it is already fetched in `_route_tapped`; return it as a third element or re-read it) and call `route_memory.remember(session, deps, thread, tap[1], tap[0], after.get("picked"), after.get("confidence"), list((after.get("options") or {}).values()))`.
- `route_turn`: after the `waiting` check and before `if spec is not None:` insert:

```python
    if spec is None:
        hit = (await asyncio.to_thread(route_memory.recall, session, deps.branch.id, now)).get(
            route_memory.key_of(text)
        )
        if hit in {a.id for a in agents} and hit != active:  # rule 4: still one of theirs
            kind: Literal["switch", "chosen"] = "switch" if active else "chosen"
            settled = await asyncio.to_thread(
                _settle, session, deps, thread, agent_router.Route(kind, hit, 1.0), agents, None
            )
            assert not isinstance(settled, ChatReply)  # a chosen agent never asks
            spec, agent_deps = AGENTS[hit], settled
        elif hit == active and active is not None:
            spec = AGENTS[active]
```

Take `now` from the time source the service already uses for `deps.today` (grep `today=` in `service.py`; the same clock call, as a datetime). Then the existing `if spec is not None:` branch builds `agent_deps` only when it is not set yet: restructure so `agent_deps` is built once (`agent_deps = _deps_for(deps, spec)` for the keep case; the switch case already has it from `_settle`).

`docs/layout.md` line 41: add `route_memory.py (what people chose when Mia asked)`.

- [ ] **Step 4: Run the tests, expect pass**

`uv run pytest node/tests/test_agent_router.py node/tests/test_route_memory.py --no-cov`

- [ ] **Step 5: Full checks and commit**

```bash
uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest
git add node/mia/chat/route_memory.py node/mia/chat/service.py node/mia/chat/agent_router.py node/tests/test_agent_router.py docs/layout.md
git commit -m "chat: a tap on 'Is this about' is remembered (chat.route_chosen); after two taps the same message is routed by code, no Jev request; a switch within the hour unlearns it"
```

---

### Task 5: The owner sees and clears it

**Files:**
- Modify: `node/mia/cli.py` (`learned`, `forget`, parser entries near line 621)
- Modify: `node/mia/chat/route_memory.py` (`forget`)
- Modify: `node/mia/i18n/strings.py` (en, fi), the eight modules (keys `cli.learned.none`, `cli.learned.row`, `cli.forgotten`)
- Modify: `README.md` (command table), `docs/layout.md` (cli.py line)
- Test: `node/tests/test_cli.py`, `node/tests/test_route_memory.py`

**Interfaces:**
- Consumes: Task 4's `recall`, `remember`; `cli._only_branch_id(session, branch_id)`; `Actor` for a CLI actor (see how `person_add` builds its actor).
- Produces: `route_memory.forget(session, branch_id, key, actor) -> None` emits `chat.route_forgotten` on `("branch", branch_id)` with after `{"key": key, "agent_id": <learned agent or None>}`; `mia learned [--branch ID]` prints one line per learned key: `<agent id>\t<key>\t<count>` using `cli.learned.row` (params agent, key, count) or `cli.learned.none`; `mia forget <key> [--branch ID]` emits the event and prints `cli.forgotten`.

- [ ] **Step 1: Write the failing tests**

`node/tests/test_route_memory.py`:

```python
def test_two_new_taps_after_forget_learn_again() -> None:
    forgotten = {"k": NOW - dt.timedelta(days=3)}
    taps = [_tap("k", A, 5), _tap("k", A, 4), _tap("k", A, 2), _tap("k", A, 1)]
    assert learned(taps, [], forgotten, NOW) == {"k": A}
    assert learned(taps[:3], [], forgotten, NOW) == {}
```

`node/tests/test_cli.py` (follow `test_person_add`'s shape: `build_parser().parse_args([...]).func(args)` and `capsys`; seed events with `route_memory.remember` through a session on the test database the CLI tests already use):

```python
def test_learned_and_forget(capsys, session, people, ...) -> None:
    # two taps for one key (use the helpers the other CLI tests use for a thread and a message)
    ...
    assert build_parser().parse_args(["learned"]).func(args) == 0
    out = capsys.readouterr().out
    assert "# sp # cl" in out and "2" in out
    assert build_parser().parse_args(["forget", "# sp # cl"]).func(args) == 0
    assert session.exec(select(Event).where(Event.action == "chat.route_forgotten")).one()
    build_parser().parse_args(["learned"]).func(args)
    assert "# sp # cl" not in capsys.readouterr().out
```

Fill the fixture plumbing from the existing CLI tests (they create a database and people; mirror `test_migrate_seed_chat_assign_confirm`).

- [ ] **Step 2: Run them, expect failure**

`uv run pytest node/tests/test_cli.py -k learned node/tests/test_route_memory.py -k forget --no-cov`

- [ ] **Step 3: Implement**

`route_memory.forget`:

```python
def forget(session: Session, branch_id: str, key: str, actor: Actor, now: dt.datetime) -> None:
    """Emits chat.route_forgotten so the key is not learned until MIN_TAPS new taps. Commits."""
    agent_id = recall(session, branch_id, now).get(key)
    events.emit(
        session, FORGOTTEN, ("branch", branch_id), None, {"key": key, "agent_id": agent_id}, actor
    )
    session.commit()
```

`cli.py`: `learned(args)` opens a session (as `person_add` does), resolves the branch with `_only_branch_id`, calls `recall` and prints rows with counts (count the `chat.route_chosen` events per key, agent; expose a `counts(session, branch_id, now) -> dict[tuple[str, str], int]` helper in `route_memory` next to `recall`, or return counts from `recall` as a second function; keep `recall`'s return type). `forget(args)` calls `route_memory.forget` with the CLI's actor. Parser:

```python
    p = sub.add_parser("learned", help="routes Mia learned from 'Is this about' taps")
    p.add_argument("--branch", default=None)
    p.set_defaults(func=learned)
    p = sub.add_parser("forget", help="forget one learned route (two new taps relearn it)")
    p.add_argument("key")
    p.add_argument("--branch", default=None)
    p.set_defaults(func=forget)
```

i18n keys, English: `"cli.learned.none": "Mia has learned no routes here yet."`, `"cli.learned.row": "{agent}\t{key}\t{count}"`, `"cli.forgotten": "Forgotten: {key}"`. Finnish and the eight modules: drafts in the same place as `reply.not_built`. The row key is a format, the same in every language.

README command table: two rows. `docs/layout.md` line 19: add `learned | forget`.

- [ ] **Step 4: Run the tests, expect pass**

`uv run pytest node/tests/test_cli.py node/tests/test_route_memory.py node/tests/test_i18n_languages.py --no-cov`

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest
git add node/mia/cli.py node/mia/chat/route_memory.py node/mia/i18n README.md docs/layout.md node/tests/test_cli.py node/tests/test_route_memory.py
git commit -m "cli: mia learned lists the routes Mia learned from taps per branch; mia forget clears one (chat.route_forgotten) until two new taps"
```

---

### Task 6: Harvest route choices for the local model

**Files:**
- Modify: `node/mia/learning/harvest.py`
- Test: `node/tests/learning/test_harvest.py`

**Interfaces:**
- Consumes: `Record`, `Review`, `load_records`, `_append`, `Pseudonymiser`, `_previous_assistant_text`; `chat.route_chosen` events (Task 4), `chat.route_forgotten`, `chat.agent_switched`.
- Produces: `harvest(session, role, branch_id)` for `role == "router"` reads `chat.route_chosen` instead of `intent.clarified`: `intent = agent_id`, `source = "real-route-choice"`, `id = f"router/real/{original_message_id}"`, undo when a `chat.agent_switched` with `from == agent_id` on the same thread (`entity_id`) happens within one hour after the tap, or a `chat.route_forgotten` for the same key comes later. Everything else (pseudonymised text and context, pending review, sensitive prefixes not applicable, dedupe by id) as for intents.

- [ ] **Step 1: Write the failing tests**

Mirror `test_clarified_choice_becomes_a_pending_pseudonymised_candidate` and `test_undo_within_one_hour_drops_the_record` for the router: emit a `chat.route_chosen` (through `route_memory.remember` with a real message in a thread), run `harvest(session, "router", branch_id)`, assert one `Record` with `role == "router"`, `intent == <agent id>`, `source == "real-route-choice"`, pseudonymised text (a name in the message is replaced), `review.status == "pending"`; a `chat.agent_switched` from that agent on the thread 10 minutes later gives no record; a `chat.route_forgotten` for the key gives no record.

- [ ] **Step 2: Run them, expect failure**

`uv run pytest node/tests/learning/test_harvest.py -k router --no-cov`

- [ ] **Step 3: Implement**

In `harvest.py`, split the event scan into a small dispatch: `if role == "router": events = _route_choices(session, branch_id)` else the existing `intent.clarified` query, where `_route_choices` yields `(ev, intent, original_id)` triples and the record fields `source` and `id` prefix come from a `(action, source)` pair per role. Add `_route_undone(session, ev)`: a `chat.agent_switched` with `entity_id == ev.entity_id`, `after["from"] == ev.after["agent_id"]`, `timestamp - ev.timestamp <= UNDO_WINDOW`; and `_route_forgotten(session, ev)`: a `chat.route_forgotten` in the branch with `after["key"] == ev.after["key"]` and `id > ev.id`. Keep the function under 60 lines by extracting `_record(...)`.

- [ ] **Step 4: Run the tests, expect pass**

`uv run pytest node/tests/learning/test_harvest.py --no-cov`

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest
git add node/mia/learning/harvest.py node/tests/learning/test_harvest.py
git commit -m "learning: route taps are harvested as pending router records (source real-route-choice), dropped when switched away within the hour or forgotten"
```

---

### Task 7: The retail case set and the gate

**Files:**
- Rewrite: `node/tests/evals/router_cases.py`
- Modify: `node/tests/evals/test_router_eval.py` (`_score`, the gate, the `small_talk` column, the held-out split)
- Modify: `docs/superpowers/specs/2026-10-18-router-follow-up-design.md` (nothing) and `README.md` (eval line if the command changes; it should not)
- Test: `node/tests/evals/test_router_cases.py` (new, offline: counts and shape)

**Interfaces:**
- Consumes: `Case(lang, text, expected, active, previous, group)`; `AGENTS`; `_score`, `_row`, `_table`, `GATED`, `ROSTER`.
- Produces: `router_cases.CASES: list[Case]` with `group in {"single", "follow_up", "switch"}`, a new field `half: Literal["tune", "gate"]` assigned by the parity of the case's index inside its (lang, group) list, and `expected` being an agent id, `"any"` (greeting, thanks) or `"small_talk"`. Counts per gated language: at least 60 single (10 per agent), 10 follow_up, 10 switch; the reported languages (fi, ilo, pam, pag): 30 single each. Finnish single cases come from the existing intent split (`_intent_cases`) filtered to rows that are not in-flow replies (keep only rows whose `context` is empty, if `intents.jsonl` carries that field; otherwise drop rows shorter than three words).

- [ ] **Step 1: Write the offline shape test**

`node/tests/evals/test_router_cases.py` (no marker, runs in CI):

```python
from collections import Counter

from mia.agents.registry import AGENTS
from tests.evals.router_cases import CASES, GATED_LANGS


def test_every_gated_language_covers_every_agent_and_group() -> None:
    for lang in GATED_LANGS:
        single = [c for c in CASES if c.lang == lang and c.group == "single"]
        by_agent = Counter(c.expected for c in single)
        assert all(by_agent[a] >= 10 for a in AGENTS), (lang, by_agent)
        assert sum(1 for c in CASES if c.lang == lang and c.group == "follow_up") >= 10
        assert sum(1 for c in CASES if c.lang == lang and c.group == "switch") >= 10


def test_expected_values_are_agents_any_or_small_talk() -> None:
    assert {c.expected for c in CASES} <= {*AGENTS, "any", "small_talk"}


def test_halves_are_balanced_per_language_and_group() -> None:
    for (lang, group), cases in _grouped(CASES).items():
        halves = Counter(c.half for c in cases)
        assert abs(halves["tune"] - halves["gate"]) <= 1, (lang, group, halves)


def test_no_case_names_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)
```

(`_grouped` is a three-line helper in the test.) Note: this test file names agent ids only through `AGENTS`; the case file names them as data strings, which `tests/test_architecture.py` allows for tests (confirm; if not, exclude `router_cases.py` the way it excluded the old file).

- [ ] **Step 2: Run it, expect failure**

`uv run pytest node/tests/evals/test_router_cases.py --no-cov`

- [ ] **Step 3: Write the case set**

Structure of `router_cases.py`:

```python
"""The retail router eval set (spec 2026-10-18-router-follow-up, decision 2): what clerks,
head staff and the owner of a bibingka shop send, in six gated and four reported languages.
Data only; test_router_eval.py runs it. Synthetic, written by Claude, not native speakers
(D18); Q28 to Q35 cover the review of the Philippine languages."""

GATED_LANGS = ("en", "fil", "ceb", "hil", "war", "bcl")
REPORTED_LANGS = ("fi", "ilo", "pam", "pag")

# (expected agent, English seed). Ten per agent, two greetings, two thanks.
SEEDS: list[tuple[str, str]] = [
    ("sales_supervisor", "3 special 5 classic 2 salted egg"),
    ("sales_supervisor", "sold 12 ube so far"),
    ("sales_supervisor", "sorry, 4 special not 3"),
    ("sales_supervisor", "how are we doing today"),
    ("sales_supervisor", "did we hit the target yesterday"),
    ("sales_supervisor", "best day this month?"),
    ("sales_supervisor", "we sold 20 boxes to one customer"),
    ("sales_supervisor", "total for the morning is 1,450"),
    ("sales_supervisor", "which branch sells most salted egg"),
    ("sales_supervisor", "closing count: 6 special 9 classic 0 ube"),
    ("shift_supervisor", "I'm sick tomorrow"),
    ("shift_supervisor", "I'll be late by 30 minutes"),
    ("shift_supervisor", "who is on shift on Saturday"),
    ("shift_supervisor", "can someone cover my afternoon"),
    ("shift_supervisor", "checking in at the mall branch"),
    ("shift_supervisor", "the oven is broken"),
    ("shift_supervisor", "power is out at the stall"),
    ("shift_supervisor", "can I swap Sunday with Ana"),
    ("shift_supervisor", "done with the closing checklist"),
    ("shift_supervisor", "a customer slipped near the counter"),
    ("inventory_manager", "sold out of special at 2pm"),
    ("inventory_manager", "only 5 ube left"),
    ("inventory_manager", "we have 3 trays of leftovers"),
    ("inventory_manager", "threw away 8 classic, too dry"),
    ("inventory_manager", "what should we bake tomorrow"),
    ("inventory_manager", "running low on rice flour"),
    ("inventory_manager", "eggs delivered, 10 trays"),
    ("inventory_manager", "LPG is almost empty"),
    ("inventory_manager", "need more banana leaves by Friday"),
    ("inventory_manager", "supplier raised the coconut price"),
    ("bookkeeper", "cash count is 4,320"),
    ("bookkeeper", "the drawer is short by 150"),
    ("bookkeeper", "paid 600 for the trike delivery, receipt attached"),
    ("bookkeeper", "deposited 10,000 at BPI"),
    ("bookkeeper", "GCash sales today 2,100"),
    ("bookkeeper", "Grab payout came in"),
    ("bookkeeper", "how much VAT do we owe this quarter"),
    ("bookkeeper", "Ate Rose paid her utang, 300"),
    ("bookkeeper", "need the sales book for the BIR"),
    ("bookkeeper", "what was our profit last month"),
    ("hr_officer", "how many hours did I work this cutoff"),
    ("hr_officer", "when is payday"),
    ("hr_officer", "can I get a cash advance of 1,000"),
    ("hr_officer", "how much is my 13th month"),
    ("hr_officer", "is my SSS paid"),
    ("hr_officer", "I want to file leave next week"),
    ("hr_officer", "do we get holiday pay on Monday"),
    ("hr_officer", "my payslip is missing"),
    ("hr_officer", "need a certificate of employment"),
    ("hr_officer", "we are hiring a new clerk, where do I start"),
    ("branch_manager", "change the price of special to 45"),
    ("branch_manager", "add a new item: cheese overload"),
    ("branch_manager", "what is the short code for salted egg"),
    ("branch_manager", "add Maria as a clerk at the mall branch"),
    ("branch_manager", "when does the mayor's permit expire"),
    ("branch_manager", "send me the weekly summary"),
    ("branch_manager", "what time do we open on Sundays"),
    ("branch_manager", "remove the ube from the menu for now"),
    ("branch_manager", "who approves supplier orders"),
    ("branch_manager", "any tips for the new clerk on upselling"),
    ("any", "good morning!"),
    ("any", "hello po"),
    ("any", "thanks!"),
    ("any", "salamat"),
]
```

Then `TEXTS: dict[str, list[str]]` with one list per language in `GATED_LANGS + REPORTED_LANGS`, each the same length and order as `SEEDS` (the eight Philippine languages and Finnish are the implementer's drafts; English is the seed itself; keep "hello po" and "salamat" as they are in every Philippine language and translate them for fi). `FOLLOW_UPS`: ten per gated language, each `(active agent, previous Mia message, text, expected)`, covering: an answer to "Why do you think sales went well?" (sales active, expected sales), "all of them" after a cover question (shift active, expected shift), "yes" after "Order 10 trays of eggs?" (inventory active, expected inventory), and three that change subject mid-thread (sales active, "the oven is broken", expected shift). `SWITCHES`: ten per gated language: five sales reports with the shift supervisor active, five cover or absence messages with the sales supervisor active (reuse the texts from `SEEDS` through the language table). `CASES` is built by three small functions and assigned `half` by index parity within (lang, group). Keep `_intent_cases()` for Finnish single cases, filtered as the Interfaces say; drop `COVER` and `WHY_ASKED` if unused.

Scoring in `test_router_eval.py`:

```python
def _score(r: dict[str, Any]) -> str:
    """right, wrong (another agent at >= 0.6), ask, small_talk, or other."""
    if r["kind"] == "ask":
        return "ask"
    if r["kind"] == "error":
        return "other"
    if r["kind"] == "small_talk":
        return "right" if r["expected"] in ("any", "small_talk") else "small_talk"
    if r["expected"] == "any" or r["agent"] == r["expected"]:
        return "right"
    return "wrong" if r["kind"] in ("switch", "chosen") else "other"
```

`_row` gains `small_talk` (a real message answered as small talk: a miss, counted separately from wrong). The gate asserts run over `half == "gate"` rows only; the summary prints both halves. The eval's `_one` must use the current `decide` (it does) so `small_talk` reaches the results. The report file name stays `router-<date>.raw.json`.

- [ ] **Step 4: Run the offline tests, expect pass**

`uv run pytest node/tests/evals/test_router_cases.py node/tests/evals/test_router_eval.py --no-cov` (the real-Jev tests are deselected without the marker; confirm they still import).

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest
git add node/tests/evals/router_cases.py node/tests/evals/test_router_cases.py node/tests/evals/test_router_eval.py
git commit -m "evals: the router case set is retail traffic in ten languages (six agents, follow-ups with context, switches), split into a tuning half and a gate half; small talk is scored"
```

---

### Task 8: Run the gate and report

**Files:**
- Create: `docs/research/router-2026-10-19.md`, `docs/research/router-2026-10-19.raw.json`
- Modify: `docs/superpowers/specs/2026-10-18-router-follow-up-design.md` (a one-line result note under Goal), `docs/questions.md` (Q36, Q37 from the spec if not yet present)

**Interfaces:**
- Consumes: Task 7's harness and set; `MIA_TYPESAFE_KEY`, `MIA_DECIDER=jev`, `MIA_JEV_MODEL` from `.env` (never printed).

- [ ] **Step 1: Run the eval once**

`MIA_DECIDER=jev uv run pytest node/tests/evals/test_router_eval.py -m evals -k test_router --no-cov -s 2>&1 | tail -60`
Expected: the gate table per language for the gate half and the tuning half, the `small_talk` column, p50 and p95 latency, tokens. The run takes 15 to 25 minutes at concurrency 4; the 30 s per-request timeout bounds a stall.

- [ ] **Step 2: If the gate fails on the tuning half, tune once**

Edit only the descriptions of Task 2 (one more pass, keep the contrast lines), rerun. Never edit the case set to pass. Two passes at most; then report the result as it is.

- [ ] **Step 3: Write the report**

`docs/research/router-2026-10-19.md` in the shape of `router-2026-10-18.md`: setup, gate table (gate half) per language with right, wrong, ask, small_talk, missed switch; the tuning half's table; the top ten confusions by confidence; latency and tokens; what changed since 18 Oct (small talk, descriptions, the set) and what it did to the numbers; what remains. Honest if the gate fails.

- [ ] **Step 4: Questions**

Add Q36 and Q37 to `docs/questions.md` exactly as the spec words them, with the assumed answers.

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest
git add docs/research/router-2026-10-19.md docs/research/router-2026-10-19.raw.json docs/questions.md docs/superpowers/specs/2026-10-18-router-follow-up-design.md
git commit -m "research: router gate on the retail set after small talk and the contrast descriptions (report in docs/research)"
```

---

## Self-review notes

- Spec coverage: decision 1 (Task 1), 2 (Task 7, 8), 3 (Task 2), 4a (Task 4), 4b (Tasks 3, 4), 4c (Task 6), 5 (Task 5), guardrails (Tasks 3, 4 tests; Review Focus), events table (Tasks 4, 5), i18n (Task 5), testing section (all), open questions (Task 8).
- Order follows the spec's "Order of work": 1 and 3 first, the set and the gate, then memory. Task 8 runs last so the memory never hides a routing problem in the gate (memory is not exercised by the eval, which calls `build_request` and `decide` directly).
- Type consistency: `Route.kind` literal gains `small_talk` (Task 1) and `Route.raw` (Task 4); `Tap`, `Switch`, `learned`, `key_of`, `recall`, `remember`, `forget` named the same in Tasks 3 to 6.
