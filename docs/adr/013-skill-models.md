# 013: Role skill models

## Status
Accepted (decision D29).

## Context
docs/superpowers/specs/2026-10-06-skill-models-design.md: every agent role gets a multilingual
intent classifier built by the /mia-train-role Claude Code skill and the `mia skills` commands.

## Decision
- New packages node/mia/learning (offline pipeline) and node/mia/skills (node runtime), and
  node/mia/agents/<role>/skill/ for each role's plan and data.
- onnxruntime and tokenizers are node dependencies; training libraries are the optional
  `learning` group, installed only where training runs (development machines, cloud jobs, and
  nodes whose owner chose local retraining under D27).
- Built packages and harvested candidates live under MIA_MODELS_DIR and MIA_LEARNING_DIR on the
  node, never in git.
- The node never downloads models: HF_HUB_OFFLINE is 1 in the Docker image and defaults to 1 in `mia serve` and nothing under
  node/mia/skills imports huggingface_hub (tests/test_architecture.py).
- torch installs CPU wheels on Linux through a pinned uv index; macOS uses the PyPI wheels.

## Consequences
- Installing tokenizers pulls huggingface-hub (with hf-xet, fsspec, tqdm, typer, rich) into the node install, and onnxruntime adds numpy and protobuf; the architecture test and HF_HUB_OFFLINE keep the node from fetching.
- A role without a promoted package behaves as before (null classifier).
- High-band tool intents run the agent with the intent as context in this version; direct slot
  to tool argument mapping is a later improvement (spec section 7 updated).
