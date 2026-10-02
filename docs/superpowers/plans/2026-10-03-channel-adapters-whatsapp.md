# Channel Adapters and WhatsApp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** People reach the local Mia Node over WhatsApp (and any later channel) through a pluggable channel layer, with invites, one-time-code linking, an outbox, and the 24 hour window handled by templates.

**Architecture:** A new `mia/channels` package holds the adapter protocol, registry, shared rendering, delivery service, outbox, linking and webhook router. Agents and the cover flow only call `notify()` (which calls `channels.deliver()`); adapters (`sim`, `whatsapp`) plug in through the registry and pass one shared contract suite. All writes go through `mia.core.store` and emit events.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, httpx (already a dependency), pytest with `httpx.MockTransport`.

**Spec:** docs/superpowers/specs/2026-10-02-channel-adapters-whatsapp-design.md (approved 2026-10-03). Rules: CLAUDE.md.

## Global Constraints
- No new dependencies. QR codes are not built (the spec mentions one); `mia invite` prints the wa.me link. Add QR when a printed invite is actually needed.
- Data standard becomes 1.2 (`STANDARD_VERSION = "1.2"`), migration `0003`.
- All writes via `store.insert` / `store.update` (rule 1); IDs via `new_id`; datetimes `sa_type=TZDateTime` (rule 10).
- User-facing strings via `mia.i18n.t` keys, Finnish and English (style rule).
- In `mia/channels`, only `transport.py` and `whatsapp/adapter.py` import httpx.
- Commit before any network await (rule 11). Sync DB work in async code via `asyncio.to_thread` (rule 12).
- Webhook signature: `X-Hub-Signature-256: sha256=<hex HMAC-SHA256(app_secret, raw body)>`, compared with `hmac.compare_digest`.
- Link codes: 6 digits, stored as HMAC-SHA256 with `MIA_NODE_SECRET`; invites valid 7 days, self codes 10 minutes; 5 failed attempts per address per hour block it for an hour.
- Outbox retries at 1, 5 and 30 minutes, then `failed`.
- WhatsApp limits: text 4096, reply buttons 3 with 20-character titles, list rows 10 with 24-character titles, window 24 hours.
- No em-dashes in docs or comments.

## Spec deviations (decided while planning)
- Templates registered in Phase 1: `mia_new_message` and `mia_cover_request`. `mia_cover_update` and `mia_approval_waiting` fall back to `mia_new_message` until they exist in WhatsApp Manager (adding one is a registry entry).
- Quiet hours: the cover flow already gates asks by D11 (`cover.may_message`), so its asks pass `urgent=True`; every other proactive message waits until quiet hours end (`send_after`).

## Review Focus
1. A button tap whose text differs from the template label (case, emoji, other language): the tap must still reach the cover flow as accept or decline. Test in Task 7.
2. Meta resends the same webhook (same message id) while the first is still being processed: exactly one agent turn. Test in Task 7.
3. A person messages Mia in the 24 hour window while a held message is waiting: the held message is sent once, before the reply. Test in Task 6.
4. Two people in the demo seed share a first name prefix, and `mia invite` gets an ambiguous name: refuse, list matches. Test in Task 5.
5. Clock at the quiet-hours boundary (exactly 06:00 local): a waiting non-urgent message becomes due. Test in Task 6.

---

### Task 1: Rule 12 compliance and docstrings (existing code)

**Files:**
- Modify: `node/mia/chat/service.py` (run_turn), `node/mia/core/egress.py` (EgressTransport), and add docstrings to the public functions listed below
- Test: `node/tests/test_chat.py`, `node/tests/test_egress.py`

**Interfaces:**
- Produces: `run_turn(session, agent, person, text, thread_id=None) -> ChatReply` unchanged signature; its DB work now runs in worker threads.

- [ ] Step 1: failing test `test_run_turn_db_work_is_off_the_event_loop`: monkeypatch `mia.core.store.insert` with a wrapper that records `threading.current_thread() is threading.main_thread()`; run `asyncio.run(run_turn(...))`; assert all recorded values are False.
- [ ] Step 2: run it, expect FAIL (inserts run on the loop thread).
- [ ] Step 3: split `run_turn` into `_prepare(session, person, text, thread_id) -> tuple[Thread, list[ModelMessage], AgentDeps, EgressContext]` and `_finish(session, deps, result, thread) -> ChatReply` (both sync), called with `await asyncio.to_thread(...)`; only `agent.run` stays on the loop. In `EgressTransport.handle_async_request`, wrap `send(...)` plus `commit` and `_record_usage(...)` plus `commit` in `asyncio.to_thread`.
- [ ] Step 4: run full suite, expect PASS.
- [ ] Step 5: add one-line guarantee docstrings to: `to_pydantic_tool`, `parse_time`, `is_quiet`, `is_soon`, `may_message`, `may_call`, `system_actor`, `rules_model`, `visit_info`, `visits_for`, `call_adapter`, `set_call_adapter`, `chat`, `history`, `egress_context`, `current_context`, `payload_hash`, `get_provider`. Add `test_public_functions_have_docstrings` to `test_architecture.py` (AST walk over core, chat, agents, channels).
- [ ] Step 6: lint, mypy, pytest; commit "Keep DB work off the event loop; docstrings on public functions".

