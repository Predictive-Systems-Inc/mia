# 006: SQLite write transactions and the event chain

## Status
Accepted.

## Context
The spec asks for WAL mode, a 5 second busy timeout and short transactions. Two problems showed up:
- pysqlite runs a SELECT outside any transaction until the first write. When `events.emit()` was a
  session's first write, two writers could read the same last hash and fork the chain
  (`verify_chain()` returned False with two concurrent writers).
- A chat turn kept one write transaction open for the whole agent run, including model calls.
  SQLite allows one writer, so every other write on the node waited for the model.

## Decision
- `_last_hash()` runs a zero-row `UPDATE events` first. That takes the write lock (waiting up to
  the busy timeout) before the hash is read. Reads elsewhere stay lock free.
- A turn commits in steps: after the user message, after each tool call, and after each egress
  log entry. The reply commits at the end, as before.
- Sync DB work in async code runs in `asyncio.to_thread`, and agent tools are sequential, so one
  Session is never used by two threads at once.

## Consequences
- A turn is no longer one transaction. If the model call fails, the user message, tool events
  and egress log stay committed and the reply is missing. For an audit log this is the wanted
  behaviour: the log of what left the node must survive a failed turn.
- Tests cover both: `test_concurrent_writers_do_not_fork_the_chain` and
  `test_no_write_lock_is_held_during_the_model_call`.
- Upgrade path if write contention grows: a single writer process, as the spec plans for bulk writes.
