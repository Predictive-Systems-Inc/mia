# CopilotKit and AG-UI practices for Mia's chat layer

Studied: CopilotKit `main` at 0365592 (MIT) and ag-ui-protocol/ag-ui `main` at 97f789c (MIT),
October 2026. Only MIT code was read. CopilotKit Intelligence (`runner/intelligence.ts`,
`handlers/intelligence/*`, `intelligence-platform/*`, `runtime-python/copilotkit_intelligence`)
and the proprietary `showcase/` were skipped. No code was copied; every adopted practice is
reimplemented in Mia's style. No dependency was added.

Links: `CK` = https://github.com/CopilotKit/CopilotKit/blob/main/packages/,
`AG` = https://github.com/ag-ui-protocol/ag-ui/blob/main/.

Folder note: `docs/research/` is new. It holds studies of outside code that inform decisions
but are not decisions themselves (those stay in docs/adr/).

## What Mia had before

`POST /ag-ui` handed the request straight to Pydantic AI's `AGUIAdapter.dispatch_request`. That
meant: no thread or message was stored (the client owned the history and could forge past
turns), client-declared frontend tools and state reached the agent, the user's words were not
wrapped (rule 8), the output tool's raw blocks went to the client without `check_blocks`
(invented approval cards could show), RUN_ERROR carried `str(exception)`, and a dropped
connection cancelled the run. There was no way to reconnect.

## Practices

### 1. Runs outlive the connection; reconnect and catch up (adapted)

- **CopilotKit:** an `AgentRunner` interface with `run`, `connect`, `isRunning` and `stop`
  (CK `runtime/src/v2/runtime/runner/agent-runner.ts`). `InMemoryAgentRunner` starts the agent
  eagerly and pushes every event into a replay buffer (CK `runtime/src/v2/runtime/runner/in-memory.ts`
  lines 609-884), so a client abort only unsubscribes (CK
  `runtime/src/v2/runtime/handlers/shared/sse-response.ts`). `connect` replays the thread's
  compacted events and then follows the live run (in-memory.ts 886-937). `SqliteAgentRunner`
  stores every run's events in `agent_runs` and a `run_state` row (CK
  `sqlite-runner/src/sqlite-runner.ts`). Routes: `/agent/:id/run`, `/connect`, `/stop/:threadId`
  (CK `runtime/src/v2/runtime/core/fetch-router.ts`).
- **AG-UI:** no protocol-level resume. The HTTP binding says SSE `Last-Event-ID` is not used and
  a broken stream cannot be re-entered (AG `docs/spec/1.0/basic/transports/http-sse.mdx` 51-55).
  A stream may replay earlier history, but it MUST be restated as `MESSAGES_SNAPSHOT` /
  `STATE_SNAPSHOT` (AG `docs/spec/1.0/events/lifecycle.mdx` 192-208). `connect()` in the client
  is left to frameworks (AG `sdks/typescript/packages/client/src/agent/agent.ts` 409-484).
- **Mia now:** `mia/chat/runs.py`. A run is an asyncio task with its own session that keeps every
  event until it ends; `POST /ag-ui` follows it, `POST /ag-ui/connect` rejoins it (RUN_STARTED,
  then the stored history as MESSAGES_SNAPSHOT, then the run's events) or, when no run is live,
  returns the stored thread as one snapshot run (RUN_STARTED, MESSAGES_SNAPSHOT, one CUSTOM
  `mia.blocks` per assistant message, RUN_FINISHED). Approval cards in a snapshot show the
  approval's current status.
- **Why adapted, not adopted:** Mia already stores every message with its blocks, so catch-up
  uses those rows instead of an event log, and no table or migration is needed. The live
  registry is in-process (`mia serve` runs one worker); a shared store is the upgrade path if a
  node ever runs several workers. No Last-Event-ID cursor: AG-UI forbids mid-run resumption, and
  snapshots keep the stream valid for stock clients.

### 2. Server-owned history and input sanitising (adopted)

- **CopilotKit:** the runner keeps the thread's messages server side and fills `RUN_STARTED.input`
  with only the messages not seen in earlier runs (in-memory.ts 819-836).
- **Mia now:** the run uses the stored thread as history and takes only the newest user message
  from the client, wrapped in `<user_message>` (rule 8). Client `messages` history, `tools`,
  `state`, `context` and `resume` are dropped, so a client can neither forge turns nor declare
  tools the manifest does not list (rule 3). A new thread's `threadId` must be a ULID; another
  person's thread is a 404 (docs/questions.md Q17, answered by D15).

### 3. One run per thread, and stop (adopted)

- **CopilotKit:** a second run on a busy thread throws "Thread already running" (in-memory.ts
  619-643); `stop` aborts the run and finishes it cleanly with `RUN_FINISHED`, not an error
  (in-memory.ts 944-988, CK `runtime/src/v2/runtime/handlers/handle-stop.ts`).
- **AG-UI:** cancellation MUST close the run with `RUN_FINISHED` outcome `cancelled`
  (lifecycle.mdx 79-115).
- **Mia now:** a second run on a thread is a 409 (CopilotKit returns an empty 200 stream, which
  hides the reason). `POST /ag-ui/stop {threadId}` cancels the person's own run through Pydantic
  AI's `CancellationToken`; Pydantic AI then closes open parts and sends RUN_FINISHED. The
  `cancelled` outcome is not in the installed ag-ui-protocol 0.1.22 (Pydantic AI tracks it in
  ag-ui issue 880), so the outcome is absent for now.

### 4. Lifecycle and error events (adapted)

- **AG-UI:** a stream begins with RUN_STARTED or RUN_ERROR; nothing but a new RUN_STARTED follows
  RUN_ERROR; RUN_FINISHED needs every text message and tool call closed (lifecycle.mdx 14,
  177-188; AG `sdks/typescript/packages/client/src/verify/verify.ts`). RUN_ERROR has `message`
  and an open `code` (lifecycle.mdx 117-130).
- **CopilotKit:** `finalizeRunEvents` closes open parts and emits RUN_ERROR `INCOMPLETE_STREAM`
  when a stream ends without a terminal event (CK `shared/src/finalize-events.ts`).
- **Mia:** Pydantic AI's AG-UI stream already closes open parts before RUN_ERROR and emits the
  lifecycle events, so Mia does not reimplement finalising. Mia adds: RUN_ERROR carries the
  translated `chat.error` text and a code (`agent_error`, `internal_error`), never exception
  text (that goes to the log); a failure before the agent starts still opens the run with
  RUN_STARTED.

### 5. Generative UI: blocks as a CUSTOM event (adapted)

- **AG-UI:** CUSTOM events carry app-specific payloads; names should have a vendor prefix and
  unknown names are ignored (AG `docs/spec/1.0/events/passthrough.mdx` 40-66). AG-UI is not a
  generative UI spec (AG `docs/concepts/generative-ui-specs.mdx`); ACTIVITY_SNAPSHOT/DELTA and
  STATE_SNAPSHOT/DELTA exist for richer cases (AG `docs/spec/1.0/events/activity.mdx`, `state.mdx`).
- **CopilotKit:** renders tool calls by tool name with partial JSON args (CK
  `react-core/src/v2/hooks/use-render-tool-call.tsx`) and activity messages by type (CK
  `react-core/src/v2/hooks/use-render-activity-message.tsx`).
- **Mia now:** the output tool's call (raw, unchecked blocks) is hidden. After `check_blocks`
  and storage, the reply goes out as one text message whose id is the stored message id (so a
  later snapshot reconciles by id) and a CUSTOM `mia.blocks` event with the `ChatReply`. Stock
  clients show the text; Mia's apps render the blocks. Streaming blocks as they form (partial
  JSON, as CopilotKit does) is skipped: it would show approval cards before they are checked.
  ACTIVITY and STATE events are skipped until a block needs live updates.

