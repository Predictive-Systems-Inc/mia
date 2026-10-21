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

A customer on the sim channel, from any unlinked number:

```
uv run mia channels sim "magkano ang bibingka?" --from 639171234567
uv run mia channels sim "10 classic po, pickup bukas 10am sa Mall kiosk" --from 639171234567
uv run mia channels sim "ready na ba order ko?" --from 639171234567
```

The order waits for the kiosk: Marites, Ana and Liza each get "Bagong order" to confirm or reject.
A pickup outside the kiosk's hours is refused with a request for another time.

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
- `MIA_AUTH_MODE=required` (the node refuses dev mode with a public URL), the master key, and
  `mia auth bootstrap --email <owner email>` with Rosa's authenticator enrolled within 24 hours.
- The model keys: `MIA_TYPESAFE_KEY` with `MIA_DECIDER=jev`, and `MIA_MODEL` with its gateway
  or local model settings (README, "Using a real model").
- Each staff member's phone number, linked with `mia invite` and `LINK`.