### Task 2: Data standard 1.2, add person

**Files:**
- Modify: `node/mia/core/models.py` (5 tables, STANDARD_VERSION 1.2), `node/mia/settings.py`, `node/mia/cli.py`, `.env.example`
- Create: `node/mia/core/people.py`, `node/migrations/versions/0003_channels.py`
- Test: `node/tests/test_people.py`, `node/tests/test_migrations.py`

**Interfaces:**
- Produces tables (all `BranchScoped` unless noted):
  - `ChannelIdentity` (`channel_identities`): person_id, channel, address, verified_at, consent_at, last_inbound_at (TZDateTime, nullable), status "active" or "revoked". Index (channel, address).
  - `ChannelLinkCode` (`channel_link_codes`): person_id, code_hmac (unique), purpose "invite" or "self", expires_at, used_at, created_by.
  - `ChannelLinkAttempt` (`channel_link_attempts`, `Stamped`, no branch): channel, address, ok.
  - `ChannelOutbox` (`channel_outbox`): person_id, channel, address, kind, payload (JSON), sensitive, idempotency_key (unique), status queued/sent/delivered/read/failed/held, attempts, send_after, channel_message_id (index), error_code.
  - `ChannelInbound` (`channel_inbound`, `Stamped`, branch nullable): channel, channel_message_id, address, person_id, body (JSON), status pending/done/failed/ignored, error; unique (channel, channel_message_id).
- Produces: `people.add_person(session, actor, *, branch_id, name, roles, language="fi", skills=None) -> Person`; `people.deactivate(session, actor, person) -> Person` (also revokes identities, wired in Task 5).
- Settings: `MIA_NODE_SECRET: str = ""`, `MIA_PUBLIC_URL: str = "http://localhost:8000"`, `MIA_WA_TOKEN`, `MIA_WA_APP_SECRET`, `MIA_WA_VERIFY_TOKEN`, `MIA_WA_PHONE_NUMBER_ID`, `MIA_WA_NUMBER` (display number for wa.me links), `MIA_WA_GRAPH_URL: str = "https://graph.facebook.com/v21.0"`.

- [ ] Step 1: failing tests: `add_person` creates the row and a `person.created` event with the actor; empty name raises `ValueError`; unknown role raises `ValueError` (allowed: staff, supervisor, admin, owner); `migration upgrade head` creates all five tables (extend existing migration test).
- [ ] Step 2: run, FAIL.
- [ ] Step 3: implement models, `people.py`, migration 0003 (hand-written `op.create_table` like 0002, with `mia.core.db.TZDateTime` columns), settings, `.env.example` lines with comments.
- [ ] Step 4: CLI `mia person add NAME --role staff [--role ...] [--lang fi] [--branch ID]` (default: the only branch); prints id.
- [ ] Step 5: pass; commit "Data standard 1.2: channel tables; add person service and CLI".

### Task 3: Channel base, registry, rendering

**Files:**
- Create: `node/mia/channels/__init__.py`, `base.py`, `registry.py`, `render.py`
- Modify: `node/mia/core/orgconfig.py` (channels config), `docs/layout.md`
- Test: `node/tests/channels/test_render.py`, `node/tests/channels/__init__.py`

