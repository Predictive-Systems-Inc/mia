import importlib.util
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_runtime_dependencies_are_installed_and_training_is_optional() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = " ".join(project["project"]["dependencies"])
    assert "onnxruntime>=1.22" in deps and "tokenizers>=0.22" in deps
    assert "torch" not in deps
    assert any("torch" in d for d in project["dependency-groups"]["learning"])
    assert "transformers>=5,<6" in project["dependency-groups"]["learning"]
    assert importlib.util.find_spec("onnxruntime") is not None
    assert "not learning" in project["tool"]["pytest"]["ini_options"]["addopts"]
