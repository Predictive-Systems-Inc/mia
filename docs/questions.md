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

## Q10: JEV rule format and interpreter
- Where: docs/superpowers/specs/2026-10-22-erp-builder-and-jev-design.md, section 3; ADR 008
- Question: "JEV" was described as JSON decision rules. Use an existing format (JSON Logic, CEL)
  or a Mia format?
- Assumed answer: a Mia format close to JSON Logic (first-match lists and decision tables,
  closed operator set, integer money), evaluated by mia/core/rules.py. No new dependency.
- Blocking: no

## Q11: Decision records in the core data standard
- Where: design section 3, "Decision records"
- Question: storing every rule evaluation needs a new core table (data standard 1.3).
- Assumed answer: a `rule_decision` table in core, written through the store with a
  `rule.decided` event. Not built until the product owner approves.
- Blocking: yes, for building the interpreter's storage (not for the design)

## Q12: Where industry-neutral ERP tables live
- Where: design section 4, "Map"; decision D8
- Question: purchasing and inventory are industry-neutral, so D8 points to core, but they are
  large and not every branch needs them.
- Assumed answer: optional standard modules owned by Better Labs (tables prefixed
  `purchasing_*`, `inventory_*`), each versioned with the data standard and installed only when
  a package needs it.
- Blocking: no

## Q13: What the architect agent may see
- Where: design section 6
- Question: the architect uses a cloud model at build time, outside core/egress.py.
- Assumed answer: it runs on a developer machine or in CI, not on a node, and sees only the
  business brief, the catalogue, the code and synthetic data, never client records.
- Blocking: no

## Q14: Organisation rule parameters
- Where: design section 3, "Organisation parameters"
- Question: can organisations change rule thresholds?
- Assumed answer: only parameters marked `org_editable`, within declared min and max, in
  node/config/org/<org>/rules.yaml; editing is privileged, logged and followed by the rule's
  test vectors.
- Blocking: no
