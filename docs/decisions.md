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
- Note (role skill models): understanding uses the multilingual encoder; translation applies
  only to free-text replies, pending the bake-off.

## D27: (refines D18) Where learning happens is the owner's choice
- Decision: retraining and label review run on the node by default. An owner may choose cloud
  training and review (stronger models, GPUs) in the organisation settings, if the data
  processing agreement covers it and the egress level allows it. The training set then leaves
  only through the egress component, pseudonymised with stricter scrubbing (identifying free
  text dropped), processed in the EU, not kept after the job; only the trained model returns.
  D18 still holds for answering: real messages are handled by the local model.

## D28: Role classifier in chat: regex fallback, one routing step, original text on clarify
- Decision A: the dispatcher keeps the regex classifier's hint (including the injection line)
  as a fallback whenever the role model gives no confident intent (no package, low band, other).
  A confident role-model intent replaces the regex hint; an injection is flagged as data in both
  cases.
- Decision B: the web chat over AG-UI and the /chat endpoint share one classify-and-route step.
  For emergency, template and "Did you mean" routes the AG-UI run sends the reply as one
  assistant text message (options as text lines) and finishes without running the agent.
- Decision C: when a person taps a "Did you mean" option, the agent runs on the original
  message (found through original_message_id) with the chosen intent as a hint, not on the
  button label. A chosen template conversation intent gets its template reply instead.

## D29: Role skill models and their dependencies
- Decision: build docs/superpowers/specs/2026-10-06-skill-models-design.md; onnxruntime and
  tokenizers become node dependencies and training libraries an optional `learning` group
  (ADR 013).
- Approval: the dependency approval required by CLAUDE.md was given on 2026-10-06 by the Fable
  decision agent on the owner's behalf (the owner asked for Fable to decide while asleep).
- Reasons: onnxruntime (MIT) runs the role classifier on the node CPU in about 20 ms; tokenizers
  (Apache 2.0) is the encoder's tokenizer at inference without PyTorch on the node; group
  `learning` is torch (BSD), transformers (Apache 2.0), onnx (Apache 2.0) and accelerate
  (Apache 2.0) for training and ONNX export, installed only where training runs.
- Approved with six changes: transformers>=5,<6; onnxruntime>=1.22 and tokenizers>=0.22; mypy
  ignore_missing_imports for onnxruntime; an architecture test that mia/skills never imports
  huggingface_hub, and HF_HUB_OFFLINE=1 by default at node startup; a sha256 field on ModelCard
  artifacts (lands in Tasks 14 and 15); a uv index so torch uses CPU wheels on Linux.
- Footprint: installing tokenizers pulls huggingface-hub (with hf-xet, fsspec, tqdm, typer, rich) into the node install, and onnxruntime adds numpy and protobuf; the architecture test and HF_HUB_OFFLINE keep the node from fetching.

## D30: (answers Q18) Roles site_manager and admin; no chat role
- Decision: two roles join the roster. `site_manager` (Site manager) supports site quality,
  safety and compliance work and keeps the human supervisor in charge of decisions; it is not
  the human role `supervisor` (S), which stays as is. `admin` (Admin) owns master data, users and
  access, administration and management reporting. The proposed ids quality.* and office.*
  become site_manager.* and admin.*.
- No chat role: generic conversation is handled by Mia itself for every role through the shared
  conversation catalogue (node/mia/learning/catalogue/conversation.yaml), which every role
  inherits. The chat.* intents map as: greeting, thanks, help and change_language keep their
  names under conversation.*; talk_to_human -> conversation.request_human; cancel ->
  conversation.undo; clarify -> conversation.confusion; request_status ->
  conversation.are_you_there; app_feedback -> conversation.feedback_about_mia;
  privacy_question -> conversation.privacy_what_do_you_know; who_am_i and link_account ->
  admin.who_am_i and admin.link_account (account and access).
