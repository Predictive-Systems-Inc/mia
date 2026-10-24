# ADR 024: Data standard 1.10, kiosk assignments

## Status

Accepted (24 Oct 2026, the owner, D50).

## Context

A person has one home branch (`person.branch_id`), and every branch scope check compares a
record's branch with it. The owner said supervisors are assigned to several kiosks and see
everything of all of them. Clerks keep one kiosk; the owner and admins already read every kiosk
through read_all.

## Decision

- Data standard 1.10, in mia/core/models.py: `BranchAssignment` (`branch_assignments`), branch
  scoped on the assigned kiosk, with `person_id`, `from_date` and an optional `to_date` (the
  first day the assignment no longer holds). At most one open assignment (no `to_date`) per
  person and branch (a partial unique index). `STANDARD_VERSION = "1.10"`; every agent manifest
  declares 1.10.
- Services in mia/core/assignments.py, each write through store with an event: `assign`
  (`assignment.created`) and `unassign` (`assignment.ended`). Only the owner or an admin
  (write_all on `data:branch_assignments`). `assign` refuses a person without the supervisor
  role (`not_supervisor`), a branch of another organisation, a branch that is no kiosk
  (`not_a_kiosk`: the commissary sells nothing), the person's home branch and a duplicate open
  assignment; `unassign` refuses without an open one. Deactivating a person or taking away
  their supervisor role (`people.set_roles`) ends their open assignments through `unassign`,
  so none comes back on reactivation.
- One branch scope: `branches_of(session, person, day)` is the home branch plus the branches of
  the assignments active on that day (only while the person is an active supervisor);
  `actor_branches` applies it to an actor. The sales supervisor's, the bookkeeper's balances and
  the inventory manager's branch checks (AgentDeps.kiosks: a clerk on a cover keeps one kiosk), `sales.receipts`,
  `approvals.decide`, the approvals inbox, the void card's recipients and
  `alerts.supervisors` (alerts and morning messages; the owners' fallback for a branch without
  a supervisor of its own stays) use it. A read of an assigned kiosk needs no
  read_all; "all" in a report or `today` is the supervisor's own kiosks. Writes, pay and the
  books (the sales journal, tax, profit) keep today's rights.
- The branch manager's `assign_kiosk` tool and chat action (risk write_internal, approval
  never; owner and admin by policy): "assign Jun to the Mall kiosk", "alisin si Jun sa Mall
  kiosk".

## Consequences

- No existing table changes. `0000_initial` is edited in place (no candidate release yet,
  rule 14) and dev databases are rebuilt: `rm data/*.db && uv run mia migrate && uv run mia
  seed`.
- Rights: owner and admin read, write, read_all and write_all on `data:branch_assignments`; the
  branch manager agent read, write and write_all; the shared-rights table in test_rbac and the
  rule 9 guard pin them.
- Ferino's seed assigns Marites to the Street stall and Jun to the Mall kiosk, so each kiosk's
  alerts and approval cards reach both supervisors.
- An assigned supervisor's morning message from each kiosk does not yet name the kiosk.
