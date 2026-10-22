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
of its actions, at one branch or at every branch. A key needs a letter: a bare number ("#") is
never a phrase. Money, external and delete actions are never teachable; every other action with
a tool and a button label may be a phrase's target, for routing. A phrase picks the action for
the decider only when that action's tool reads: a write always keeps its question (Did you
mean, or the agent's own guard). The turn still runs the agent's own decider, guards and tool
rbac.

Storage is event-sourced like the learned routes (route_memory reads `chat.route_chosen`):
`phrase.taught`, `phrase.confirmed` and `phrase.retired` events on the hash chain, no new
table, so no data standard change. The phrasebook is the fold of the events that apply to a
branch; its version is the count of them at that branch; every `decision.made` records the
version it used.

## 3. How a phrase is used

1. Routing: an exact key match routes to the phrase's agent before any Jev request, the same
   place `_recalled` routes a learned tap. A taught phrase routes also when another agent is
   active (a person said what it means); a tapped phrase routes only when no agent is active,
   as `_recalled` does.
2. Deciding: the agent's Jev request adds up to three examples per action to that action's
   option text, only from phrases taught on the Teach path by an owner or admin, each at most
   60 characters (data, rule 8: quoted message text, never instructions, pseudonymised like
   the message). A tapped phrase is never an example. When Jev still asks only from its own
   doubt (its pick is clarify or below the threshold), a phrase whose action reads takes that
   action if it is one of Jev's alternatives with no missing input. A decision an agent's
   guard made (`Decision.guarded`: the bookkeeper's cash count or expense question, an order
   with no buy word, a closure, an action outside the side's options, a receipts kiosk's
   confirm) is never overridden.
3. Evals: `mia phrases export` writes each taught phrase as a short-half row of the agent's
   CSV (node/tests/evals/cases/<agent>.csv, intent = the action, extra `"taught": true`) for a
   pull request. The sets' loader leaves taught rows out of their own counts; one shared test
   holds every taught row to the no-wrong-write rule. `mia phrases import --branch` replays
   them at one branch (`--every-branch` for all).

### Learning from Did you mean taps

The owner, 22 Oct: "when I click total benta, it prompted Did you mean, sales today. When I
choose that, system must add confidence level to recognize in the future". A tap on an action
of an agent's "Did you mean" writes `phrase.confirmed` (the asked message's key, the agent, the
action, the person, the branch); Something else writes nothing, and nor does a key with no
letter. Per key, the confidence is the taps for the leading (agent, action) minus the taps for
any other; a key at 1 or more whose latest tap agrees is a learned phrase. It routes when no
agent is active and, for a read, is the hint to the decider; it never becomes an example. The
Phrases drawer shows its confidence and taps. A taught phrase counts as confirmed at once and
outranks taps. Only teachable actions are learned: a tap on a money, external or delete action
runs that turn and is never learned.

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

## 4b. Request a feature (every user, every mode)

The owner, 22 Oct: "add a button for users to request to support certain action. this is a
global database of feature request".

- Every person can ask for something Mia cannot do: a **Request a feature** button in the app's
  menu and on each phone of the phones page, and in chat the reply to a capability gap offers it
  as a button ("Ask for this feature"). Staff on WhatsApp can also type "request: <what>".
- The request holds: what the person wants in their own words (data, rule 8), the message that
  failed if there was one, the person's role, branch and language, and the time. It is written as
  `feature.requested` on the node's hash chain (no new table, no data standard change) and the
  person is told it was sent.
- The same request from several people is grouped by code (the key of the text, as phrases);
  each person's request still counts.
- **Global**: the node's requests go to one shared list across every Mia node, where the
  developer sees them and marks them planned, built or declined; the node shows each request's
  status back to whoever asked. Where that list lives is the owner's decision (Q130): it is a new
  external service, and the request text leaves the node (pseudonymised: names and numbers
  masked as for Jev). The owner's answer (22 Oct, Q130): keep it on the node for now. Each node
  keeps its own list, `mia requests export` writes it for the developer, nothing leaves the node,
  and the developer marks a request's status with `mia requests status <id> planned|built|declined`
  so the asker sees it. A shared place is chosen later (for example when Mia Cloud exists).

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