### 6. Human-in-the-loop (skip, keep Mia's approvals)

- **AG-UI:** a run pauses by finishing with outcome `interrupt` and `Interrupt` objects; the
  client resumes with a new run carrying `resume[]` that must cover every interrupt (AG
  `docs/spec/1.0/basic/patterns/interrupt-resume.mdx`, AG `docs/concepts/interrupts.mdx`).
  Frontend tools finish the run with `pendingToolCallIds` and the result comes back as a tool
  message (AG `docs/spec/1.0/events/tool-calls.mdx` 155-177).
- **CopilotKit:** `useInterrupt` (CK `react-core/src/v2/hooks/use-interrupt.tsx`) and
  `useHumanInTheLoop` (CK `react-core/src/v2/hooks/use-human-in-the-loop.tsx`), both client side.
- **Mia:** skip. Risky tools call `approvals.request()` and stop (rule 3); the approval is a
  durable row, decided later, possibly by another person, on another device or channel, through
  `/approvals/{id}/decide`. An AG-UI interrupt is tied to one thread and one client and would let
  the requester's own client answer it. `resume` is dropped from client input. If a future
  in-run confirmation is wanted (for example "confirm this low-risk change"), map it to an
  interrupt with `reason: "confirmation"` and keep money, external and delete on approvals.

### 7. Testing (adopted)

- **AG-UI:** a conformance corpus of 69 stream fixtures (AG `spec/1.0/conformance/streams/`), the
  client verifier tests (AG `sdks/typescript/packages/client/src/verify/__tests__/`), and Python
  event-sequence tests in integrations (for example AG
  `integrations/adk-middleware/python/tests/test_event_bookending.py`).
- **CopilotKit:** runner tests with a scripted fake agent and the AG-UI verifier (CK
  `runtime/src/v2/runtime/runner/__tests__/in-memory-runner.test.ts`, `in-memory-runner.e2e.test.ts`).
- **Mia now:** `node/tests/test_ag_ui.py` has `assert_well_formed()`, a small port of the
  verifier's rules, applied to every stream (run, rejoin, snapshot, agent error, setup error),
  plus negative tests: forged history and tools ignored, other people's threads (run, connect,
  stop), busy thread, bad input, missing actor, wrong content type, error text not leaked.

### Also noted, not adopted

- Thread listing and history endpoints (CK `runtime/src/v2/runtime/handlers/intelligence/threads.ts`
  local fallback): useful for the app's thread list later; `/ag-ui/connect` covers catch-up now.
- Request hooks for auth (CK `runtime/src/v2/runtime/core/hooks.ts`): Mia's routes already call
  `resolve_actor` and tools call `rbac.require`; a proxy runtime would bypass that (rules 4, 5).
- SSE keep-alive comments (CK `runtime/src/v2/runtime/handlers/shared/sse-keep-alive.ts`): add
  if proxies cut idle streams during long tool calls.
- Suggestions endpoint, user memories, cloud persistence: out of scope or against rules 6 and 9.
