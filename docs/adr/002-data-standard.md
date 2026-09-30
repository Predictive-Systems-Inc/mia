# 002: Data standard v1.0 field list

## Status
Accepted for the initial build. Changes need the product owner (CLAUDE.md: ask before changing
the data standard).

## Context
The spec lists entities and required fields. The build needs exact tables.

## Decision
Every table has `id` (ULID), `branch_id`, `created_at`, `updated_at`, except `organisation`
(no branch) and `events` (only `timestamp`). Code lives in `mia/core/models.py`.

| Table | Fields beyond the common ones |
| --- | --- |
| organisation | name, country (ISO 3166 alpha-2), default_language |
| branch | organisation_id, name, timezone (IANA) |
| person | name, status, roles (list), skills (list), engagement_type, language (BCP 47) |
| client | name, type (business, residential), status |
| location | client_id, name, address, geofence (JSON), instructions (Markdown), access_notes |
| job | location_id, name, recurrence (RRULE), start_time (local HH:MM), duration_minutes, required_skills, resources |
| visit | job_id, location_id, date, assigned_person_ids, planned_start, planned_end, actual_start, actual_end, status, proof_refs |
| approval | type, requester_type, requester_id, requester_on_behalf_of, subject_type, subject_id, summary, evidence, approver_roles, channel, expires_at, escalate_to, status, decided_by, decided_at, reason |
| chat_threads | person_id, agent_id, title |
| chat_messages | thread_id, role, sender_id, text, blocks, agent_id, model_messages |
| events | timestamp, branch_id, actor_type, actor_id, on_behalf_of, action, entity_type, entity_id, before, after, tool_call_id, approval_id, prev_hash, hash |
| usage_cloud_requests | organisation_id, agent_id, subagent_id, task, model, provider, input_tokens, output_tokens, cost_minor, currency, timestamp, result |
| egress_log | timestamp, agent_id, purpose, level, provider, tokens, payload_hash |

Additions to the spec's list, each needed by the build: `location.name`, `job.name`,
`job.start_time`, `visit.location_id` (denormalised for site queries), `chat_messages.model_messages`
(conversation history for the agent), and the approval requester split into three columns.

Industry tables live in the cleaning template (`cleaning_sites`, `cleaning_checklists`,
`cleaning_availability`, `cleaning_work_limits`). Agent tables carry the agent prefix
(`dispatcher_absences`).

Code lists in this version: person status (active, inactive), engagement_type (employee,
contractor, agency), client type (business, residential), visit status (planned, in_progress,
completed, cancelled, unfilled), approval status (pending, approved, rejected, expired,
escalated), approval channel (app_only, any).

## Consequences
- Encrypted fields (contact details, access notes) are plain text in this build; field-level
  encryption with the node master key is a later task and will need a migration.
- `events` is append-only: ORM guard plus SQLite triggers. Retention is not implemented yet.