**Interfaces:**
```python
class ChannelCapabilities(BaseModel):
    max_text: int; max_buttons: int; max_button_label: int
    max_list_rows: int; max_list_label: int
    session_window_hours: int | None; supports_templates: bool
class InboundMessage(BaseModel):
    channel: str; address: str; channel_message_id: str
    text: str = ""; button: str | None = None; has_media: bool = False
    received_at: datetime
class StatusUpdate(BaseModel):
    channel: str; channel_message_id: str; status: str; error_code: str | None = None
class TemplateCall(BaseModel):
    name: str; lang: str; params: list[str] = []; buttons: list[str] = []
class ChannelPayload(BaseModel):
    channel: str; address: str; body: dict[str, Any]
class DeliveryResult(BaseModel):
    ok: bool; channel_message_id: str | None = None; error_code: str | None = None
class ChannelAdapter(Protocol):
    channel_id: str; capabilities: ChannelCapabilities
    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool
    def verify_subscription(self, params: Mapping[str, str]) -> str | None
    def receive(self, body: bytes) -> list[InboundMessage | StatusUpdate]
    def render(self, address: str, parts: list[RenderedPart]) -> list[ChannelPayload]
    def render_template(self, address: str, call: TemplateCall) -> ChannelPayload
    async def send(self, payload: ChannelPayload) -> DeliveryResult
```
- `render.py`: `RenderedPart = TextPart | ButtonsPart | ListPart`; `to_parts(blocks, caps, lang, *, sensitive) -> list[RenderedPart]`. Rules: text joined and split at `max_text`; quick replies up to `max_buttons` become `ButtonsPart` (labels cut to `max_button_label`), up to `max_list_rows` become `ListPart`, otherwise numbered text "1. ... 2. ..." plus i18n `channel.reply_with_number`; CardBlock becomes text `*title*` plus `label: value` lines; ApprovalCardBlock becomes summary plus i18n `channel.open_in_app` with `{MIA_PUBLIC_URL}/approvals/{id}`, never buttons; FormBlock and FileBlock become `channel.open_in_app` links; `sensitive=True` replaces everything with one `channel.sensitive` text plus link.
- `registry.py`: `register(adapter)`, `get(channel_id) -> ChannelAdapter` (KeyError), `enabled(org: str | None = None) -> list[ChannelAdapter]` (registered and `orgconfig.load().channels[id].enabled`).
- orgconfig: `class ChannelConfig(BaseModel): enabled: bool = False`; `OrgSettings.channels: dict[str, ChannelConfig] = {}`.

- [ ] Step 1: failing render tests, one per rule above (3 buttons, 5 options to list, 12 options to numbered text, long text split, approval card has no ButtonsPart, sensitive replaces all).
- [ ] Step 2: FAIL. Step 3: implement. Step 4: PASS.
- [ ] Step 5: layout.md gets the channels tree from the spec; commit "Channel base types, registry and fallback rendering".

### Task 4: Simulator adapter and contract suite

**Files:**
- Create: `node/mia/channels/simulator.py`, `node/tests/channels/test_contract.py`, `node/tests/channels/conftest.py`

**Interfaces:**
- `SimAdapter(capabilities=WHATSAPP_LIKE, secret="sim-secret")`: webhook body is JSON `{"messages": [...], "statuses": [...]}` signed like WhatsApp; `send` appends the payload to `self.sent` and returns `DeliveryResult(ok=True, channel_message_id=new_id())`; `fail_next: str | None` makes the next send return that error code.
- Contract fixture `adapter` parametrised over `["sim", "whatsapp"]` (the whatsapp param is skipped until Task 8 adds it): each adapter module provides `contract_kit()` returning `(adapter, make_inbound_body(address, text, msg_id, button=None) -> bytes, sign(body) -> dict[str,str], sent_bodies() -> list[dict])`.
- Contract tests: good signature verifies; bad and missing signature fail; text and button tap parse into `InboundMessage`; a status body parses into `StatusUpdate`; `render` output for every block type respects capabilities; `send` returns a channel message id.

- [ ] Steps: failing tests, FAIL, implement, PASS, commit "Simulator adapter and shared channel contract suite".

### Task 5: Linking and invites

**Files:**
- Create: `node/mia/channels/linking.py`
- Modify: `node/mia/cli.py` (`mia invite NAME`), `node/mia/core/people.py` (deactivate revokes), `node/mia/i18n/strings.py`
- Test: `node/tests/channels/test_linking.py`

**Interfaces:**
- `create_code(session, actor, person, purpose: Literal["invite","self"]) -> str` (returns the plain code once; stores HMAC).
- `invite_link(code: str) -> str` gives `https://wa.me/{MIA_WA_NUMBER digits}?text=LINK%20{code}`.
- `parse_link_text(text) -> str | None` matches `^\s*LINK\s+(\d{6})\s*$` (case-insensitive).
- `redeem(session, channel, address, code, now) -> RedeemResult` with `status: Literal["linked","invalid","expired","used","taken","blocked"]` and `person: Person | None`. Records a `ChannelLinkAttempt` every time; `blocked` when 5 failed attempts in the last hour.
- `identity_for(session, channel, address) -> ChannelIdentity | None` (active only).
- `revoke_all(session, actor, person)`.

