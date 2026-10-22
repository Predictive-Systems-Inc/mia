# Testing the Ferino's node

A local test of the Mia Node with the Ferino's configuration (node/config/org/ferinos: retail,
eight agents, Filipino, Cebuano and English, the simulated channel on and WhatsApp off). Nothing
leaves the laptop except the Jev decider (TypeSafe) and the model, both through core/egress.py.

## The local test in five commands

Run from the repository root. `MIA_TYPESAFE_KEY` comes from `.env` (never paste it into a
command). `MIA_PUBLIC_URL` is set to localhost because dev mode refuses to start with a public
URL, and `.env` may hold a tunnel URL.

```
export MIA_ORG=ferinos MIA_DB_PATH=data/ferinos-test.db MIA_AUTH_MODE=dev MIA_DECIDER=jev MIA_PUBLIC_URL=http://localhost:8000
rm -f data/ferinos-test.db && uv run mia migrate && uv run mia seed      # 1. a fresh database
uv run mia serve                                                          # 2. the node on :8000
open http://localhost:8000/                                               # 3. the web chat
uv run mia channels sim "magkano ang bibingka?" --from 639171234567       # 4. a phone on the sim channel
uv run mia tick                                                           # 5. one round of due work
```

3. The chat page has an actor picker in dev mode: pick the person, then type. From a script, send
   `POST /chat` with `{"text": "..."}` and the header `X-Mia-Actor: <person id>` (ids from
   `GET /persons`). Dev mode honours the header from loopback only (ADR 011).
4. A number nobody linked is a customer: the customer service agent answers it. A linked number
   (see below) chats as that person.
5. `serve` already runs the same due work every `MIA_TICK_SECONDS` (30 by default); `tick` runs one
   round on demand. Notifications land in each person's chat (`GET /notifications`).

## The eight personas

Each person sees only the agents their role may use; Rosa (owner) sees all eight. When the
router is unsure it asks "Tungkol ba ito sa:" with at most six agent buttons; tap one, or say it
more plainly. Rows marked "asks first" got that question in the 21 Oct 2026 smoke test (Jev
router confidence 0.3 to 0.5); the others went straight to the agent named.

| Person | Role | Try | Expect |
|---|---|---|---|
| Rosa | owner | `ano ang benta ngayon` | sales supervisor: today's sales per kiosk |
| | | `pakisend ang summary ngayong linggo` | branch manager: last week per kiosk, best and slowest item, waste |
| | | `payslip ni Ana` | HR officer: the payslip, or "no record yet" before a payroll run |
| Marites | supervisor, Mall kiosk | `sira ang kalan` | shift supervisor: incident logged, Rosa told |
| | | `ilang ube ang natitira sa Mall kiosk?` | inventory manager: the count left |
| | | `ano ang orders ngayon` | customer service: today's customer orders |
| Jun | supervisor, Street stall (Cebuano) | `cash count 12450` | bookkeeper: the count against cash sales, Rosa told when over |
| | | `5 ube na lang` | inventory manager: count recorded (asks first) |
| | | `ubos na ang ube` | inventory manager: sold out recorded (asks first) |
| Nonoy | supervisor, Commissary | `ipadala ang production plan para bukas` | production planner: tomorrow's draft plan per item and kiosk |
| | | `kaya ba ng oven ang 150 special bukas?` | production planner: yes or no with the oven minutes left |
| | | `batch 2 classic 45 ok 3 sunog` | production planner: batch recorded (asks first) |
| Ana | clerk, Mall kiosk | `sick ako bukas` | shift supervisor: absence logged, asks all day or morning only |
| | | `nandito na ako` | shift supervisor: checked in |
| | | `ano ang shift ko bukas?` | shift supervisor: her shifts |
| Liza | clerk, Mall kiosk | `pwede ba akong mag-leave sa Biyernes?` | HR officer: leave request sent for approval |
| | | `ano ang orders ngayon` | customer service: today's orders |
| | | `15 classic pa` | inventory manager: count recorded (asks first) |
| Pao | clerk, Street stall (Cebuano) | `masakit akong tiyan, dili ko makaadto ugma` | shift supervisor: absence logged |
| | | `nahutdan na mi og ube` | inventory manager: sold out recorded (asks first) |
| | | `pila among baligya karon?` | sales supervisor: today's sales (asks first) |
| Berto | driver (staff) | `naihatid na sa street stall` | production planner: delivery recorded |
| | | `delivered na sa mall` | production planner: delivery recorded (asks first) |
| | | `ano ang dadalhin ko bukas?` | production planner: the dispatch list (asks first) |

The sim channel runs only in dev mode (loopback); on a server (`MIA_AUTH_MODE=required`) it is
ignored and `mia channels sim` refuses, since its webhook secret is public (ADR 021).

A customer on the sim channel, from any unlinked number:

