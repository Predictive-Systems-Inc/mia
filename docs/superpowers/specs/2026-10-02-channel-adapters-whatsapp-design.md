# Channel adapters and WhatsApp: design

Date: 2026-10-02. Status: draft for review. Decision D13 (local node only, no Mia Cloud).
Builds on spec.md, sections "Chat interface", "Channel adapter interface", "Graceful fallback",
"Channel rules"; ADR 005 and decisions D10, D11 (confirmation flow, quiet hours).

## 1. Goal

People reach the local Mia Node from WhatsApp the same way they reach it from the app. Success:
the README demo works end to end over WhatsApp. A supervisor adds and invites a person, the person
links their number, a cleaner reports sick, a supervisor finds cover and assigns, the picked
cleaner confirms with a button tap, and the supervisor is told.

The channel layer is pluggable: agents, the chat service and the cover flow never know which
channel a message travels on. Adding Viber, Messenger or SMS later means adding an adapter
folder that passes the contract suite, with no change to agents.

### Decisions taken in design
| Topic | Decision |
|---|---|
| First channel | WhatsApp Business Platform (Meta Cloud API), called directly with httpx. No provider, no new dependency. |
| Webhook reachability | Cloudflare Tunnel (`cloudflared`) beside the node, stable hostname. |
| Identity | One-time code (spec default). No phone numbers stored on `person`. |
| Invites | Click-to-chat link `https://wa.me/<number>?text=LINK%20<code>` plus a QR of it. |
| Proactive messages | WhatsApp first for linked people; the app thread always keeps a copy. |
| Outside the 24 hour window | Approved templates: a specific template per kind when one exists, else `mia_new_message` with the full message held until the person replies. |
| Add person | In scope: core service plus `mia person add`. |

### Out of scope
Mia Cloud; voice (CallAdapter stub stays); inbound media handling (reply "text only for now");
other channels (the interface and contract suite are built, the adapters are not); encryption
of channel tokens at rest (see 7).

## 2. Architecture

```
node/mia/channels/
  base.py        ChannelAdapter protocol and its models (below)
  registry.py    register(adapter); get(channel_id); enabled(org) from org settings.yaml
  render.py      shared fallback rendering of Mia blocks by ChannelCapabilities
  service.py     deliver(...) outbound; handle_inbound(...) inbound
  outbox.py      due rows -> send, retry with backoff, delivery statuses
  linking.py     create_code, redeem, unlink
  transport.py   ChannelTransport: the only HTTP exit for channels
  router.py      GET and POST /channels/{channel_id}/webhook
  simulator.py   "sim" adapter for tests and local development
  whatsapp/
    adapter.py   WhatsAppAdapter
    templates.py template registry (name, language, parameters, buttons)
```

