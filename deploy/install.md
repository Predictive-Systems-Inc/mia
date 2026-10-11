# Installing a Mia Node

One Mia Node runs on one small server at a client branch (a mini PC on site or a rented server).
This guide takes a new server to a running, backed-up node in under two hours. Commands run from
the `deploy/` folder of the repository unless stated otherwise.

| Step | Time |
| --- | --- |
| 1. Server and Docker | 20 min |
| 2. Get the code | 5 min |
| 3. Settings (`deploy/.env`) | 15 min |
| 4. Build, start and check | 20 min |
| 5. Backups | 20 min |
| 6. Restore test | 10 min |
| 7. WhatsApp through Cloudflare Tunnel (optional) | 30 min |

What runs (deploy/docker-compose.yml):

- `node`: the Mia Node (FastAPI and the chat page on port 8000). Each start runs `mia migrate`
  first, then the server. The periodic work (cover confirmations, channel outbox) runs inside
  the node every `MIA_TICK_SECONDS`; there is no separate worker.
- `litestream`: continuous backup of the SQLite database to the target you choose. It starts
  once the node is healthy.
- `tunnel` (optional, profile `tunnel`): Cloudflare Tunnel for WhatsApp webhooks.

Data lives in the Docker volume `mia_mia-data` (`/data/mia.db` inside the containers).

## 1. Server and Docker

- Linux x86-64, 4 cores, 16 GB RAM, 100 GB SSD (spec, node install baseline). Outbound HTTPS.
  No inbound ports are needed: the node listens on 127.0.0.1 only and outside traffic arrives
  through the tunnel.
- Install Docker Engine with the Compose plugin: https://docs.docker.com/engine/install/
- Check: `docker compose version` prints v2 or later.
- Keep the operating system updated and the disk encrypted where the hardware allows it; the
  server holds the client's business data.

## 2. Get the code

```
git clone <repository url> mia
cd mia/deploy
```

## 3. Settings

```
cp ../.env.example .env
chmod 600 .env
```

Edit `deploy/.env`. Secrets live only in this file (or the environment), never in the repository;
`.env` is in `.gitignore`. Set at least:

- `MIA_ORG`: the organisation folder under `node/config/org/` (mounted read-only into the node,
  so its instructions and settings can be edited on the server; restart the node after a change).
- `MIA_NODE_SECRET`: `python3 -c "import secrets; print(secrets.token_hex(32))"`. Set it once and
  keep it (changing it invalidates open invites).
- `MIA_MODEL`, `MIA_GATEWAY_URL`, `MIA_GATEWAY_KEY`, `MIA_EGRESS_LEVEL`: see the README, "Using a
  real model". `MIA_MODEL=test` runs without any model.
- `MIA_GEOCODER`, `MIA_GEOCODER_KEY`: `static` needs no key.
- The backup target (section 5) and, for WhatsApp, the `MIA_WA_*` values and
  `CLOUDFLARE_TUNNEL_TOKEN` (section 7).

`MIA_DB_PATH` is fixed to `/data/mia.db` by the compose file; the value in `.env` is ignored.

## 4. Build, start and check

```
docker compose build          # mia-node:local from the repository (Dockerfile at the root)
docker compose up -d --wait
curl http://127.0.0.1:8000/health
```

`/health` must show `"status":"ok"` and `"events_chain":true`. Docker uses the same endpoint
for the container health check (`docker compose ps` shows `healthy`).

Add the first people, or load the demo data on a test install:

```
docker compose exec node mia person add "Sanna Virtanen" --role supervisor --lang fi
docker compose exec node mia seed          # demo data only, never on a client's node
```

Logs: `docker compose logs -f node litestream`.

## 5. Backups

Litestream copies every change of `/data/mia.db` to the target within about a second. Choose the
target in `deploy/.env`:

```
# Testing only: a Docker volume on the same disk (does not survive a lost server).
LITESTREAM_REPLICA_URL=file:///backups/mia

# Real use: an S3-compatible bucket (AWS S3, Backblaze B2, Hetzner, UpCloud, MinIO ...).
LITESTREAM_REPLICA_URL=s3://<bucket>/<branch>/mia
LITESTREAM_S3_ENDPOINT=https://<provider endpoint>     # empty for AWS
LITESTREAM_ACCESS_KEY_ID=<key>
LITESTREAM_SECRET_ACCESS_KEY=<secret>
```