```
uv run mia channels sim "magkano ang bibingka?" --from 639171234567
uv run mia channels sim "10 classic po, pickup bukas 10am sa Mall kiosk" --from 639171234567
uv run mia channels sim "ready na ba order ko?" --from 639171234567
```

The order waits for the kiosk: Marites, Ana and Liza each get "Bagong order" to confirm or reject.
A pickup outside the kiosk's hours is refused with a request for another time.

## Phones on screen

`http://localhost:8000/sim` shows the sim channel as a row of phones, one per person, so a whole
exchange (a clerk asks, head staff approves, a customer orders) runs on one screen. It answers
only in dev mode from loopback, like the sim channel itself (ADR 021); anywhere else it is 404.

- The top bar has one chip per person, grouped by role (owner, admin, supervisor, clerk, staff).
  Clicking a chip switches that phone on or off; the first time, the person gets a sim number
  (`63900` followed by their position among all people by id, seven digits: `639000000001`,
  `639000000002`, ...; the 0900 prefix is not a real mobile range), linked on the sim channel
  as a dev link (event `channel.linked`). Which phones are on, and each phone's thread, survive
  a reload (browser storage).
- `+ customer` adds an unlinked phone with a name and number you type: the customer service
  agent answers it.
- Mia's buttons and list rows are chips: tapping one sends it as a button tap. Each phone fetches
  what waits for it every 2 seconds (alerts, cards, tick messages). `Tick now` runs one round of
  due work, as `uv run mia tick`.
- After moving the clock forward a day, phones get a "New message from Mia. Reply to see it." notice
  instead of messages (WhatsApp's 24-hour rule, copied by the sim channel); tap Show or send anything.
- `App` on a staff phone opens the person's approval cards (`/notifications`) with Approve and
  Reject, as on the dev chat page.
- Test in English first: the seed sets everyone to Filipino, so click "All phones: English" once
  per fresh database. Every person listed (not only the phones switched on) then gets English
  replies, set as each person's own language choice (event `person.language_chosen`). Each phone's
  status bar has its own en and fil chips (and a list of the other languages). The customer phone
  has no switch: it follows the language the customer writes in.
- Real replies need the Jev decider: start the node with `MIA_DECIDER=jev` as the export line
  above sets, with `MIA_TYPESAFE_KEY` from `.env` (never pasted into a command). With
  `MIA_MODEL=test` and no decider the phones get the customer's "try later" reply and the
  agents' fallback apology instead of real answers.
- A customer's reply that waits for staff (an order confirmed in an App drawer) reaches the
  customer's phone on its next poll; no tick is needed.

Two phones: switch on Ana and Marites. On Ana's phone send `sp 5 cl 8 ube 3` (or `15 classic pa`
for a count); her phone gets the reply. On a receipts kiosk Ana can ask `void resibo 3`: the
request reaches Marites (a notice on her phone, the card in her App drawer); she approves it
there and Ana's phone shows the outcome on its next poll.
For a customer, add `+ customer` (say Lorna, `639171234501`), send `pa-order po 10 classic,
pickup 6pm`; Marites, Ana and Liza get "Bagong order", one of them approves, and the customer's
phone shows the confirmation on its next poll.

## A clerk's day

One normal day at the Mall kiosk, from the first check-in to the closing cash count, in the order
it happens (node/tests/test_day_sales_clerk.py, scenario 1, runs the same day with a pinned clock
on Wednesday 28 Oct 2026: Ana 09:00 to 17:00, Liza 13:00 to 21:00). On the local node send each
message at its time (or as close as the day allows: the business date is the kiosk's local date,
and a count after 21:00 still belongs to the day). When the router asks "Tungkol ba ito sa:",
tap the agent named. The amounts below use today's prices (Special is PHP 49.50 while the seeded
price experiment runs); the cash count is the day's cash sales less 30 pesos.

| Time | Person | Send | Expect |
|---|---|---|---|
| 09:00 | Ana | `nandito na ako` | shift supervisor: checked in at the Mall kiosk at 09:00 |
| 12:00 | Ana | `sp 5 cl 8 ube 3` | sales supervisor: 5 Special, 8 Classic, 3 Ube; today's total against the target |
| 13:00 | Liza | `nandito na ako` | shift supervisor: checked in; no missed check-in notice to Marites at 13:15 |
| 14:00 | customer (sim) | `pa-order po 10 classic, pickup 6pm` | customer service: the order waits; Marites, Ana and Liza get "Bagong order" |
| 14:05 | Marites | approve the order card in her chat | the customer is told the order is confirmed for 18:00 |
| 16:00 | Ana | `ubos na ang ube` | inventory manager: Ube sold out at 16:00 |
| 17:00 | Ana | `sp 4 cl 6` | sales supervisor: recorded as cash (the counts cover the sales before the 16:00 sell-out) |
| 17:01 | Ana | `ube 2 gcash` | sales supervisor: recorded as GCash (one tender per message; two in one message are asked) |
| 17:02 | Ana | `uwi na ako` | shift supervisor: checked out, the timesheet drafted |
| 20:30 | Liza | `sp 3 cl 5` | sales supervisor: recorded, the day's total |
| 21:00 | Liza | `uwi na ako` | shift supervisor: checked out |
| 21:10 | Marites | `bilang ng pera 1459` | bookkeeper: the count against the day's cash sales (total less the GCash), within the 100-peso threshold; Rosa is not told |
| 22:05 | (tick) | `uv run mia tick` | Rosa: the end-of-day sales report against the target; Marites: the closing stock (Ube sold out at 16:00); no missing-count list, no cash count reminder |

