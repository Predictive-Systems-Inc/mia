# Field Work over Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cleaners check in, check out and get visit details through chat; the tools route to the scheduling core.

**Architecture:** Three `ToolBinding`s in `agents/dispatcher/tools.py` on top of `core/scheduling.py`; three intents in the rules classifier, `rules.decide` and `rules.compose`; strings in `i18n/strings.py`; grants in `manifest.yaml`.

**Tech Stack:** as the dispatcher today. No dependency.

**Spec:** docs/superpowers/specs/2026-10-12-field-work-chat-design.md

## Global Constraints
- CLAUDE.md rules 3, 4, 7, 8: registered tools with manifest entries, `rbac.require` before each, decisions in code, message text is data.
- Visit choice: today's visits of the acting person; check-in needs `planned` and the window from `scheduling` (2 h before the start to 4 h after the end); check-out needs `in_progress`.
- Reply text through i18n keys (fi and en).

## Review Focus
1. "Olen perillä" at 12:00 with a 09:00 to 10:00 visit must check in (window to 14:00); at 15:00 it must say too late. Pinned in Task 1 (`test_check_in_picks_the_visit_in_window`).
2. A supervisor saying "I'm here" with no visit of their own must get "no visit now", never someone else's visit. Pinned in Task 1 (`test_check_in_only_own_visits`).
3. A door-code question over WhatsApp must not leak the access notes in plain text. Pinned in Task 2 (`test_details_are_sensitive_on_channels`).

### Task 1: Tools, classifier, rules, strings, manifest
**Files:** modify `node/mia/agents/dispatcher/tools.py`, `classifier.py`, `rules.py`, `manifest.yaml`, `node/mia/i18n/strings.py`; tests `node/tests/test_tools.py`, `node/tests/test_classifier.py`, `node/tests/test_chat.py`.
- [ ] Tests first (below), run RED, implement, run GREEN, full check line, commit.

### Task 2: Sensitive details on channels, eval scenarios, docs
**Files:** `node/mia/chat/blocks.py` or `chat/service.py` (mark the details reply sensitive), `node/mia/agents/dispatcher/tests/scenarios.yaml`, `docs/capabilities.md` (Built column), `docs/plan.md`.
- [ ] Tests first, implement, full check line, commit.
