# Decisions from the product owner

Answers to docs/questions.md. Reference the question number. Decisions that change the spec also get an ADR.

## D1: (answers Q1)
- Decision:
- Reason:

## D1: (answers Q2) An explicit instruction is the approval
- Decision: when a person with the required role explicitly instructs Mia (for example the
  supervisor says "Assign Mikael"), that instruction counts as the approval and the change is
  applied directly. Mia asks for approval only when it acts on its own decision, when no rule
  covers the case, or when payment or money is involved.
- Reason: the user already decided; a second approval step by the same person adds nothing.

## D2: (answers Q1) `MIA_MODEL=test` runs the rules model
- Decision: keep `test` as the deterministic rules model (FunctionModel plus the rules classifier
  named in the manifest). Pydantic AI's TestModel is used directly in unit tests only.
- Reason: no API key needed, deterministic, and the brief, CI and .env.example stay unchanged.

## D3: (answers Q3) Job and Visit live in core
- Decision: location, job and visit are core data standard tables. The cleaning template adds
  only industry extras (sites, checklists, availability, working-hour limits).
- Reason: other industries reuse jobs and visits.

## D4: (answers Q4) Visit lookup through optional tool inputs
- Decision: find_replacements also accepts location_name, date and time; get_my_visits also
  accepts person_name (permission checked). No separate search tool.
- Reason: keeps the tool set at four while supporting natural requests.

## D5: (answers Q5) Evals command
- Decision: `uv run pytest node/tests/evals -m evals` (or `uv run pytest -m evals`); tests stay
  under node/tests.
- Reason: matches the layout; README and CI already use it.