- One intent per message: site_manager.emergency, report_hazard, work_instructions and
  privacy_request merge into conversation.emergency, hazard_report, kb_cleaning_howto and
  privacy_rights_request (first contact by Mia, follow-up by the site manager); report_injury
  and chemical_safety stay separate because they cover more than injury_minor and
  kb_chemical_safety (serious and supervisor-reported injuries; exposures that already happened).
- Addendum (6 Oct 2026): one message, one label, because the classifier sees text and not the
  sender. (1) Questions about rules or company knowledge are the shared conversation kb_*
  intents. (2) Doing something stays with the role intent, which keeps only action messages.
  (3) The same message separated only by sender role is one intent with one owner (client
  details: admin.update_client; site access: admin.update_site; damage: site_manager.report_damage).
  report_injury keeps only reports about someone else; chemical_safety is split into the
  conversation intents. Review: docs/research/intent-overlap-review-2026-10-06.md.
- Consequences: docs/capabilities.md lists no chat area; intents.jsonl is relabelled; the
  classification eval accepts conversation.* ids as labels beside the catalogue ids and `other`.

## D31: Conversation intents merged after the embedding overlap review
- Context: the overlap review (docs/research/overlap-report-conversation.md and
  docs/research/intent-overlap-reference.md) showed conversation intents that one message could
  fairly get either of. One message, one label (D30): the owner decided on 2026-10-07 to merge
  five groups, so the catalogue goes from 93 to 87 conversation intents.

  | Removed | Survives as | Handling |
  | --- | --- | --- |
  | conversation.compliment | conversation.thanks | template (one reply fits both) |
  | conversation.rephrase_simpler | conversation.confusion | template |
  | conversation.kb_surface_care, conversation.kb_chemical_safety | conversation.kb_cleaning_howto | kb_cleaning |
  | conversation.self_harm_risk | conversation.distress | emergency |
  | conversation.personal_threat | conversation.emergency | emergency |

- Merges among intents with the same handling cost nothing at runtime: the reply was the same
  either way, and the classifier no longer has to split one meaning in two. The removed intents'
  examples and records moved to the survivor; survivor descriptions cover both.
- distress now runs the emergency script (crisis line, 112 or 911, supervisor told) by the
  owner's decision, so stress and despair get the stronger script rather than risk a missed
  self-harm message; distress joins safety_ids(). Exposures that already happened stay
  conversation.chemical_exposure.
- Kept apart, descriptions sharpened with one clause each saying what the other intent is not:
  goodbye / thanks, goodbye / greeting, the laughter pairs (affirm, greeting, emoji_only),
  kb_expenses_travel / kb_payment_invoicing and kb_household_tax_deduction / tax_personal_advice.
- Consequences: i18n drops conversation.compliment and its label, and the thanks and confusion
  replies are reworded to fit both meanings; intents.jsonl relabels 42 records; the merged pairs
  move to "## Merged (D31)" in the overlap reference so recall is not measured on them.
- Addendum (2026-10-08): the owner keeps distress merged with the emergency handling after
  seeing the script it triggers; a later layer will split distress from self-harm risk. The
  merged confusion intent keeps rephrase_simpler's model_brief handling (the model rephrases
  its last answer), not the template, so "say it more simply" still works; its template
  reply key is removed.

## D32: Embedding overlap review and the three-contender bake-off
- Context: the D30 review found overlapping intents by reading. The embedding review
  (docs/superpowers/specs/2026-10-06-embedding-review-design.md) measures it, and a bake-off tests
  whether embedding classifiers can match the fine-tuned encoder.
- Decision: the default embedding model is intfloat/multilingual-e5-small; no new dependency
  (transformers, torch and numpy from the learning group). `mia skills overlap` is a ranked review
  aid, not a gate: owner-judged precision 6/10 at the top 10, recall@40/80/120 = 0.39/0.46/0.57
  against 46 reference pairs (docs/research/overlap-calibration-2026-10-06.md). The trained
  classifier's confusion list is the authoritative overlap signal. `mia skills bakeoff <role>`
  trains the encoder, nearest-examples and contrastive contenders; the winner is the gate passer
  with the best macro F1, then coverage, and the encoder only for roles with slots. Nothing is
  promoted by the bake-off; Gate 2 and `promote` stay with the developer.
