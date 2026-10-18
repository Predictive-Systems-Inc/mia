"""The sales supervisor agent (daily sales counts, targets and the day's story)."""

from pathlib import Path

from mia.agents.base import Manifest

AGENT_DIR = Path(__file__).resolve().parent
MANIFEST = Manifest.load(AGENT_DIR / "manifest.yaml")