- [ ] Step 1: failing tests: code stored hashed (plain code not in DB); redeem links and sets verified_at and consent_at; reuse returns `used`; expired returns `expired`; address active for another person returns `taken` and notifies the code's creator; 6th wrong attempt within an hour returns `blocked` even with a valid code; deactivate revokes identities; `mia invite Sa` with two matches exits with the match list (Review Focus 4).
- [ ] Step 2 to 4: FAIL, implement (`hmac.new(secret, code, sha256)`; `secrets.randbelow(10**6)` zero-padded; refuse when `MIA_NODE_SECRET` is empty), PASS.
- [ ] Step 5: commit "One-time code linking and invites".

### Task 6: Outbox, transport and deliver

**Files:**
- Create: `node/mia/channels/outbox.py`, `node/mia/channels/transport.py`, `node/mia/channels/service.py` (deliver part)
- Modify: `node/mia/chat/channels.py` (notify calls deliver), `node/mia/agents/dispatcher/cover.py` (cover.ask passes template and urgent), `node/mia/api/main.py` (ticker runs outbox)
- Test: `node/tests/channels/test_deliver.py`, `node/tests/channels/test_outbox.py`

**Interfaces:**
- `deliver(session, person, blocks, actor, *, kind="message", template: TemplateCall | None = None, sensitive=False, urgent=False, now=None) -> list[ChannelOutbox]`.
  For each enabled adapter with an active identity: window open (`last_inbound_at` within `session_window_hours`) queues rendered payloads; closed queues `template or mia_new_message` and stores the rendered message as `held` rows; not urgent and inside quiet hours sets `send_after` to the next quiet-hours end in branch time.
- `notify(...)` gains keyword args `template=None, urgent=False, sensitive=False` and calls `deliver` after storing the app copy.
- `async def outbox.send_due(now) -> int`, run by the ticker: loads due `queued` rows (ordered by id) and increments `attempts` in one short transaction inside `asyncio.to_thread`, commits, awaits `adapter.send` for each, then records each result in its own short transaction inside `asyncio.to_thread`. Returns rows sent.
- `outbox.release_held(session, identity) -> int` turns held rows for that identity into queued.
- `transport.ChannelTransport(inner=None)`: httpx transport that emits a `channel.sent` event per request with channel, person id and payload SHA-256 (never content). Used by `WhatsAppAdapter`'s client.
- Retry: on error, `send_after = now + [1, 5, 30][attempts-1]` minutes; after the third failure `failed` plus event `channel.failed`. Error `131047` re-queues once as `mia_new_message` and holds the original.

- [ ] Step 1: failing tests: window open queues rendered payloads; window closed queues `mia_cover_request` for kind cover_request, `mia_new_message` otherwise, plus held rows; `release_held` then sends held after reply (Review Focus 3, one send only); non-urgent at 23:00 Helsinki gets `send_after` 06:00 and is due at exactly 06:00 (Review Focus 5); sensitive never reaches `adapter.sent` with content; disabled channel queues nothing; retry schedule and final failed; 131047 path; idempotency key duplicate is skipped; app copy always stored.
- [ ] Step 2 to 4: FAIL, implement, PASS. Cover flow: in `_tell` for key `cover.ask`, pass `template=TemplateCall(name="mia_cover_request", lang=person.language, params=[first name, location, date, time], buttons=[t("cover.reply_accept"), t("cover.reply_decline")])`, `urgent=True`.
- [ ] Step 5: commit "Outbox, channel transport and deliver for proactive messages".

### Task 7: Inbound handling and webhook router

**Files:**
- Modify: `node/mia/channels/service.py` (handle_inbound), `node/mia/api/main.py` (include router, ticker retries pending inbound)
- Create: `node/mia/channels/router.py`
- Test: `node/tests/channels/test_inbound.py`

**Interfaces:**
- `GET /channels/{channel_id}/webhook` returns the challenge as plain text or 403.
- `POST /channels/{channel_id}/webhook` (sync `def`): verify signature (403 plus `channel.webhook_rejected` event), parse, insert inbound rows (skip duplicates by unique key, catching IntegrityError per row), apply status updates, commit, schedule `handle_inbound(row_id)` per new row with `BackgroundTasks`, return `{"ok": true}`.
- `async def handle_inbound(inbound_id: str) -> None`: own session; unlinked plus LINK text runs `redeem` and replies with `channel.linked` or the matching error key; unlinked otherwise replies `channel.not_linked` and marks `ignored`; linked: update `last_inbound_at`, `release_held`, text is `button or text`, normalised by `normalise_button(text, lang)` (case-folds and strips emoji and punctuation, maps any language's accept or decline label to the person's language label), runs `run_turn` in the person's latest thread with the dispatcher, then `deliver(reply blocks, urgent=True)`; media only replies `channel.text_only`. Exceptions mark the row `failed`, reply `channel.error` once, never retried.