- Consequences: the skill and guidelines carry the "same action?" test; the reviewer lists suspect
  labels and paraphrases and never relabels; nothing is merged automatically.

## D33: Authentication built as designed
- Context: ADR 011 and D17 fixed the design; the build is plan 2026-10-12-authentication.md.
- Decision: data standard 1.3 is in effect (auth_credentials, auth_devices, auth_sessions,
  auth_clients; channel_link_codes and channel_link_attempts renamed auth_codes and
  auth_attempts). Deviations from the spec text, each for a rule: refresh rotations are events
  (rule 1); failure records commit before the error is raised (lockouts must accumulate);
  limits also apply per subject whatever the IP; a reset revokes the old credentials, not only
  the sessions; the token endpoint needs no form dependency. `MIA_AUTH_MODE=dev` is for
  development only. Passkeys (`webauthn`) and SMS still need approval before they are built.
- Consequences: `mia auth bootstrap` is the first login on a server; the `mia_login_code`
  WhatsApp template must be approved before staff can sign in by phone; the master key file is
  part of the install and of the recovery copy.

## D34: Scheduling core built on the assumptions Q19 to Q22
- Context: plan item 4 (Sprint 2); docs/superpowers/specs/2026-10-12-scheduling-core-design.md.
- Decision: visits are generated 28 days ahead from the job recurrence (DAILY, WEEKLY with
  BYDAY, INTERVAL, UNTIL; no dependency), one per (job, date); a new visit copies the last
  same-weekday assignment when eligible (no job field, Q21); the office assigns under the
  dispatcher's eligibility rules, and a rule-breaking assignment is an approval
  `schedule.assignment_override` for admin or owner, app only (Q22); check-in opens two hours
  before the planned start and closes four hours after the planned end; the inbox lists the
  approvals the person's roles (with inheritance) may decide. The schedule board is the apps
  project's (Q19). Timesheets wait for Q20 because they change the data standard.
- Consequences: `mia schedule generate` and the daily ticker keep visits ahead; supervisors get
  `data:core.visit write`, staff `write_own` for their own check-in and check-out. Skills are a
  hard rule in the office assignment path (an override approval) but stay a ranking factor in
  the dispatcher's cover flow, where the supervisor's instruction is the approval (D1). Check-in
  and check-out are per visit, as the visit status is; per-person times belong to timesheets
  (Q20), so on a two-person visit the second cleaner cannot check in once the first has.

## D35: customer_service talks to the public outside the people table (Q67)
- Context: every inbound channel message had to come from a linked Person; customer_service
  serves customers on Messenger, Viber and WhatsApp who are not staff. The owner approved the
  Q67 design on 19 October 2026.
- Decision: a customer is not a Person. An agent-owned table customer_service_customers keyed
  by the channel address (platform and id) holds the name the customer gives, the language and
  the branch whose public number was messaged (one public number per branch). The agent acts
  as its own actor on behalf of the address and may call only customer_service.* tools: reads of
  the menu, prices, hours, delivery areas and the customer's own order status (risk none), and
  place_order (money), which drafts an order in customer_service_orders and asks the branch's
  clerk or supervisor to confirm through approvals. No staff tool ever runs for a customer, no
  linking to a Person from the customer flow, every customer message is data (rule 8), the
  auth.py address limits apply, deposits are out of v1.
- Consequences: a new inbound branch for public numbers in channels/inbound.py with its own
  tests (negative tests: a customer cannot reach a staff agent or tool); customer orders stay
  agent-owned until the production_planner or the sales_supervisor reads them, then promotion
  with an ADR (the Q39 precedent). Sell-out answers ("may bibingka pa ba") wait for data
  standard 1.5, since they would make customer_service a second reader of
  inventory_manager_stock_events.

## D36: Data standard 1.5, the sales and stock tables are shared (Q39, Q53; ADR 017)
- Context: the branch_manager, the bookkeeper and customer_service will read the sales counts,
  targets and notes and the stock events, which were agent-owned (rule 9). The owner decided on
  19 October 2026.
