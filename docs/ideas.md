# Ideas (out of scope for the initial build)

- Stream real model tokens in `/chat/stream` (today the reply is computed, then sent as word deltas).
- Port the egress transport to `httpx2` before Pydantic AI v3 removes `httpx.AsyncClient` support.
- Personal data filter in egress for phone numbers, e-mail addresses and IDs, not only names.
- Notify the supervisor proactively when an absence leaves visits uncovered (respecting quiet hours).
- An approvals inbox endpoint (`GET /approvals`) listing what the current person may decide.
- Use `BEGIN IMMEDIATE` for event writes if more than one writer process ever shares a node.
