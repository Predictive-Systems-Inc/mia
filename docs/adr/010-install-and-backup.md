# 010: Docker Compose install and Litestream backup

## Status
Accepted for the local node. Covers the plan's Sprint 0 compose item and the Sprint 5 install,
backup, restore test and update items.

## Context
The plan and spec call for a Docker Compose install, Litestream backup, a restore test and an
update procedure. docs/plan.md already reserves a deploy/ folder; docs/layout.md does not list it.
The spec also names a Huey worker; the node runs its periodic work in-process instead
(MIA_TICK_SECONDS in api/main.py), which is enough for one branch.

## Decision
- New folder deploy/: docker-compose.yml, litestream.yml, install.md and restore-test.sh.
  Dockerfile and .dockerignore sit at the repository root because the build context is the
  whole repository.
- One image (python:3.12-slim, uv, user `mia`, uid 10001). The node container runs
  `mia migrate && mia serve`, so migrations always run before the server. The image's
  HEALTHCHECK calls /health; Litestream starts only once the node is healthy.
- Litestream (0.5.17, a pinned binary copied into the image) runs as a sidecar container from
  the same image, so backup, restore and the restore test use one version and one non-root user.
  The target is one URL from the environment: a file volume for testing or an S3-compatible
  bucket.
- No Huey and no separate worker container. If bulk jobs (imports, exports, pay runs) need one,
  that is a separate proposal.
- Two CLI commands: `mia backup DEST` (SQLite online backup, used before updates for rollback)
  and `mia verify-db PATH` (read-only: integrity check, events hash chain, migration revision,
  row counts). Neither writes to the live database.
- The node port binds to 127.0.0.1. A Cloudflare Tunnel container (compose profile `tunnel`)
  publishes only the webhook path until real login lands.

## Consequences
- Backups are a deliberate exception to rule 6 (nothing leaves the node except through egress.py
  and channels/transport.py): the operator chooses and configures the target, and the full
  database leaves the node, real names included, without pseudonymisation. install.md requires a
  private, encrypted-at-rest bucket with a key limited to it, in a region matching the client's
  agreement. Litestream does not encrypt client-side in this setup.
- Litestream adds two bookkeeping tables (`_litestream_seq`, `_litestream_lock`) to the live
  database. They are not in the data standard or the migrations; `mia verify-db` lists them.
- The restore test result is printed, not yet logged as an event (the spec asks for an event).
- The spec's signed images, automatic rollback on a failed health check, and "last backup" on
  the health page are not built; rollback is the manual procedure in install.md.
- CI builds the image and runs the compose smoke test and restore test in a separate job;
  `uv run pytest` checks the deploy files statically and never needs Docker.
