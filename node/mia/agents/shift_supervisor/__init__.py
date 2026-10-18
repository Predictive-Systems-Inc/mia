"""The shift supervisor agent (rosters, absences, cover, check-in)."""

from pathlib import Path

from mia.agents.base import Manifest

AGENT_DIR = Path(__file__).resolve().parent
MANIFEST = Manifest.load(AGENT_DIR / "manifest.yaml")
