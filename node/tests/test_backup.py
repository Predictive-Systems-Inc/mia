"""`mia backup` and `mia verify-db` (the restore check), plus static checks of deploy/ that run
without Docker."""

import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import yaml

from mia.cli import main
from mia.settings import NODE_DIR, get_settings

REPO = NODE_DIR.parent


@pytest.fixture
def seeded() -> Path:
    assert main(["migrate"]) == 0
    assert main(["seed"]) == 0
    assert main(["chat", "Olen kipeä huomenna.", "--as", "Juha"]) == 0  # adds events
    return get_settings().MIA_DB_PATH


def test_backup_then_verify(
    seeded: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copy = tmp_path / "restore" / "mia.db"
    assert main(["backup", str(copy)]) == 0
    before = copy.read_bytes()
    capsys.readouterr()

    assert main(["verify-db", str(copy)]) == 0
    out = capsys.readouterr().out
    assert "integrity: ok" in out
    assert "events chain: intact" in out
    assert re.search(r"events: [1-9]\d*", out)
    assert re.search(r"migration: \w+", out)
    assert "OK: restore verified" in out
    assert copy.read_bytes() == before  # verification never changes the copy


def test_backup_refuses_to_overwrite(seeded: Path, tmp_path: Path) -> None:
    dest = tmp_path / "exists.db"
    dest.write_bytes(b"keep me")
    with pytest.raises(SystemExit, match="exists"):
        main(["backup", str(dest)])
    assert dest.read_bytes() == b"keep me"


def test_backup_without_database(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no database"):
        main(["backup", str(tmp_path / "out.db")])


def test_verify_detects_a_tampered_chain(
    seeded: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Tamper with a throwaway copy only (the triggers protect the real one).
    copy = tmp_path / "tampered.db"
    assert main(["backup", str(copy)]) == 0
    with closing(sqlite3.connect(copy)) as conn:
        conn.execute("DROP TRIGGER events_no_update")
        conn.execute("UPDATE events SET action = 'tampered' WHERE rowid = 1")
        conn.commit()
    capsys.readouterr()
    assert main(["verify-db", str(copy)]) == 1
    out = capsys.readouterr().out
    assert "events chain: BROKEN" in out and "FAILED" in out


def test_verify_missing_or_garbage_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["verify-db", str(tmp_path / "nope.db")]) == 1
    assert not (tmp_path / "nope.db").exists()
    garbage = tmp_path / "garbage.db"
    garbage.write_bytes(b"not a database" * 100)
    assert main(["verify-db", str(garbage)]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_verify_empty_database_has_no_chain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty.db"
    with closing(sqlite3.connect(empty)) as conn:
        conn.execute("CREATE TABLE t (x)")
    assert main(["verify-db", str(empty)]) == 1
    assert "BROKEN or missing" in capsys.readouterr().out


# Static checks of the deploy files (CI runs the Docker build and smoke test separately).


def _compose() -> dict:
    return yaml.safe_load((REPO / "deploy" / "docker-compose.yml").read_text())


def test_dockerfile_runs_migrations_first_as_non_root_with_health() -> None:
    text = (REPO / "Dockerfile").read_text()
    assert "FROM python:3.12" in text
    assert re.search(r"^USER mia$", text, re.MULTILINE)
    assert re.search(r"^HEALTHCHECK .*\n.*/health", text, re.MULTILINE)
    cmd = re.search(r"^CMD (.+)$", text, re.MULTILINE)
    assert cmd and cmd[1].index("mia migrate &&") < cmd[1].index("mia serve")


def test_compose_wires_node_and_litestream() -> None:
    services = _compose()["services"]
    node, litestream = services["node"], services["litestream"]
    assert node["environment"]["MIA_DB_PATH"] == "/data/mia.db"
    assert all(p.startswith("127.0.0.1:") for p in node["ports"])  # no login yet: local only
    assert litestream["depends_on"]["node"]["condition"] == "service_healthy"
    shared = {v.split(":")[0] for v in node["volumes"]} & {
        v.split(":")[0] for v in litestream["volumes"]
    }
    assert "mia-data" in shared
    config = yaml.safe_load((REPO / "deploy" / "litestream.yml").read_text())
    assert [db["path"] for db in config["dbs"]] == ["/data/mia.db"]
    assert services["tunnel"]["profiles"] == ["tunnel"]


def test_deploy_variables_are_documented_and_no_secrets_committed() -> None:
    deploy = REPO / "deploy"
    used = set()
    for name in ("docker-compose.yml", "litestream.yml"):
        used |= set(re.findall(r"\$\{(\w+)", (deploy / name).read_text()))
    documented = set(re.findall(r"^#?\s*(\w+)=", (REPO / ".env.example").read_text(), re.MULTILINE))
    assert used <= documented, used - documented
    for line in (REPO / ".env.example").read_text().splitlines():
        if re.match(r"(MIA_\w*(TOKEN|KEY|SECRET)|LITESTREAM_SECRET\w*|CLOUDFLARE\w*)=", line):
            assert line.endswith("="), f"secret with a value in .env.example: {line}"
