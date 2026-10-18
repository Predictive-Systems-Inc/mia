# Spec template

Write `docs/superpowers/specs/<date>-<agent_id>-design.md`. Follow the section order of
docs/superpowers/specs/2026-10-19-sales-supervisor-design.md. Fill from the catalogue row. No
em-dashes; Filipino never Tagalog.

## 1. Goal
One paragraph: the job in the shop's words, who it is for, the proof shop. Then "Out of scope".

## 2. Data standard check (gate 1, the owner)
First section after the goal. Tables read and written, which other agents read each, which are
core (a second reader makes it core, rule 9). If core changes: the question to the owner and
"stop until a yes". Without a yes: agent-owned tables, and the promotion recorded as blocking
before the next reader (Q39).

## 3. Who talks to it
Roles, languages, channels, and what each role may do (read_own, read_all, write_all).

## 4. Scenarios (the acceptance list)
Five to ten, in priority order, each as a short story with the expected reply and the test name.

## 5. Data
Agent-owned tables, template (industry) fields, core tables touched; ids, money in minor units,
times with zones, the migration note (rule 14).

## 6. The agent
Actions and slots, tools with risk and roles, due work with windows and markers, events.

## 7. Parsing
What code splits and what Jev picks (rule 7); the correction and negation rules.

## 8. i18n
New keys by group, the ten languages, and the label.

## 9. Seed and configuration
Demo data, org settings, policy lines.

## 10. Testing and gates
Unit, chat and due tests, the decider gate at the Q40 bar, the router seeds.

## 11. Open questions
Each into docs/questions.md in its shape (Where, Question, Assumed answer, Blocking).

## 12. Order of work
The tasks of the plan in order.

## Carried over
Follow-ups from the reviews, one bullet each with the place that owns it.