Then `docker compose up -d` and check `docker compose logs litestream` for `snapshot complete`.

The backup is a full copy of the client's business data: names, phone numbers, messages,
schedules and the events log. It is the one place data leaves the node besides the model and
channel exits, and only to the target the operator configures here (ADR 010). For the bucket:

- A private bucket used only for this node, with public access blocked.
- Encryption at rest switched on (server-side encryption; most providers have it on by default,
  check it). Litestream does not add its own encryption in this setup.
- An access key limited to this bucket (read and write on the branch prefix, nothing else).
- A region that matches the client's data processing agreement (EU for Finnish clients).
- Bucket versioning or object lock if the provider has it, so a stolen key cannot erase history.
- Store the access key in the client's password manager as well: a restore on a new server needs it.

## 6. Restore test

Run at install and every quarter (spec, keys and backup):

```
./restore-test.sh
```

It restores the latest backup to a temporary file inside the node container, runs
`mia verify-db` on it (SQLite integrity, the events hash chain, migration revision, row counts)
and deletes the copy. Exit code 0 and `OK: restore verified` mean the backup is usable. A point in
time: `./restore-test.sh -timestamp 2026-10-01T06:00:00Z`. Write the date and result in the
client's operations log.

## Restore after a lost or broken server

1. Install sections 1 to 3 on the new server with the same `deploy/.env` (backup target and keys).
2. Restore before the node starts for the first time:
   ```
   docker compose run --rm --no-deps node litestream restore -config /etc/litestream.yml /data/mia.db
   docker compose run --rm --no-deps node mia verify-db /data/mia.db
   docker compose up -d --wait
   ```
   On the same server with a damaged database, stop first and move the old files aside (step 2
   refuses to overwrite an existing database):
   ```
   docker compose stop
   docker compose run --rm --no-deps node sh -c 'mkdir -p /data/broken && mv /data/mia.db* /data/broken/'
   ```
3. Check `/health` and that the last changes people remember are there.

## Updates

```
docker tag mia-node:local mia-node:previous                       # keep the running image
docker compose exec node mia backup /data/pre-update-$(date +%Y%m%d%H%M).db
git pull
docker compose build
docker compose up -d --wait                                       # migrations run on start
curl http://127.0.0.1:8000/health
./restore-test.sh
```

`mia backup` writes a consistent copy while the node runs; keep it until the update has run for
a week, then delete it (`docker compose exec node rm /data/pre-update-<date>.db`).

Rollback (the new version fails its health check or misbehaves). A newer migration may have
changed the database, so return to the copy taken before the update:

```
docker compose stop
docker compose run --rm --no-deps node sh -c 'mkdir -p /data/failed && mv /data/mia.db* /data/failed/ && cp /data/pre-update-<date>.db /data/mia.db'
MIA_IMAGE=mia-node:previous docker compose up -d --wait
```

Changes made between the update and the rollback stay in `/data/failed/` and are not in the
restored database; tell the supervisor which period to check. Litestream continues from the
restored database. Pin `MIA_IMAGE=mia-node:previous` in `.env` until the fix is released.

## 7. WhatsApp through Cloudflare Tunnel

WhatsApp webhooks need a public HTTPS address. Follow docs/whatsapp-setup.md for the Meta side;
for the tunnel, run it as a container next to the node:

1. In the Cloudflare dashboard (Zero Trust, Networks, Tunnels) create a tunnel and copy its token
   to `CLOUDFLARE_TUNNEL_TOKEN` in `deploy/.env`.
2. Add a public hostname for the tunnel with service `http://node:8000` and path
   `channels/.*`. Until real login lands, publish only the webhook path, never the whole node.
3. Set `MIA_PUBLIC_URL=https://<that hostname>` in `deploy/.env`.
4. `docker compose --profile tunnel up -d --wait`
5. Set the callback URL in Meta to `https://<hostname>/channels/whatsapp/webhook`.
