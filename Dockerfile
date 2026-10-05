# Mia Node image: Python 3.12, uv, non-root. Built from the repository root:
#   docker build -t mia-node:local .
# deploy/docker-compose.yml runs it; deploy/install.md explains the install.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
# Litestream ships in the node image so backup, restore and the restore test use one version
# and run as the same non-root user (deploy/docker-compose.yml runs it as a sidecar).
COPY --from=litestream/litestream:0.5.17 /usr/local/bin/litestream /usr/local/bin/litestream

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYDANTIC_AI_NO_BANNER=1 \
    MIA_DB_PATH=/data/mia.db

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

# The package is installed editable on purpose: settings.NODE_DIR finds config/ and migrations/
# next to the package, so they stay at /app/node.
COPY node ./node
RUN uv sync --locked --no-dev \
    && useradd --system --uid 10001 --home-dir /app mia \
    && mkdir -p /data /backups \
    && chown mia:mia /data /backups

USER mia
VOLUME ["/data", "/backups"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import json, urllib.request as u; r = json.load(u.urlopen('http://127.0.0.1:8000/health', timeout=4)); raise SystemExit(r['status'] != 'ok')"]

# Migrations run before the server on every start (a database at head is left as it is).
CMD ["sh", "-c", "mia migrate && exec mia serve --host 0.0.0.0 --port 8000"]