- Decision: `sales_supervisor_counts`, `sales_supervisor_targets`, `sales_supervisor_notes` and
  `inventory_manager_stock_events` become the core tables `sales_counts`, `sales_targets`,
  `sales_notes` and `stock_events` in mia/core/models.py (data standard 1.5), with the same
  fields, indexes and foreign keys. `inventory_manager_orders` stays agent-owned (one reader so
  far); the HR tables (Q59) are not part of this promotion.
- Consequences: `0000_initial` is edited in place (no candidate release yet, rule 14) and dev
  databases are rebuilt; the rbac data resources take the table names with no role gaining a
  right (the admin wildcards on the old prefixes became explicit grants); old event rows keep
  the old entity types (rule 2). The branch_manager and the bookkeeper may now be built, and
  customer_service may read `stock_events` for sell-out answers (D35).

## D37: Dated prices per branch, and the owner decides their own money request (Q73, Q77)
- Context: the branch manager's price and promo experiments need a price history, and the
  approvals core never lets a requester decide their own request, which blocks a one-owner
  shop when the owner types a price change. Asked on 20 October 2026; the owner answered both.
- Decision: the retail template gains `retail_item_prices` (a dated price per branch and item;
  `retail_items.price` stays the default) and `retail_items.components` (a bundle's item ids);
  sales counts are priced at the price in force on their business date. The owner's own typed
  money request is the decision: an approval row is still created, and the requester may decide
  it only when they hold the owner role in that branch and complete the PIN step-up; every
  other requester still waits for another approver. Price experiments are proposed only from a
  curated catalogue of proven pricing strategies (data rows with sources, like the tips), each
  proposal naming its strategy, its rationale and its guard rails; the model never invents a
  price or a strategy.
- Consequences: a template migration (0000_initial edited in place), one new rule in
  core/approvals.decide with negative tests (a supervisor still cannot self-approve; an owner
  of another branch cannot), the strategy catalogue as `branch_manager_strategies` rows seeded
  with sources, and a cost floor per item (`retail_items.cost`, nullable) so no strategy prices
  below cost. Recorded in the branch manager spec (section 13) and plan.
- Note (20 Oct 2026, the branch manager's fix wave): the rule is a money rule. It reaches only
  requests with a money, external or delete risk (approvals.request records it in
  `evidence["risk"]`); an owner's own cover override, leave or other request still waits for
  another approver. `mia decide` passes no step-up for the requester's own request, so from the
  shell an owner's own request is refused (the shell was trusted for it before this branch; it
  still decides other people's requests, ADR 011).

## D38: The bookkeeper, data standard 1.6, no utang, VAT (Q84 to Q87)
- Context: the bookkeeper matches settlements and payouts to sales, needs supplier spend and
  payroll for profit, and the catalogue lists utang. Asked on 20 October 2026; the owner
  answered all four.
- Decision: data standard 1.6: `sales_counts` gains `tender` (cash, gcash, maya, grab,
  foodpanda; default cash, the clerk says it when it is not cash); `inventory_manager_orders`
  moves to core as `supplier_orders`; the HR officer's `hr_officer_contracts`, `_payslips` and
  `_leave` move to core as `contracts`, `payslips`, `leave` with their redactions and own-row
  rules kept, the bookkeeper reading payslip totals per branch and month only (owner and admin,
  never a supervisor, never per person). No utang in v1 (neither staff advances nor suki credit;
  Q57 stays closed for now). Ferino's tax regime is VAT at 12 percent, computed in code from
  the sales journal and receipts with a VAT amount; the dated table keeps the 3 percent
  percentage tax for other shops.
- Consequences: one migration edit (0000_initial), ADR 018, the rights-equality test extended
  to the promoted tables, the sales supervisor's count parser reads a tender word, the inventory
  and HR agents' imports move; the bookkeeper spec (docs/superpowers/specs/2026-10-20-bookkeeper-design.md)
  and plan follow.
