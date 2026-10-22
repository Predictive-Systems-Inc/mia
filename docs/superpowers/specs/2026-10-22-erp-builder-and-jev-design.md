# ERP builder agent and JEV decision rules: design

Date: 2026-10-22. Status: draft for review. ADR 008 (proposed). Builds on spec.md, sections
"Tools", "Subagents", "Data standard", "Data and onboarding", "Tests and grading"; decisions D3,
D8, D9 (where data lives) and architecture rules 1, 3, 7, 9 and 14.

## 1. Goal

Mia should cover common business processes (selling, buying, stock, billing, staff) without
hand-writing every table and tool. A large "architect" model with ERP knowledge designs the
tables a business needs and writes the code that maintains them. Cheap agents then run that
code every day.

Three parts:

1. **Architect agent (build time).** Reads a business description and the ERP catalogue,
   proposes tables, writes migrations, service functions, tools and decision rules, with
   tests. A person reviews the result as a pull request before it ships.
2. **JEV decision rules.** Business decisions ("does this purchase need approval, and by whom",
   "is this invoice overdue") are written as JSON documents. A small interpreter in code
   evaluates them. No model runs at decision time.
3. **Small runtime agents.** Agents on the node (rules classifier or a small local model)
   understand the message, then call the generated tools. The tools load facts from the
   database, run JEV rules, and save records and decisions through the service layer.

Success: from a one-page business description, the architect produces a package that passes
lint, types, tests and the architecture checks, and a reviewer can read every table and rule
without reading Python.

### Decisions taken in design
| Topic | Decision |
|---|---|
| When the architect runs | Build time only. Its output is code in a pull request, reviewed, tested and signed. It never runs on a client node and never changes a live schema. |
| JEV | JSON decision rules evaluated by a Mia interpreter in mia/core. Closed operator set, integers only for money, no I/O, no loops. No new dependency. |
| Who supplies facts to a rule | Code. A tool's fact loader reads the database; the model may pass only what the person said (for example an amount). |
| Decision records | Every evaluation is saved as a record plus an event, so a decision can be looked up and replayed exactly. |
| Architect harness | Claude Code (or the Claude Agent SDK) with a Mia `erp-builder` skill, deterministic scaffolding scripts and the repository's own checks. No new runtime component on the node. |

### Out of scope
Generating code on a client node; schema changes from chat; a rule editor UI; a full general
ledger (accounting stays behind connectors, spec "Tools"); Mia Cloud distribution (D13).

## 2. Architecture

```
build time (developer machine or CI, never the node)
  business brief ──► architect agent ──► package (pull request) ──► review + CI ──► signed
                       │ reads
                       ├─ docs/erp/ catalogue (processes, entities, typical decisions)
                       ├─ data standard (core/models.py), CLAUDE.md, ADRs
                       └─ scaffolds (scripts that write the boilerplate deterministically)

run time (Mia Node)
  message ──► small agent (classify, extract) ──► generated tool
                                                   ├─ rbac.require (rule 4)
                                                   ├─ fact loader (code reads tables)
                                                   ├─ rules.decide(rule, facts) ──► decision record + event
                                                   └─ service function (store.insert/update + event)
```

The large model works once per feature, at build time. At run time the model only classifies
and words replies (rule 7). Every calculation and decision is Python or JEV, both covered by
tests.

### What the architect produces (one package)
```
<package>/
  business.yaml        the structured brief the person confirmed (entities, processes, roles, decisions)
  models.py            SQLModel tables, prefixed by owner (cleaning_*, purchasing_*, <agent>_*)
  migrations/          Alembic revision (rule 14)
  services.py          create, update and state transition functions; all writes via core/store.py (rule 1)
  tools.py             typed tools with Pydantic input and output, fact loaders, rbac checks
  manifest.yaml        tool entries with risk, approval, reads and writes (rule 3)
  rules/*.jev.json     decision rules with their test vectors
  prompts/             instructions for the small agent that uses the tools
  tests/               unit tests for services and tools, rule vectors, scenarios.yaml
```

## 3. JEV: JSON decision rules