### Interface (from spec.md, adapted to the code base)
```python
class ChannelCapabilities(BaseModel):
    max_text: int                 # WhatsApp 4096
    max_buttons: int              # reply buttons, WhatsApp 3
    max_button_label: int         # WhatsApp 20
    max_list_rows: int            # list message, WhatsApp 10 (0 = no lists)
    session_window_hours: int | None   # WhatsApp 24; None = no window
    supports_templates: bool

class ChannelAdapter(Protocol):
    channel_id: str
    capabilities: ChannelCapabilities
    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool
    def verify_subscription(self, params: Mapping[str, str]) -> str | None  # GET handshake
    def receive(self, body: bytes) -> list[InboundMessage | StatusUpdate]
    def render(self, message: OutboundMessage) -> list[ChannelPayload]
    def render_template(self, template: TemplateCall) -> ChannelPayload
    async def send(self, payload: ChannelPayload) -> DeliveryResult
    async def fetch_media(self, ref: MediaRef) -> bytes   # not used in Phase 1
```
`InboundMessage`: channel, address (the sender's channel id, the WhatsApp `wa_id`), channel
message id, text, button value, media ref, timestamp. `OutboundMessage`: person, thread,
blocks, kind, sensitivity. `ChannelPayload`: JSON body plus idempotency key. `DeliveryResult`:
channel message id or error code.

### Changes to existing code
- `chat/channels.py notify()` keeps storing the app copy and then calls `channels.deliver()`.
  Its callers (cover flow, supervisor updates) do not change.
- `api/main.py` includes the channels router; the ticker also runs `outbox.process_due()` and
  retries pending inbound rows.
- `cli.py`: `mia person add`, `mia invite NAME`, `mia channels sim "text" --from ADDRESS`.
- `test_architecture.py`: in `mia/channels`, only `whatsapp/adapter.py` and `transport.py`
  may import httpx; `agents/` and `chat/` import nothing from `channels/<adapter>`.
- `docs/layout.md`: add the channels package (ADR 007).

## 3. Data (data standard 1.2, migration 0003)

| Table | Fields | Notes |
|---|---|---|
| `channel_identities` | id, branch_id, person_id, channel, address, verified_at, consent_at, last_inbound_at, status | unique (channel, address) among active rows |
| `channel_link_codes` | id, branch_id, person_id, code_hmac, purpose (invite or self), expires_at, used_at, created_by | 6 digits, HMAC with `MIA_NODE_SECRET` |
| `channel_link_attempts` | id, channel, address, attempted_at, ok | lockout counting |
| `channel_outbox` | id, branch_id, person_id, channel, kind, payload, template, idempotency_key (unique), status, attempts, send_after, channel_message_id, error_code, held_message_id | status: queued, sent, delivered, read, failed, held |
| `channel_inbound` | id, channel, channel_message_id (unique with channel), address, person_id, body, status, error | status: pending, done, failed, ignored |

All writes go through `store.insert` / `store.update` and emit events (rule 1).
`people.add_person(session, actor, name, roles, language, ...)` is a new core service.

## 4. Data flow

### Inbound
1. `POST /channels/{id}/webhook`: `verify_webhook` on the raw body; 403 and an event if it fails.
2. `receive` parses messages and status updates. Messages are inserted into `channel_inbound`
   (duplicates skipped by the unique key), the transaction commits, the route returns 200.
3. A background task runs `handle_inbound` for each new row. The ticker retries rows left
   `pending` after a restart.
4. `handle_inbound`:
   - Unlinked address: text matching `LINK <6 digits>` runs `linking.redeem`; anything else
     gets a fixed public reply (i18n key) and status `ignored`. No agent runs.
   - Linked address: set `last_inbound_at`, release any `held` outbox rows for that identity,
     map a button tap to its value text, run `chat.service.run_turn` in the person's latest
     thread, and `deliver` the reply immediately (not via the ticker).
   - Status updates set the outbox row status by channel message id.
   - Media without text: i18n "text only for now" reply and an event.

### Outbound: `deliver(session, person, blocks, actor, kind, sensitivity)`
1. Callers have already stored the app copy (notify or the chat reply).
2. For every enabled channel with an active identity for the person:
   - Sensitive blocks become "View in the Mia app" with a link.
   - Quiet hours (D11, org settings) set `send_after`, except the D11 urgent cover rule.
   - Window open (`last_inbound_at` within `session_window_hours`): `render` the blocks.
   - Window closed: the template for `kind` if one exists, else `mia_new_message`; the rendered
     full message is stored as a `held` row, sent when the person next writes.
   - Insert into `channel_outbox` with an idempotency key, commit.
3. `outbox.process_due` sends due rows through the adapter. Retries at 1, 5 and 30 minutes, then
   `failed` and an event. Meta error 131047 (outside window) re-sends once as `mia_new_message`.

### Rendering on WhatsApp
| Block | WhatsApp |
|---|---|
| Text | text message, split above 4096 characters |
| Quick replies, up to 3 | reply buttons, labels cut to 20 characters |
| Quick replies, 4 to 10 | list message |
| Card | text with a bold title and one line per field |
| Approval card | summary plus a link to the app, never decision buttons |

### Templates (Phase 1, Finnish and English each)
`mia_new_message`, `mia_cover_request` (buttons Hyväksyn / En pysty), `mia_cover_update`,
`mia_approval_waiting`. Templates are created in WhatsApp Manager by hand; `templates.py` holds
their names, languages and parameter order, and a template not listed there is never sent.

## 5. Linking and invites
- `mia invite NAME` (and a supervisor tool later) creates a code valid 7 days and prints the
  wa.me link and a QR (rendered as text in the terminal). A person asking in the app for their
  own code gets one valid 10 minutes.
- Redeem: code HMAC matches, not used, not expired, address not active for another person.
  Then the identity is created with `verified_at` and `consent_at` (the person messaged first),
  the code is marked used, and a welcome is sent in the person's language.
- 5 failed attempts from one address within an hour block that address for an hour.
- An address already linked to someone else is refused and the inviting supervisor is notified.
- Deactivating a person sets their identities to `revoked`.

## 6. Security
- Signature: HMAC SHA-256 of the raw body with `MIA_WA_APP_SECRET`, compared with
  `hmac.compare_digest`. GET handshake checks `MIA_WA_VERIFY_TOKEN`.
- `ChannelTransport` (httpx transport, like `EgressTransport`): refuses payloads built from
  sensitive blocks, refuses channels switched off for the organisation, logs channel, person,
  payload hash and channel message id as an event; never the content.
- Inbound text goes through `run_turn`, so the `<user_message>` boundary, RBAC and approvals
  apply unchanged. Money, external and delete approvals are never decided on a channel.
- Settings: `MIA_WA_TOKEN`, `MIA_WA_APP_SECRET`, `MIA_WA_VERIFY_TOKEN`,
  `MIA_WA_PHONE_NUMBER_ID`, `MIA_WA_GRAPH_URL` (default Meta Graph API, versioned),
  `MIA_NODE_SECRET`, `MIA_PUBLIC_URL` (for links). Placeholders in `.env.example`.

## 7. Assumptions to record in docs/questions.md
- Q8: channel tokens live in `.env` with file permissions in Phase 1; the spec's encryption at
  rest comes with field encryption. Not blocking.
- Q9: one thread per person and agent is shared by the app and WhatsApp. Not blocking.

## 8. Error handling
| Failure | Behaviour |
|---|---|
| Meta unreachable, timeout, 5xx | retry 1, 5, 30 minutes, then `failed` and an event; the app copy stands |
| 131047 outside window | one re-send as `mia_new_message`, full message held |
| Template missing, rejected, paused | `failed` with the error code and an event; `/health` lists failing channels |
| Exception in `handle_inbound` | row `failed` with the error, one apology reply; never retried (an agent turn could act twice) |
| Expired or used code | clear reply, no change |

## 9. Testing
- Contract suite (`tests/channels/test_contract.py`), parametrised over every registered
  adapter (`sim`, `whatsapp` with `httpx.MockTransport`): webhook verify good and bad, parse
  text and button taps, de-duplication, render every block within capabilities, send, statuses.
- Unit: render fallbacks; linking (hash, single use, expiry, lockout, taken address, revoke);
  deliver (window open and closed, template choice, held release, quiet hours, urgent rule);
  outbox (backoff, failure, 131047, idempotency); WhatsApp payloads against saved sample bodies.
- Negative: bad signature (403, nothing processed); unlinked sender with an injection attempt
  (public reply only, no agent run); sensitive block never reaches the transport; approval card
  has no decision buttons; disabled channel sends nothing; wrong or reused code refused.
- End to end over `sim`: person add, invite, link, the README demo with Mikael's window closed
  so `mia_cover_request` is used; visit reassigned, event chain verifies, every message has an
  outbox row and an app copy.
- Architecture guards as in 2.
- Manual checklist (docs/whatsapp-setup.md): Meta app setup, cloudflared, webhook registration,
  LINK from a real phone, the demo.