The customer line on the sim channel: `uv run mia channels sim "pa-order po 10 classic, pickup
6pm" --from 639171234567`. With those prices the day's sales are PHP 1,579.00, of which PHP 90.00
GCash, so the cash sales are PHP 1,489.00 and `bilang ng pera 1459` is 30 pesos short, within
the threshold; `bilang ng pera 1339` (150 pesos short) tells Rosa the exact amount.

Not built yet, so not in the day: a late notice ("late ako, 1:30 na ako makakarating") reaches
nobody, head staff hears only from the missed check-in notice 15 minutes after the shift starts;
no agent tells head staff of a slow day while the kiosk is open (the owner's report and the
branch manager's evening nudge to the clerks compare with the target); the sales report goes to
the owner, not to head staff.

### Playing the day on the phones page

At any hour, the phones page (/sim) can play the day with its test clock (top bar, "Node time").
Pick a day the seed gave Ana a 09:00 shift (a Wednesday in the scenario). Each row of the table
is a step: type that day and the step's time in the clock's box and press Set
(or use "+15 min", "+1 h" and "Next day 08:00"), then send the message from that person's phone;
on the tick row press "Tick now" instead of running `mia tick`. Setting the clock runs nothing by
itself, only Tick now (or the node's own ticker) runs due work at the new time; the 13:15 missed
check-in notice, for example, needs the clock past 13:15 and a tick. While the clock is shifted
it shows amber with "(test time)"; "Real time" returns to the real clock.

The clock is dev only (MIA_AUTH_MODE=dev, loopback; in required mode the node ignores it) and in
memory: a server restart returns to real time. Start from a fresh test database
(step 1 at the top of this page): moving the clock back interleaves the new events
with later ones, so a replayed day in a used database reads out of order.

## Adding a real person and linking a phone

```
uv run mia person add "Maria Santos" --role clerk --lang fil --branch <branch id>
uv run mia invite "Maria Santos"            # prints a wa.me link and "LINK 123456"
uv run mia channels sim "LINK 123456" --from 639181112222
uv run mia channels sim "sick ako bukas" --from 639181112222
```

Branch ids: `sqlite3 data/ferinos-test.db "select id, name from branch"` (read-only). On WhatsApp
the person sends the same `LINK 123456` text to Mia's number instead.

## Staff phone test on a server

Phones need a server: follow deploy/install.md (Docker, Litestream backups, section 7 for the
Cloudflare Tunnel) and docs/whatsapp-setup.md. The owner provides:

- A host with Docker and Docker Compose (a small VPS or a mini PC at the commissary).
- A Cloudflare account, a tunnel token (`CLOUDFLARE_TUNNEL_TOKEN`) and a hostname on a domain
  they control, set as `MIA_PUBLIC_URL`.
- A Meta WhatsApp Business app: the access token (`MIA_WA_TOKEN`), the app secret
  (`MIA_WA_APP_SECRET`), a verify token they choose (`MIA_WA_VERIFY_TOKEN`), the phone number id
  (`MIA_WA_PHONE_NUMBER_ID`) and the number itself (`MIA_WA_NUMBER`), plus
  `channels.whatsapp.enabled: true` in node/config/org/ferinos/settings.yaml.
- Approved WhatsApp templates in Filipino (`fil`) and Cebuano (`ceb`). Today
  docs/whatsapp-setup.md lists only Finnish (`fi`) and English (`en`) texts for `mia_new_message`
  and `mia_cover_request`, and `mia_login_code` (staff sign-in codes) still needs its text there.
  Until a template is approved, messages Mia starts outside the 24 hour window stay in the app.
- The sim channel is ignored here: it runs only in dev mode (loopback), so phones use WhatsApp.
- `MIA_AUTH_MODE=required` (the node refuses dev mode with a public URL), the master key, and
  `mia auth bootstrap --email <owner email>` with Rosa's authenticator enrolled within 24 hours.
- The model keys: `MIA_TYPESAFE_KEY` with `MIA_DECIDER=jev`, and `MIA_MODEL` with its gateway
  or local model settings (README, "Using a real model").
- Each staff member's phone number, linked with `mia invite` and `LINK`.