### Format (jev 1)
```json
{
  "jev": "1",
  "id": "purchasing.request_approval",
  "version": "1.0.0",
  "description": "Who must approve a purchase request.",
  "inputs": {
    "amount":       {"type": "money"},
    "month_spent":  {"type": "money"},
    "month_budget": {"type": "money"},
    "category":     {"type": "enum", "values": ["supplies", "equipment", "services"]}
  },
  "params": {
    "auto_limit": {"type": "money", "default": 10000, "min": 0, "max": 50000, "org_editable": true}
  },
  "outputs": {
    "outcome":  ["auto_approve", "needs_approval"],
    "approver": ["none", "supervisor", "owner"],
    "reason":   ["within_limits", "over_limit", "over_budget", "equipment"]
  },
  "decide": {"first": [
    {"when": {"==": [{"var": "category"}, "equipment"]},
     "then": {"outcome": "needs_approval", "approver": "owner", "reason": "equipment"}},
    {"when": {">": [{"+": [{"var": "month_spent"}, {"var": "amount"}]}, {"var": "month_budget"}]},
     "then": {"outcome": "needs_approval", "approver": "owner", "reason": "over_budget"}},
    {"when": {">": [{"var": "amount"}, {"param": "auto_limit"}]},
     "then": {"outcome": "needs_approval", "approver": "supervisor", "reason": "over_limit"}},
    {"else": {"outcome": "auto_approve", "approver": "none", "reason": "within_limits"}}
  ]},
  "tests": [
    {"given": {"amount": 4000, "month_spent": 0, "month_budget": 50000, "category": "supplies"},
     "expect": {"outcome": "auto_approve", "approver": "none", "reason": "within_limits"}},
    {"given": {"amount": 12000, "month_spent": 0, "month_budget": 50000, "category": "supplies"},
     "expect": {"outcome": "needs_approval", "approver": "supervisor", "reason": "over_limit"}}
  ]
}
```

- **Operators (closed set):** `var`, `param`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `and`, `or`,
  `not`, `in`, `if`, `+`, `-`, `*`, `min`, `max`, `div_round` (integer division with a named
  rounding mode), `days_between` (ISO dates). Nothing else: no loops, regex, string building,
  floats or calls.
- **Two shapes:** `first` (ordered list, first match wins, `else` required) and `table` (a
  decision table rendered from the same structure, for rules with many rows).
- **Types:** `money` is integer minor units; the currency is checked equal across operands
  (rule 10). `date` and `datetime` are ISO 8601 with time zone. `enum` values are listed.

### Interpreter guarantees (mia/core/rules.py)
- **Pure and deterministic:** the same rule version, inputs and params always give the same
  output. No clock, no database, no network inside a rule.
- **Total:** inputs and params are validated against the declared types before evaluation;
  a missing or mistyped input is an error, never a silent null.
- **Bounded:** at most 500 nodes and depth 32 per rule, checked at load.
- **Checked at load:** unknown operators, outputs outside the declared lists, a `first`
  without `else`, unreachable branches and failing test vectors all refuse to load the rule.
- **Cannot loosen platform rules:** a JEV outcome can add an approval but never remove one.
  A tool with risk money, external or delete still requests approval whatever the rule says
  (rule 3, spec "Approvals").

### Decision records
Each `rules.decide(...)` call stores one row and emits `rule.decided`:

| Field | Meaning |
|---|---|
| id, branch_id, decided_at | ULID, branch, ISO 8601 with time zone |
| rule_id, rule_version, rule_hash | Exactly which rule ran (hash of the file) |
| subject_type, subject_id | The record the decision is about |
| inputs, params, output | The facts used and the result |
| actor, tool_call_id | Who asked, for whom, through which tool (rule 5) |

This gives deterministic retrieval ("why was this request sent to the owner?" reads the row,
not a model) and replay (the QA agent re-runs a stored decision and checks the output still
matches). The table is a data standard change and needs the product owner's approval (Q11).

### Organisation parameters
Only parameters marked `org_editable` can change per organisation, within `min` and `max`, in
`node/config/org/<org>/rules.yaml`. Editing them is a privileged, logged action followed by the
rule's test vectors, the same as organisation instructions (spec "Instructions").

## 4. The architect agent

### Pipeline
1. **Brief.** The architect interviews the person (or reads a written description) and writes
   `business.yaml`: processes, entities, states, roles, documents, volumes, country, and every
   decision in plain words with two or three examples. The person confirms it. The examples
   become JEV test vectors.
2. **Map.** Each entity is matched to the catalogue and the data standard and placed in one
   layer (D8): existing core table (reuse), core gap (proposal, needs an ADR and owner
   approval), standard module (industry-neutral ERP area such as purchasing or inventory, see
   Q12), industry template, or agent table. The mapping report is part of the pull request.
3. **Scaffold.** Deterministic scripts write the boilerplate from `business.yaml`: model
   classes with `Stamped`/`BranchScoped`, ULID ids, money pairs, `TZDateTime`, the Alembic
   revision, service function stubs that call `store.insert`/`store.update`, tool stubs with
   `rbac.require`, manifest entries. The model never hand-writes this part, so it is always
   in house style.
4. **Fill.** The model writes what needs judgement: state transition rules, fact loaders,
   JEV rules, prompts for the small agent, scenarios, i18n keys.
5. **Verify.** `ruff`, `mypy`, `pytest`, tests/test_architecture.py, JEV load checks and
   vectors, migration upgrade and downgrade on a copy, and a conformance check for the data
   standard (prefixes, ULIDs, money, time zones, no direct table writes). The architect fixes
   failures until everything passes.
