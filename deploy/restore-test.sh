#!/bin/sh
# Restore test (deploy/install.md, section 6): restore the latest Litestream backup to a temporary
# file inside the node container, verify it with `mia verify-db`, then delete the copy.
# Exit code 0 means the backup restores and its events hash chain is intact.
# Extra arguments go to `litestream restore`, e.g. -timestamp 2026-10-01T06:00:00Z.
set -eu
cd "$(dirname "$0")"
docker compose exec -T node sh -c '
  out=$(mktemp -d)/restore-test.db
  trap "rm -rf $(dirname "$out")" EXIT
  litestream restore -config /etc/litestream.yml -o "$out" "$@" /data/mia.db
  mia verify-db "$out"
' restore-test "$@"
