# 003: How tools declare risk and approval

## Status
Accepted for the initial build.

## Context
Architecture rules 3 and 4: agents act only through registered tools, every tool call is
permission checked, and risky tools must request approval and stop.

## Decision
- The manifest lists every tool with `id`, `kind`, `risk` (read, write_internal, external,
  money, delete), `approval` (never, first_time, always, or a limit) and optional `reads` and
  `writes`. Manifest validation refuses a risky tool with `approval: never` and any tool needing
  approval without `roles.approvers`.
- `agents/base.py` builds the agent from the manifest. Implementations are bound by tool id; the
  build fails if the bound set and the manifest set differ (no tool, no action).
- Every call goes through one guard, in this order:
  1. `rbac.require(actor, tool:<id>, action)` for the agent principal and the person it acts for
     (`action` is `request` when `approval: always`, else `execute`);
  2. for risk money, external or delete: create an approval (`app_only`) and raise
     `ApprovalRequired` unless an approved approval for that tool is supplied;
  3. run the tool; data access inside the tool is checked again with ownership (`read_own`).
  The call, its inputs and its result (or refusal) are written to the events log.
- The model sees refusals as a result (`status: denied | approval_required | invalid`), never an
  exception, so it can answer politely.
- `approval: always` on a `write_internal` tool (the dispatcher's `propose_assignment`) means the
  tool's own job is to create the approval; the change itself is applied by a registered handler
  (`apply_assignment`) only after a person approves.
- No-self-approval is checked on the requester principal, its on_behalf_of person and the
  approval's `evidence.triggered_by` (for example the cleaner whose absence caused the change).
  Agents never decide approvals, and `tool:*:approve` is denied for agent roles.

## Consequences
- `first_time` and amount limits (`above: ...`) are parsed but treated like `always` for risky
  tools; the dispatcher has no such tools yet.