## D6: (answers Q6) Travel in ranking, home base, cleaner confirmation
- Decision: rank replacements by added travel (from the previous visit that day, or the
  cleaner's home base address). Coordinates come from geocoding addresses. Each cleaner has a
  home base address. After the supervisor picks a candidate, Mia asks that cleaner to confirm;
  the visit changes only when the cleaner accepts. On decline, the supervisor is told and the
  next candidate is offered.
- Open follow-ups: geocoding provider, where home base is stored, confirmation timeout.

## D7: (answers Q6a) Geocoding is a tool with pluggable providers
- Decision: geocoding is a core tool with one interface and swappable providers, chosen by
  configuration. First provider: Digitransit (Finland). Requests leave the node only through
  the egress layer and are logged; results are cached so each address is geocoded once.
- Reason: Finnish address quality now, other countries (Philippines) later without code changes.

## D8: (answers Q6b) Home base on the person, data standard 1.1
- Decision: home address and its coordinates are person fields in the core data standard
  (version 1.1, ADR to follow), encrypted with other contact details when field encryption lands.
- Principle (applies to all later choices): every design decision must fit the architecture so
  the system stays easy to maintain. Shared, industry-neutral data goes in the core standard;
  industry fields in templates; agent working data in agent tables; external services behind
  tools with pluggable providers and the egress layer.

## D9: Employee data is shared data
- Decision: all employee data lives in the core data standard (1.1): home base address and
  coordinates, skills, weekly availability and working-hour limits. The tables
  cleaning_availability and cleaning_work_limits move to core. The cleaning template keeps only
  industry data (sites, checklists).
- Reason: employee data is industry-neutral and reused by every shift business and agent.

## D10: (answers Q6c) Confirmation escalation: message, then call, then next candidate
- Decision: Mia messages the picked cleaner for confirmation; with no response it escalates to a
  phone call; with still no response it moves to the next candidate and tells the supervisor.
- Build note: voice is deferred (brief non-goal), so the call step goes behind a channel
  adapter interface with a stub that logs the call request; the real voice adapter plugs in
  later. Calls only to people who agreed to calls, respecting quiet hours (spec, Voice rules).
- Open: timings for each step.

## D11: (answers Q6d) Confirmation timings and quiet hours
- Decision: organisation settings with these defaults: wait 15 minutes after the message, then
  call; wait 10 minutes after the call, then move to the next candidate and tell the supervisor.
  If the visit starts within 60 minutes, call at once and move on after 5 minutes. Quiet hours
  (21:00 to 06:00): urgent cover (visit before 10:00 next morning) may message during quiet
  hours but never call before 06:00; other requests wait until quiet hours end.

## D12: (answers Q7) Old marketing site removed
- Decision: the Netlify site (index.html, netlify/, netlify.toml) is discarded; Mia has a new
  website elsewhere. This repository holds only the Mia ERP monorepo.

## D13: Focus on the local node; Mia Cloud is not built yet
- Decision: build only the Mia Node for now: a local instance that answers through chat (Mia
  apps over AG-UI) and outside channel adapters (spec, Channel adapter interface). Mia Cloud
  (configuration UI, bundle sync, catalogue) is not built until decided otherwise; configuration
  stays in node/config.
- Changes the Phase 1 plan: outside channels move from deferred to in scope. Cloud model access
  through core/egress.py stays; that is the model gateway, not Mia Cloud.
- First channel: WhatsApp (WhatsApp Business Platform), following the spec build order.

## D14: Agents follow the A2A standard
- Decision: agent-to-agent communication follows A2A (Agent2Agent) 1.0. Mia agents publish
  signed Agent Cards and accept A2A tasks; AG-UI stays for apps, MCP for connectors, channel
  adapters for messaging apps. See ADR 008.

## D15: (answers the AG-UI thread id question) Thread ids stay ULIDs
- Decision: chat thread ids stay ULIDs (rule 10), also when an AG-UI client starts a thread with
  its own threadId. AG-UI's threadId is an opaque string, so Mia's apps send a ULID; other ids
  are rejected. No external-id column and no data standard change.

## D16: Agents are human roles; processes are for design and testing
- Decision: every agent is a hired role that mirrors a human job in the client's departments
  (dispatcher, client service, bookkeeper, recruiter and so on), with a job description, its own
  RBAC role and approvers. End-to-end processes (Lead-to-Contract, Contract-to-Service,
  Service-to-Cash, Hire-to-Retire, Procure-to-Pay, Record-to-Report) are how workflows are
  designed and tested across those agents; a process is never an agent. See docs/plan.md.

## D17: (answers Q10 to Q16) Authentication as designed
- Decision: accept docs/superpowers/specs/2026-10-05-authentication-design.md and ADR 011:
  data standard 1.3 adds auth_credentials, auth_devices, auth_sessions and auth_clients and
  renames channel_link_codes and channel_link_attempts to auth_codes and auth_attempts (Q10);
  no email in Phase 1, admin resets and `mia auth reset` for a locked-out owner (Q11); A2A clients
  act only as themselves, a claimed on_behalf_of is logged, not used (Q12); one 6-digit PIN as the
  step-up for money, external and delete approvals (Q13); staff codes over WhatsApp, no SMS
  provider until needed (Q14); standard library only, webauthn later for passkeys (Q15); MFA
  required for owner, admin and accountant and offered to supervisors, office sessions 12 h idle
  and 7 days at most, staff 30 days idle and 90 days at most (Q16).

## D18: Phase 1 runs a local model only
- Decision: real Hype data is handled by Gemma 4 12B on Ollama on the node; no cloud model route
  for real data in Phase 1. Cloud models are used for development and as the distillation
  teacher, with synthetic or demo data only. The pilot starts when the evaluation suite passes
  its target with the local model (85% on Oct 5; target 95%).

## D19: Node hardware for Hype
- Decision: an Apple Silicon Mac mini with 24 GB or more of unified memory, on site.

## D20: No cleaner mobile app in Phase 1
- Decision: cleaners work over WhatsApp: chat, absences, cover, check-in and check-out by
  location share, checklists with interactive lists and buttons, photos as media messages. The
  office uses the web app. Changes the proposal (an app was promised); agree it with Hype first.

## D21: Service agreements in the data standard
- Decision: add service agreements in Sprint 1 (client, sites, scope, frequency, price per visit
  or per square metre, index clause, start and end, versions), linked to the jobs and visits they
  generate. Master data with an owner; changes need approval.

## D22: A turn stops after 8 model calls
- Decision: a chat turn may make at most 8 model requests. On the cap the user gets a short
  translated reply that a supervisor will follow up, and the event is logged.

## D23: Restore tests are recorded; the tunnel exposes only webhooks before login
- Decision: `mia restore-test --record` writes each restore test as an event through a service
  function. Until authentication is built, the Cloudflare Tunnel publishes only the channel
  webhook paths.

## D24: The plan lists all necessary work, not an hour budget
- Decision: hour estimates are not a constraint; docs/plan.md includes all work Phase 1 needs.

## D25: (amends D20) The mobile app is a separate project; Mia focuses on chat
- Decision: the cleaner and office apps are built as a separate project. This repository
  focuses on the chat interface: the web chat over AG-UI and messaging channels (WhatsApp).
  Field work in Phase 1 stays over WhatsApp as in D20.

## D26: Language is a separate layer; the core is measured in English
- Decision: messages are translated to English before the model and replies translated back,
  by a separate, measurable translation layer. Intents, tools and evaluations are defined and
  measured in English first; translation quality is measured on its own. Revisit if the
  translation layer costs more accuracy than a multilingual model loses.

## D27: (refines D18) Where learning happens is the owner's choice
- Decision: retraining and label review run on the node by default. An owner may choose cloud
  training and review (stronger models, GPUs) in the organisation settings, if the data
  processing agreement covers it and the egress level allows it. The training set then leaves
  only through the egress component, pseudonymised with stricter scrubbing (identifying free
  text dropped), processed in the EU, not kept after the job; only the trained model returns.
  D18 still holds for answering: real messages are handled by the local model.
