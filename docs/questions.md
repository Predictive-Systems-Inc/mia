# Questions from the coding agent

All questions below (Q1 to Q7) are answered in docs/decisions.md (D1 to D12).

Format for each entry:

## Q1: short title
- Where: file or spec section
- Question: what is unclear
- Assumed answer: what the code does now
- Blocking: yes or no

## Q1: What `MIA_MODEL=test` runs
- Where: brief, Environment; ADR 004
- Question: the brief says `test` uses Pydantic AI's `TestModel`, and also that the four demo
  conversations must work with `MIA_MODEL=test`. `TestModel` calls tools with generated
  arguments and cannot hold a conversation, so both cannot be true.
- Assumed answer: `test` runs the dispatcher's deterministic rules model (a `FunctionModel`
  driven by the rules classifier from the manifest). `TestModel` is used in unit tests.
- Blocking: no

## Q2: The demo supervisor cannot approve her own request
- Where: brief, demo conversation 3; spec, Approvals ("nobody approves a request they made or triggered")
- Question: in demo 3 the supervisor asks Mia to assign Mikael and then approves. The agent acts
  on her behalf, so she made the request and the spec rule forbids her approval. Which wins?
- Assumed answer: the spec rule. The seed adds an owner (Helena Hyppönen) who approves, so the
  seed has 7 persons instead of 6. Approving as the supervisor shows "nobody approves a request
  they made or triggered". If a supervisor's own chat choice should count as the decision, that
  changes a security rule and needs your decision.
- Blocking: no (the stricter rule is in place)

## Q3: Where Job and Visit live
- Where: brief layout lists Job and Visit in both `core/models.py` and `templates/cleaning/models.py`
- Question: which one owns the tables?
- Assumed answer: core owns location, job and visit (they are in the data standard). The
  cleaning template adds `cleaning_sites`, `cleaning_checklists`, `cleaning_availability` and
  `cleaning_work_limits`.
- Blocking: no

## Q4: Finding the visit for "Who can cover Kalasatama tomorrow at 6:30?"
- Where: brief, tools table (`find_replacements` input: visit id)
- Question: the supervisor names a site and time, not a visit id, and there is no visit search tool.
- Assumed answer: `find_replacements` also accepts `location_name`, `date` and `time` and
  resolves the visit (start within 30 minutes). `get_my_visits` also accepts `person_name` so a
  supervisor can ask about someone else, and a cleaner's attempt is denied and logged (demo 4).
- Blocking: no

## Q5: Evals command path
- Where: brief, commands (`uv run pytest tests/evals -m evals`)
- Question: tests live in `node/tests`, so `tests/evals` does not exist at the repository root.
- Assumed answer: `uv run pytest node/tests/evals -m evals` (or `uv run pytest -m evals`).
- Blocking: no

## Q6: Replacement ranking without travel data
- Where: plan, Replacement scoring ("shortest added travel")
- Question: the seed has no coordinates, so travel cannot be scored.
- Assumed answer: ranking is knows the site, has the skills, fewest hours this week, then name.
  Travel is added when locations have geofence coordinates.
- Blocking: no

## Q7: The existing marketing site in this repository
- Where: repository root (`index.html`, `netlify/`, `netlify.toml`)
- Question: the repository already held a Netlify site ("Mia, your clinic's AI secretary").
  Its `netlify.toml` publishes the whole repository root, so docs and code would be served too.
- Assumed answer: left unchanged. Suggest moving the site to its own repository or setting
  `publish` to a folder that holds only the site.
- Blocking: no

## Q8: Encrypting channel tokens at rest
- Where: spec, Channel rules ("channel tokens encrypted")
- Question: the node has no secret store or field encryption yet.
- Assumed answer: MIA_WA_TOKEN and MIA_WA_APP_SECRET live in `.env` (file permissions, ignored by
  git, excluded by detect-secrets) for Phase 1; they move to encrypted storage with field
  encryption.
- Blocking: no

## Q9: One conversation across app and WhatsApp
- Where: spec, Conversations; ADR 007
- Question: should WhatsApp messages get their own thread?
- Assumed answer: no. A person's latest thread with the agent is shared by the app and every
  channel, so history and approvals stay in one place; the app shows the whole conversation.
- Blocking: no

## Q10: Data standard 1.3 for authentication
- Where: docs/superpowers/specs/2026-10-05-authentication-design.md, section 12; ADR 011
- Question: authentication needs credentials, devices, sessions and clients tables, and one-time
  codes and attempt counts for logins. May the data standard add auth_credentials,
  auth_devices, auth_sessions and auth_clients, and rename channel_link_codes to auth_codes and
  channel_link_attempts to auth_attempts (one table for every one-time code and every attempt)?
- Assumed answer: yes, as proposed in section 12. person gets no new field: phone numbers stay
  in channel_identities and the login email lives on the password credential.
- Blocking: yes (changes the data standard; nothing is built until approved)

## Q11: No email delivery for password resets
- Where: design section 9; spec, Authentication (email plus password)
- Question: email is the office login, but the node has no email service. Should the node send
  reset emails (a new external service), or do resets go through people and channels it has?
- Assumed answer: no email in Phase 1. An admin or owner resets a user and hands over a one-time
  enrolment link (on screen or to the person's linked WhatsApp); a locked-out owner uses
  `mia auth reset` on the node host; MFA users also get ten recovery codes.
- Blocking: no

## Q12: on_behalf_of from outside agents over A2A
- Where: design section 6; ADR 008 (Mia actor extension)
- Question: an outside agent may claim it acts for a person. Is that claim used for RBAC?
- Assumed answer: no. Outside clients act only as themselves with their registered roles; the
  claim is written to the event as claimed_on_behalf_of. Agents on the same node pass the real
  actor in process. Trusted delegation (for example node to node in one organisation) is a
  later decision.
- Blocking: no (changes a security rule only if the answer is yes)

## Q13: One PIN as the step-up for risky approvals
- Where: design section 8; spec, Approvals and Voice rules; plan, Sprint 2
- Question: should office users with TOTP or a passkey use that factor for the step-up instead
  of a PIN?
- Assumed answer: one 6-digit PIN for everyone, re-entered within 5 minutes before deciding a
  money, external or delete approval, on an aal2 session. The same PIN serves voice later.
- Blocking: no

## Q14: Staff login codes through WhatsApp, no SMS provider yet
- Where: design sections 4.4 and 13; spec, Authentication (phone number with one-time code)
- Question: the spec says a one-time code to the phone; it does not say SMS. Can the code go
  through the WhatsApp channel (a Meta authentication template) to the person's linked number?
- Assumed answer: yes. No SMS provider until a pilot user has no WhatsApp; then an SMS channel
  adapter (46elks first for Finland), which is a new external service needing approval.
- Blocking: no

## Q15: Dependencies for authentication
- Where: design section 13
- Question: stdlib scrypt or argon2-cffi for passwords; passkeys now or later?
- Assumed answer: stdlib only for the first build (scrypt, secrets, hmac for TOTP and HKDF, no
  JWT). Passkeys come as a later step with `webauthn` (py_webauthn, BSD-3), after approval.
- Blocking: no for the first build; yes for passkeys

## Q16: Supervisor MFA and session lifetimes
- Where: design sections 4.1 and 5; spec, Authentication (MFA for owner, admin, accountant)
- Question: should supervisors need MFA too, and are the session lifetimes right?
- Assumed answer: MFA offered but not required for supervisors, as the spec says. Access tokens
  15 minutes; office refresh 12 hours idle and 7 days absolute; staff on a bound device 30 days
  idle and 90 days absolute.
- Blocking: no