- [ ] Step 1: failing tests: bad signature 403 and nothing stored; unlinked plus injection text gets only `channel.not_linked`, no `tool.called` events; `LINK <code>` links; linked "Olen kipeä huomenna" produces an absence and a reply in outbox; same webhook posted twice gives one turn (Review Focus 2); button "✅ HYVÄKSYN" and "Accept" both accept a cover request for a Finnish speaker (Review Focus 1); status update marks outbox delivered; exception path marks failed and sends one apology.
- [ ] Step 2 to 4: FAIL, implement, PASS. Step 5: commit "Inbound channel handling and webhook router".

### Task 8: WhatsApp adapter

**Files:**
- Create: `node/mia/channels/whatsapp/__init__.py`, `adapter.py`, `templates.py`, `node/tests/channels/whatsapp_samples/*.json`
- Modify: `node/tests/channels/test_contract.py` (enable whatsapp param), `node/mia/api/main.py` (register adapters at startup when settings present)
- Test: `node/tests/channels/test_whatsapp.py`

**Interfaces:**
- `WhatsAppAdapter(settings, transport=None)`; `channel_id = "whatsapp"`; capabilities from Global Constraints.
- Send: `POST {MIA_WA_GRAPH_URL}/{MIA_WA_PHONE_NUMBER_ID}/messages`, `Authorization: Bearer {MIA_WA_TOKEN}`, body `{"messaging_product":"whatsapp","to":addr,...}`:
  text `{"type":"text","text":{"body":...}}`; buttons `{"type":"interactive","interactive":{"type":"button","body":{"text":...},"action":{"buttons":[{"type":"reply","reply":{"id":"b0","title":...}}]}}}`; list `{"type":"interactive","interactive":{"type":"list","body":{"text":...},"action":{"button":<channel.choose>,"sections":[{"rows":[{"id":"r0","title":...}]}]}}}`; template `{"type":"template","template":{"name":...,"language":{"code":...},"components":[{"type":"body","parameters":[{"type":"text","text":p}]}]}}`.
  Response `messages[0].id`; error `error.code` as string.
- Receive: `entry[].changes[].value.messages[]` (`from`, `id`, `timestamp`, `type` text uses `text.body`, interactive uses `button_reply.title` or `list_reply.title`, template button uses `button.text`, other types set `has_media`), `statuses[]` (`id`, `status`, `errors[0].code`).
- `templates.py`: `TEMPLATES = {"mia_new_message": Template(params=0, langs=("fi","en")), "mia_cover_request": Template(params=4, langs=("fi","en"))}`; `render_template` refuses unknown names or wrong parameter counts.

- [ ] Step 1: failing tests: payload shapes for text, buttons, list, template against saved samples; receive parses the four inbound shapes and a failed status; unknown template refused; adapter's HTTP goes through `ChannelTransport` (event emitted, payload hash only); contract suite passes for whatsapp.
- [ ] Step 2 to 4: FAIL, implement, PASS. Step 5: commit "WhatsApp Cloud API adapter".

### Task 9: End to end, guards, docs

**Files:**
- Test: `node/tests/channels/test_e2e.py`, `node/tests/test_architecture.py`
- Modify: `docs/layout.md`, `docs/questions.md` (Q8, Q9), `docs/adr/007-channel-adapters.md` (Status: Accepted), `README.md` (commands), `node/config/org/demo/settings.yaml` (`channels: {whatsapp: {enabled: false}, sim: {enabled: true}}`)
- Create: `docs/whatsapp-setup.md`

- [ ] Step 1: e2e over sim: `add_person`, `create_code`, inbound `LINK`, Juha reports sick, Sanna asks for cover and assigns Mikael (Mikael's window closed, so `mia_cover_request` queued), Mikael taps Hyväksyn, Sanna's update queued; assert visit reassigned, `verify_chain` true, every channel message has an app copy.
- [ ] Step 2: architecture guards: httpx imports in `mia/channels` only in transport.py and whatsapp/adapter.py; `agents/` and `chat/` import nothing from `mia.channels.whatsapp` or `mia.channels.simulator`.
- [ ] Step 3: docs; `mia channels sim "text" --from ADDRESS` CLI for local trials.
- [ ] Step 4: full check (ruff, format, mypy, pytest, evals); commit "Channels end to end test, guards and setup docs".
