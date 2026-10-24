from mia.agents.registry import AGENTS, DEFAULT
from mia.agents.shift_supervisor import MANIFEST


def test_the_shift_supervisor_is_registered_under_its_manifest_id() -> None:
    spec = AGENTS[DEFAULT]
    assert spec.id == MANIFEST.id == DEFAULT
    assert spec.label_key == f"agent.{MANIFEST.id}.label"
    assert spec.run_due is not None and spec.stream_agent is not None


def test_every_spec_is_keyed_by_its_own_id() -> None:
    assert all(key == spec.id for key, spec in AGENTS.items())