6. **Review.** A pull request with the mapping report and each JEV rule rendered as a readable
   decision table. A person approves; CI runs; the package is signed (spec "Agent package").

### Patterns the generated code follows
- **Records with a lifecycle are state machines.** Each status field lists its states and
  allowed transitions in code (draft, submitted, approved, ordered, received, closed). Each
  transition is one service function that checks the transition, runs any JEV rule, writes
  through the store and emits an event.
- **Quantities and money that change over time are ledgers.** Stock and balances are derived
  from append-only movement rows (stock movements, payment allocations), never edited totals.
  This matches the events table and makes retrieval and audit deterministic.
- **Facts come from code.** A tool's model-facing input holds only what the person said;
  everything else a rule needs is loaded by the fact loader under the agent's permissions.

### ERP catalogue (docs/erp/)
One Markdown file per process, written and reviewed by people, read by the architect:
order to cash (quote, sales order, delivery, invoice, payment), procure to pay (supplier,
purchase request, purchase order, goods receipt, supplier invoice), inventory (item, stock
location, stock movement), service operations (already core: job, visit), staff (already
core: person, availability, work limits), billing export (accounting stays behind
connectors). Each file lists entities, fields, states, typical decisions and country notes
(Finland and the Philippines first).

### Improving the architect
The architect gets better from evidence, not from editing itself at run time:
- An eval set of business briefs with reviewed reference packages (node/tests/evals style).
- Review findings are stored as short lessons in the skill (situation, lesson, evidence), in
  the style of Harness², and changed only through reviewed commits.
- Prompt tuning, if needed, runs offline against the eval set (GEPA style).

## 5. Runtime flow (example: purchase request)

1. Staff writes "Need 6 boxes of microfibre cloths for Kamppi, about 140 euros".
2. The small agent classifies `purchase_request` and extracts item, quantity, site and amount.
3. It calls `purchasing.create_request` (risk write_internal). The tool checks permissions,
   loads `month_spent` and `month_budget` for the site, and calls
   `rules.decide("purchasing.request_approval", ...)`.
4. The decision is saved. The outcome `needs_approval / supervisor / over_limit` creates an
   approval record (spec "Approvals"); `auto_approve` moves the request to `approved`.
5. The agent words the reply from the tool result and the decision's `reason` (i18n keys).
6. Later, "why did this need approval?" is answered from the decision record, not regenerated.

Model tokens are spent only on steps 2 and 5. Sending the purchase order to a supplier is a
separate external tool and always needs approval.

## 6. Security and rule compliance

| Rule | How the design keeps it |
|---|---|
| 1 writes through services | Scaffolded services only use `store.insert` and `store.update`; the architecture test covers generated code. |
| 3 registered tools, approvals | Generated tools are manifest entries; risk money, external and delete keep `approval: always`; JEV cannot remove an approval. |
| 4 permission checks | Scaffolded tools call `rbac.require` first; a negative test per tool is generated. |
| 6 egress | The architect runs at build time and is not part of the node. It sees business descriptions and synthetic data only, never client records (Q13). |
| 7 code calculates | Decisions are JEV or Python; the model classifies and words replies. |
| 8 untrusted content | Briefs and catalogue text are data to the architect; generated prompts keep the `<user_message>` boundaries. |
| 9, 10 data standard | Mapping step plus conformance check; core changes need an ADR and owner approval. |
| 14 migrations | Every schema change is an Alembic revision, tested up and down. |

## 7. Assumptions to record in docs/questions.md
Q10 (JEV format and interpreter), Q11 (decision records in core), Q12 (standard modules for
industry-neutral ERP areas), Q13 (architect data access), Q14 (organisation rule parameters).

## 8. Error handling
- A rule that fails to load stops the package from installing; the node never runs a partly
  valid rule set.
- A rule input that is missing at run time returns a tool refusal (`status: invalid`) with an
  i18n reason; the agent asks the person or tells the supervisor. No default is guessed.
- Replay mismatches found by the QA agent are reported as findings, never auto-corrected.

## 9. Testing
- Interpreter: unit tests per operator, type errors, bounds, currency mismatch, `else`
  requirement, determinism (same input, same output, same hash).
- Every rule: its own vectors at load and in CI.
- Generated packages: unit tests per service and tool with mocked dependencies, negative
  permission tests, scenarios with the rules model (`MIA_MODEL=test`).
- Architect: eval set of briefs, scored on passing checks first, then reviewer rubric.

## 10. First slice
1. `mia/core/rules.py` interpreter with tests and the decision record (after Q11 is answered).
2. `docs/erp/procure-to-pay.md` catalogue entry.
3. Scaffold script for one entity with a state machine.
4. A hand-checked purchasing package for Hype Siivous (supply requests), produced by the
   architect, to measure how much review it needs.
