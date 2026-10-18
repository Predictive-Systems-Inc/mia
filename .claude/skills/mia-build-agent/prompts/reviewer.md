# Extra review questions per task kind

Append the block for the task's kind to the task review and all blocks to the whole-branch
review. Also run the whole of `checklist.md`.

## data
- Is there a schema test, and does the migration downgrade drop tables in dependency order?
- Are all foreign keys declared, and is `branch_id` nullable only where a person has none?
- Are the tables agent-owned (prefixed) unless a second reader is already named in the spec?
- Ids ULIDs, money integer minor units plus currency, times with zones?

## actions
- Is any message text copied into instructions rather than state?
- Units (pieces, minor units) and orientation (item then number, number then item) both handled?
- Does the decider only pick from the agent's own ACTIONS?

## tools
- Is `_check` called before every read and every write, and is there a negative test for each?
- Is branch scoping through `read_all` and `write_all` (not a bare branch id from the message)?
- One event per row written; a supersede bound by date, never another person's row?

## turn
- Is the write committed before the Jev await?
- Are taps validated against the agent's own ACTIONS, and stale taps refused?
- Exactly one reply per turn? Is an instruction hidden in a message treated as data (injection test)?

## due
- Do windows work across midnight, with the business date from the closing's day?
- Is the marker written in the same transaction as the send, per branch and date?
- Urgent flags right (end-of-shift urgent, reminders and morning not), and nothing sent when empty?
- Per-branch commits, so one branch failing does not lose another's sends?

## i18n
- Is every key in all ten languages through the coverage test, with identical placeholders?
- Filipino named fil, never Tagalog; no digits in the strings?
- Do tests assert through `t(...)` and not literals?

## evals
- Is the gate half fresh, split by seed, with no text in both halves?
- Is `PENDING` emptied and the raw file named by local time, never overwritten?
- Do the report's numbers recompute from the raw file, and is a failing gate stated as it is?
