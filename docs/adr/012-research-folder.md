# 012: docs/research for research notes and evaluation reports

## Status
Accepted.

## Context
docs/layout.md asks for an ADR before a new folder. Two kinds of documents have no place yet:
research notes on outside projects (copilotkit-practices.md, from the AG-UI work) and dated
evaluation reports (model-comparison-2026-10-05.html).

## Decision
- docs/research/ holds research notes and evaluation reports. Reports are dated in the file name
  (`model-comparison-YYYY-MM-DD.html`) and never edited after the fact; a new run gets a new file.
- Decisions that come out of research still go to docs/decisions.md or an ADR; a research note
  never decides anything on its own.

## Consequences
- The history of model evaluations stays in the repository next to the code it measured.
- Reports may quote model output verbatim, including characters the docs style otherwise avoids.
