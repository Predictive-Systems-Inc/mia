# Teach Mia: unrecognised messages become phrases, design

22 October 2026. The owner, testing on the phones page: "when command is not recognize, we should
trigger a smart agent to create and clarify the command which will be added into our database for
future use. how can we implement this while keeping version control", then, after the design
below was given in chat: "okay with that... but when in dev mode (in /sim), we want to add new
commands as we go".

## 1. Two gaps, two paths

- **A phrase gap**: Mia can already do it, the words are new ("sales today?", "anong code ng
  ube"). Learned as data, no code change, after a person approves it.
- **A capability gap**: Mia cannot do it ("send me list of item codes" before 22 Oct). A tool
  carries permissions, risk and approvals (rule 3), so it is never created at runtime. It is
  recorded as a backlog item with the message and a note, and built by a developer through the
  normal agent build.

## 2. What a phrase is

A phrase maps a message key (route_memory.key_of: casefolded, numbers as #) to an agent and one
of its actions, at one branch or at every branch. Only actions whose risk is read or whose write
already asks before writing can be taught (the turn still runs the agent's own decider and
guards; a phrase only decides which agent and which action Jev is told the message is about).
Money, external and delete actions are never teachable.

Storage is event-sourced like the learned routes (route_memory reads `chat.route_chosen`):
`phrase.taught` and `phrase.retired` events on the hash chain, no new table, so no data standard
change. The phrasebook is the fold of those events; its version is the count of them; every
`decision.made` records the version it used.

## 3. How a phrase is used

1. Routing: an exact key match routes to the phrase's agent before any Jev request, the same
   place `_recalled` routes a learned tap today, also when another agent is active (a taught
   phrase is a stronger signal than a tap: a person said what it means).
2. Deciding: the agent's Jev request adds up to three taught examples per action to that
   action's option text (data, rule 8: the examples are quoted message text, never
   instructions; they are pseudonymised like the message).
3. Evals: `mia phrases export` writes each phrase as a short-half row of the agent's CSV
   (node/tests/evals/cases/<agent>.csv, intent = the action) for a pull request; CI then holds
   the phrase to the short-half rules (no wrong write).

## 4. Dev mode on the phones page: teach as you go

On /sim (dev and loopback only), when Mia answers with a rephrase, a "Did you mean" or a reply the
tester did not want, the phone shows a **Teach** chip under that reply:

- It opens a picker of the phone owner's agents and their teachable actions (labels from the
  existing intent i18n keys), plus **Mia can't do this yet**.
- Picking an action writes `phrase.taught` at once (dev mode: the tester is the approver; actor
  the person on that phone, on behalf of the tester) and resends the message, so the tester sees
  the taught answer immediately.
- **Mia can't do this yet** asks for a one-line note and writes `capability.requested` (the
  message, the person's role, the note); `mia phrases export` also writes these to
  docs/backlog/capabilities.csv for the developer.
- A **Phrases** drawer in the top bar lists taught phrases with Retire, and shows the phrasebook
  version.

No model is called on the teach path: the tester picks. Nothing here runs in required mode.

## 5. Production: the nightly proposal (phase 2)

When a rephrase or a "Something else" tap happens, Mia writes `intent.unrecognised`. Once a night
a smart model reviews them through egress (rule 6) and proposes "phrase for action X" or
"capability gap"; the owner or an admin approves each on an app card; an approval writes
`phrase.taught`. Two owner decisions are open before phase 2 (Q129): who approves (owner only,
or admins too), and which model reviews (a new external service, pseudonymised staff messages
leave the node).

## 6. Version control

- Runtime: events, append-only, each with actor and time; version = event count; rollback =
  `phrase.retired` (nothing is deleted); decisions record the version.
- Git: `mia phrases export` writes the CSV rows and the backlog file; a pull request carries them;
  CI runs the rows; merging is the release of those phrases as test data. A phrase that causes a
  wrong write fails CI and is retired.
- A fresh database starts with no phrases; `mia phrases import` replays the exported rows as
  `phrase.taught` events by the system actor, so a test database can be rebuilt with them.

## 7. Tests

A taught phrase routes the next identical message (numbers aside) to its agent without a Jev route
request, also with another agent active; a retired phrase stops routing; a money or delete action
is refused as a teach target; the teach route is 404 outside dev mode and off loopback; the
export writes valid CSV rows and import replays them; the decision event carries the phrasebook
version; Rosa's "sales today?" taught to sales_today then answers at once.

## 8. Not in phase 1

The nightly model review and the approval card (phase 2, after Q129); teaching slot values (a
phrase names an action, the agent's parser still reads the details); per-person phrases.
