# Authentication and identity: design

Date: 2026-10-05. Status: draft for review (design only, nothing built). ADR: 011 (proposed).
Builds on spec.md, sections "Roles and permissions", "Authentication", "Approvals", "Channel
rules", "Voice rules", "Keys and backup"; plan.md, "Status and revised order" item 1; ADR 003
(tool risk and approval), ADR 007 (channel adapters), ADR 008 and D14 (A2A needs OAuth2 or mTLS).

Items marked **APPROVAL NEEDED** change the data standard, add a dependency or add an external
service. CLAUDE.md requires Allan's approval before any of them is built.

## 1. Goal

Every request that reaches a Mia Node carries an actor the node has verified, so a pilot with
real people, WhatsApp in production and inbound A2A can run on a node that is reachable from the
internet through a Cloudflare Tunnel.

Success: the X-Mia-Actor header is accepted only in dev mode on loopback; office users log in
with password plus a second factor (or a passkey); staff log in with a code sent to their
linked WhatsApp number and keep a bound device; outside agents get node-issued client
credentials; money, external and delete approvals need a fresh PIN; every login, failure,
lockout, revocation and credential change is an event in the hash chain.

### Decisions taken in design (recommendations; Allan decides the items in 12, 13 and 17)
| Topic | Recommendation |
|---|---|
| Tokens | Opaque random tokens (stdlib `secrets`), stored as SHA-256 hashes. No JWT: the node is the only issuer and the only verifier, and a DB lookup gives instant revocation. |
| Access and refresh | One mechanism for web and mobile: access token 15 minutes, rotating refresh token with reuse detection (spec, Sessions). Browser keeps both in HttpOnly cookies. |
| Office login | Email plus password, then TOTP (authenticator app). Passkeys as a later step (one dependency). |
| Password hashing | Stdlib `hashlib.scrypt` (OWASP parameters). `argon2-cffi` only if Allan prefers Argon2id. |
| TOTP | Stdlib `hmac` (RFC 6238 is about 20 lines). No `pyotp`. |
| Staff login | Phone number, code sent through the WhatsApp channel (Meta authentication template), then the device is bound. The phone number is the person's existing WhatsApp channel identity, so `person` gets no phone field. |
| WhatsApp-linked staff | A one-time login link sent to their linked WhatsApp, for "View in the Mia app" and for the web app on the phone. |
| SMS | Not in the first build. Only needed for staff without WhatsApp; then an SMS channel adapter (spec build order already lists SMS). |
| A2A and services | OAuth2 client credentials issued by the node (opaque bearer tokens, 1 hour). mTLS is not practical behind Cloudflare Tunnel (TLS ends at Cloudflare). |
| Step-up | A 6-digit PIN per person, re-entered within 5 minutes before deciding a money, external or delete approval (spec, Approvals; plan, Sprint 2). |
| Secrets | One master key file (root-only, outside the data folder, a Docker secret), subkeys derived with HKDF-SHA256 built on stdlib `hmac`. |
| Rate limits | In the node database, generalising `channel_link_attempts`. No `slowapi`. |
| Dev mode | `MIA_AUTH_MODE=dev` keeps X-Mia-Actor for local development and existing tests, only from loopback, and the node refuses to start in dev mode with a public URL. |

### Non-goals
- Mia Cloud accounts or single sign-on across branches (D13). Each node authenticates its own
  people; a role in branch A gives no rights in branch B (spec, Domains).
- Email delivery (password reset mails). The node has no email service; resets go through an
  admin, the linked WhatsApp, or the node CLI (see 9).
- Social login, SAML, OIDC provider federation.
- Voice PIN entry (DTMF) and caller verification: voice is deferred (brief non-goal). The PIN
  designed here is the one voice will use.
- Field-level encryption of contact details: separate work (Q8); this design only uses the
  same master key.
- Mobile app screens: the API is designed so the Expo app can use it; screens come with Sprint 3.

## 2. Threat model

The node is a single-branch FastAPI process on a mini PC or rented server. It has no open
inbound port; `cloudflared` opens an outbound tunnel and Cloudflare serves a public hostname
with TLS. Everything on that hostname is reachable by anyone on the internet.

### Assets
Personal data of staff and clients (schedules, addresses, access notes, later pay), the ability
to change schedules and decide approvals, the events log's integrity, channel tokens, the master
key, model gateway keys.

### Trust boundaries
| Boundary | Trusted side | Notes |
|---|---|---|
| Internet to Cloudflare | Cloudflare | Cloudflare terminates TLS and sees plaintext, including passwords and tokens. It is a processor under the DPA, as it already is for WhatsApp webhooks. |
| Cloudflare to node | Node | Reached through `cloudflared`. `CF-Connecting-IP` is trusted only when the TCP peer is the tunnel (`MIA_TRUSTED_PROXIES`). |
| Node to model gateway, Meta, geocoder | Node | Unchanged: egress.py and channels/transport.py (rule 6). |
| Node host (root) | Out of scope | Root on the host has the database and the master key. Physical security and OS updates are install concerns. |

### Threats and mitigations
| Threat | Mitigation |
|---|---|
| Anyone sets X-Mia-Actor and acts as the owner (today's state) | Header accepted only with `MIA_AUTH_MODE=dev` from a loopback peer with no Cloudflare headers; startup refuses dev mode when `MIA_PUBLIC_URL` is not localhost. Architecture test: no route reads the header outside the dev dependency. |
| Credential stuffing, password guessing | MFA required for owner, admin and accountant (spec), offered to supervisors; per-login and per-IP failure limits; scrypt; generic error messages and equal timing for unknown logins. |
| Phishing | TOTP is phishable; passkeys are not, so passkeys are the upgrade (step 11). Approvals of money and external still need the PIN. |
| Stolen access token (logs, proxy) | 15 minute lifetime; tokens never logged; stored only as hashes. |
| Stolen refresh token | Rotation on every use; a reused old refresh token revokes the whole session (reuse detection). |
| Lost or stolen phone | Supervisor or the person revokes the device; sessions on it end at once (server-side lookup). Risky approvals still need the PIN. |
| WhatsApp account takeover or SIM swap | WhatsApp login gives staff-level assurance only (aal1); approvals of money, external and delete need aal2 plus PIN; staff are told to enable WhatsApp two-step verification during onboarding. |
| Forwarded login link or OTP | Single use, 10 minutes, bound to the browser that opened it (it becomes that device); every use is an event and is shown to the person. |
| CSRF on cookie sessions | Cookies `SameSite=Strict`, `HttpOnly`, `Secure`; unsafe methods with cookie auth must carry an `Origin` equal to `MIA_PUBLIC_URL`. Bearer requests are not affected. |
| XSS stealing tokens | Tokens in HttpOnly cookies on the web; the node sends a strict Content-Security-Policy for the office app it serves. |
| Account lockout as denial of service | Lockout is per (login, IP) first; a per-login lock is short (15 minutes) and the owner can always unlock through the CLI. |
| Prompt injection to raise privileges | Unchanged rule 8: the actor comes only from the authenticated request, never from model output or message text; `ChatRequest.actor_id` is removed. |
| Outside agent impersonation over A2A | OAuth2 client credentials issued per client by the owner; X-Mia-Actor never accepted on A2A routes (ADR 008); on_behalf_of claims from outside are recorded but not trusted (see 6). |
| Replay of an A2A token | 1 hour lifetime, revocable, scoped to one client and its roles. |
| Backup theft (Litestream copy) | Database holds only hashes of passwords, tokens, codes and PINs. TOTP seeds are derived from the master key, which is never in the backup. |
| Insider (admin) abuse | Every credential change, reset and revocation is an event with actor; no self-approval (unchanged); admins cannot read secrets, only reset them. |
| Exposed internal endpoints | Cloudflare ingress rules expose only the paths in 11; `/health` on the public hostname shows status only, not version or model. |

## 3. Identities

| Identity | Principal type | How it is verified | Assurance | Notes |
|---|---|---|---|---|
| Office user (owner, admin, accountant, supervisor) | `person` | Email and password plus TOTP, or passkey | aal2 (aal1 for a supervisor without MFA) | MFA mandatory for owner, admin, accountant (spec). |
| Staff (cleaner) on the app | `person` | Code to the linked WhatsApp number, then a bound device | aal1; aal2 with PIN on a bound device | Phone number = active channel identity address (E.164). |
| Staff on WhatsApp only | `person` | The channel identity (linked once with a link code, ADR 007) | channel | Already built. Never decides app_only approvals (approvals.decide). |
| Mia agent on this node | `agent` | In-process; never authenticates over HTTP | n/a | `Actor.person(p).as_agent(role)` as today. Spec: "node-issued credentials, never user accounts" applies when an agent is called over A2A. |
| Outside agent or service (A2A, scripts, other nodes) | `agent` with id `client:<client_id>` | OAuth2 client credentials | client | Roles come from the client registration, checked by rbac like any agent role. |
| System | `system` | n/a | n/a | Ticker, migrations, the CLI's own bookkeeping. |
| Node CLI user | `person` | Shell access to the node host | host | `mia` commands act as a named person; events carry `via: cli`. Shell access is already full access. |

Assurance levels follow NIST SP 800-63B names, used only internally: `channel` (a WhatsApp
identity), `aal1` (one factor), `aal2` (two factors, or a user-verifying passkey, or a bound
device plus PIN), `client` (machine credential). A session records its level.

## 4. Login flows

All flows end in `issue_session(person, device, method, aal)` (section 5). All failures return
the same message and status (401 `invalid credentials`), whatever was wrong.

### 4.1 Office: password then TOTP
1. `POST /auth/login {email, password}`. Rate limits checked first (section 10), then scrypt.
2. If the person needs MFA (role owner, admin or accountant, or the person enrolled TOTP) the
   response is `{mfa_required: true, mfa_token}`; `mfa_token` is a 5 minute single-use auth
   code (section 7, `auth_codes`, purpose `mfa`).
3. `POST /auth/mfa {mfa_token, code}` checks the TOTP (30 second steps, window of one step
   either side, each step usable once: `last_step` on the credential) or a recovery code.
4. A role that requires MFA without an enrolled factor gets only an enrolment session (it can
   reach `/auth/mfa/enrol` and nothing else) until TOTP is confirmed with a first code.
5. Ten single-use recovery codes are shown once at enrolment, stored as hashes.

### 4.2 Office: passkey (step 11, needs approval of `webauthn`)
`POST /auth/passkey/options` then `POST /auth/passkey/verify`. User verification required,
so a passkey alone is aal2. Relying party id is the host of `MIA_PUBLIC_URL`; changing the
hostname invalidates passkeys (install guide warns about this). Passkeys are enrolled from an
existing aal2 session.

### 4.3 First login and invites (office and staff)
- Bootstrap: `mia auth bootstrap --email owner@example.fi` on the node prints a one-time
  enrolment link (24 hours). The owner sets a password and enrols TOTP. No default passwords.
- An admin adding an office user gets the same enrolment link to hand over (shown once on
  screen, or sent to the person's linked WhatsApp). The link sets password and MFA.
- Staff need no enrolment link: the existing WhatsApp invite (link code, ADR 007) is the
  enrolment, because it proves the number belongs to them.

### 4.4 Staff: phone code then device binding
1. `POST /auth/otp/start {phone}`. The node looks up an active `channel_identities` row with
   that address (any channel that can deliver codes; WhatsApp first). Unknown numbers get the
   same response and nothing is sent.
2. A 6-digit code (5 minutes, single use, at most 5 tries, at most 3 sends per number per hour)
   is sent with a Meta authentication template (copy-code button) through `channels.deliver`
   and `channels/transport.py` (rule 6). The code is never in an event or log.
3. `POST /auth/otp/verify {phone, code, device: {name, platform}}` creates an `auth_devices`
   row and returns a device secret (256 bits, shown once, kept in the app's secure storage)
   plus a session.
4. Later logins on that device use `POST /auth/device {device_id, device_secret}` (no code)
   and get aal1. With the PIN (`POST /auth/stepup`) the session is aal2 for 5 minutes.
5. Sign-out revokes the device and its sessions (spec). A supervisor can revoke any device of
   a person in their branch; deactivating a person revokes every device, session and channel
   identity (extends `linking.revoke_all`).

Device binding uses a bearer device secret, not a hardware-held key pair, so it needs no
dependency. Upgrade path: the app generates a P-256 key in the secure enclave and signs a
challenge; that needs `cryptography` (already planned for field encryption).

### 4.5 WhatsApp-linked staff: login link
- A linked person asks Mia for the app ("open the app", or a "View in the Mia app" button on
  a sensitive block) and gets a link `MIA_PUBLIC_URL/auth/link/<code>` on WhatsApp: single use,
  10 minutes, sent only to the active identity of that person.
- Opening it in a browser shows one "Continue as <first name>" button (so link previews and
  scanners that fetch the URL do not consume it); the POST creates a browser device and an
  aal1 session.
- The existing "View in the Mia app" secure links use the same mechanism, so they stop being
  plain URLs to an unauthenticated page.

## 5. Sessions and refresh tokens

| Item | Value |
|---|---|
| Access token | 32 random bytes, base64url, 15 minutes. Sent as `Authorization: Bearer` (mobile, A2A) or the `mia_at` cookie (web). |
| Refresh token | 32 random bytes, rotated on every use. Office: expires after 12 hours idle, 7 days absolute. Staff on a bound device: 30 days idle, 90 days absolute. Cookie `mia_rt` with `Path=/auth/refresh`. |
| Storage | SHA-256 of each token on the `auth_sessions` row; plain tokens never stored or logged. |
| Reuse detection | The row keeps the previous refresh hash; presenting it revokes the session and emits `auth.refresh_reused`. |
| Revocation | Sign-out, device revoke, password change (all other sessions), person deactivated, role change (sessions keep working but roles are read fresh from `person` each request). |
| Writes | Verifying an access token is a read only. `last_seen_at` is written on refresh, not per request (rule 11: short write transactions). |

## 6. Deriving actor and on_behalf_of per request (rules 4 and 5)

One FastAPI dependency replaces `resolve_actor` and `ActorHeader`:

```python
class AuthContext(BaseModel):
    actor: Actor  # principal (+ on_behalf_of), branch_id
    person: Person | None  # the human, reloaded from the database on every request
    method: str  # password_totp, passkey, phone_otp, device, wa_link, client, dev
    aal: str  # channel, aal1, aal2, client
    session_id: str | None
    channel: str  # "app" for app sessions; decides app_only approvals


CurrentAuth = Annotated[AuthContext, Depends(current_auth)]
```

Resolution order in `current_auth`: bearer token, then cookie, then (dev mode only) X-Mia-Actor.
No credential gives 401. The person is loaded fresh: inactive gives 403 and roles always come
from `person.roles`, never from the token.

| Entry point | principal | on_behalf_of |
|---|---|---|
| App request (web, mobile) | the person | none |
| App request that runs an agent (`/chat`, `/ag-ui`) | the agent role (`as_agent`) | the person |
| WhatsApp message (already built in channels/inbound.py) | the agent role | the person from `channel_identities` |
| A2A request from an outside client | `agent` `client:<client_id>` with the client's roles | none. An on_behalf_of claim in the A2A Mia extension is written to the event's data as `claimed_on_behalf_of` but not used for RBAC (Q12). |
| A2A request between Mia agents on this node | in-process call, actor passed through unchanged | the original person |
| Ticker and handlers | `system` | the person who approved, where relevant (as today) |

Every route and tool then calls `rbac.require(auth.actor, resource, action, session=...)` as
today; nothing in RBAC changes. `approvals.decide` takes `channel` from `auth.channel` instead
of a route constant, and for `app_only` approvals also requires `aal2` and a PIN step-up within
the last 5 minutes (section 8). `ChatRequest.actor_id` is removed.

## 7. A2A and service-to-service credentials

- The owner (or admin) registers a client: `mia auth client add NAME --role agent.partner_x`
  or an admin endpoint. The node shows `client_id` and `client_secret` once; the secret is
  stored as a scrypt hash.
- `POST /auth/token` with `grant_type=client_credentials` (RFC 6749 section 4.4, HTTP Basic or
  form credentials) returns an opaque access token for 1 hour. No refresh token.
- The client's roles are agent roles loaded like manifest roles (grants and denies, risky
  permissions one by one). Clients never hold `approve` (spec rule 1 for agents).
- The Agent Card declares an OAuth2 `clientCredentials` security scheme with this token URL
  (ADR 008). A2A routes accept only client tokens; a person cookie or X-Mia-Actor is refused.
- mTLS: not chosen. Cloudflare Tunnel ends TLS at Cloudflare, so the node never sees the
  client certificate; Cloudflare API Shield mTLS could forward a verified header, but that is
  a paid Cloudflare feature and ties identity to Cloudflare. Revisit for node-to-node traffic
  over Tailscale.
- Outbound A2A (Mia calling another agent) stores that agent's client credentials as secrets
  (section 11) and goes through the single A2A exit (ADR 008).
- `private_key_jwt` (signed client assertions instead of a shared secret) is the upgrade when
  a partner requires it; it needs `cryptography`.

## 8. PIN for money, external and delete approvals

- Each person who may approve sets a 6-digit PIN from an aal2 session (office) or a bound
  device after phone code (staff with approver roles). Stored as a scrypt hash on
  `auth_credentials` (kind `pin`). Trivial PINs (all same digit, 123456 style sequences) refused.
- `POST /auth/stepup {pin}` marks the session `stepped_up_at`. Deciding an `app_only` approval
  needs `aal2` and `stepped_up_at` within 5 minutes; otherwise the API answers 403
  `step_up_required` and the app asks for the PIN.
- 5 wrong PINs lock the PIN until the person logs in again with MFA (office) or a phone code
  (staff); every failure and lock is an event.
- Voice uses the same PIN later (DTMF), as the spec says.
- Office users with TOTP or a passkey could use that factor as the step-up instead of the PIN;
  one PIN for everyone is simpler and matches the spec (Q13).

## 9. Account recovery

| Case | Path |
|---|---|
| Office user forgot password or lost authenticator | An admin or owner resets: all sessions revoked, a new enrolment link (24 hours) is shown to the admin or sent to the person's linked WhatsApp. Event `auth.reset` with both actors. |
| Office user, self-service | Recovery code (one of ten) in place of TOTP; password reset still needs an admin because there is no email delivery (Q11). |
| Owner locked out, no other owner or admin | `mia auth reset --person <id>` on the node host prints an enrolment link. Shell access is already full access; the event records `via: cli`. |
| Staff lost phone | Supervisor revokes the device and the WhatsApp identity, then sends a new link code (ADR 007) to the new phone. |
| Staff changed number | Same as lost phone; the old identity is revoked, never overwritten (linking already refuses overwrites). |
| Master key lost | Out of scope here; spec, Keys and backup (recovery copy, optional escrow). Without it, TOTP seeds are lost and every MFA user re-enrols through the reset path. |

## 10. Rate limiting and lockout

Stored in the node database (generalising `channel_link_attempts` into `auth_attempts`, see
12), so limits survive restarts and need no dependency. Counted before any expensive hash.

| Attempt | Limit | Effect |
|---|---|---|
| Password per (login, IP) | 5 failures in 15 minutes | 15 minute block for that pair |
| Password per login | 20 failures in 1 hour | 15 minute block; event `auth.locked`; owner unlocks via CLI |
| Any auth per IP | 50 failures in 15 minutes | 15 minute block for the IP |
| TOTP or recovery code per mfa_token | 5 tries | token void |
| Phone code sends per number | 3 per hour | silently not sent (same response) |
| Phone code tries per code | 5 | code void |
| PIN per person | 5 failures | PIN locked until re-login with MFA or phone code |
| Client secret per client_id | 10 failures in 15 minutes | 15 minute block |
| Link code per address | 5 failures per hour (already built) | unchanged |

IP comes from `CF-Connecting-IP` only when the TCP peer is in `MIA_TRUSTED_PROXIES` (the
cloudflared container), else from the TCP peer. A Cloudflare WAF rate limiting rule on
`/auth/*` is an optional outer layer (the free plan includes one rule).

## 11. Secrets and configuration

| Setting | Meaning |
|---|---|
| `MIA_AUTH_MODE` | `required` (default) or `dev`. |
| `MIA_MASTER_KEY_FILE` | Path to a 32-byte key file, mode 0400, outside the data folder; a Docker secret in Compose. Generated by `mia keys init` at install (spec, Keys and backup). |
| `MIA_NODE_SECRET` | Kept for one release as a fallback for link-code HMACs, then replaced by a subkey. |
| `MIA_TRUSTED_PROXIES` | Peers allowed to set `CF-Connecting-IP`. |
| `MIA_PUBLIC_URL` | Already exists; also the cookie origin, CSRF origin and passkey relying party. |

- Subkeys: HKDF-SHA256 (RFC 5869, a few lines on stdlib `hmac`) from the master key with fixed
  labels: `mia/link-codes`, `mia/auth-codes`, `mia/totp`. TOTP seed for a credential =
  HKDF(totp key, credential id + enrolment nonce), so no seed is stored at all.
- When field encryption lands, the TOTP key becomes a data key wrapped by the master key, so a
  master key rotation does not invalidate authenticators (spec: rotation re-wraps keys).
- The OS keyring (spec option) is not used: in Docker there is no keyring, and a root-only file
  is what the spec allows as the alternative.
- Channel tokens and client secrets for outbound A2A stay in `.env` until field encryption
  (Q8, unchanged).
- Cloudflare ingress allowlist (cloudflared config): `/auth/*`, `/chat*`, `/ag-ui`,
  `/approvals/*`, `/notifications`, `/channels/*/webhook`, `/a2a*`, `/.well-known/*`, the
  office app's static files, `/health` (reduced). Everything else returns 404 at the edge.

## 12. PROPOSED data standard change (1.3) **APPROVAL NEEDED**

This changes the data standard (CLAUDE.md: ask before). Migration 0004, Alembic. All tables
follow ADR 002 (ULID ids, `created_at`, `updated_at`, TZDateTime). Writes go through service
functions in `mia/core/auth.py` using `store.insert` and `store.update`, which emit events
(rule 1). Secrets are never in events: the `before` and `after` of these rows are redacted to
non-secret fields.

### 12.1 New tables
**auth_credentials** (BranchScoped): one login factor of a person.
| Field | Type | Notes |
|---|---|---|
| person_id | str, FK person, index | |
| kind | str | `password`, `totp`, `recovery_code`, `pin`, `passkey` |
| login | str or null, unique when not null | lowercased email, only on `password` rows |
| secret_hash | str or null | scrypt string for password, pin, recovery_code; null for totp and passkey |
| data | JSON | totp: `{nonce, last_step}`; passkey: `{credential_id, public_key, sign_count, transports}` |
| status | str | `pending` (TOTP before first code), `active`, `revoked`, `used` (recovery code), `locked` (pin) |
| last_used_at | datetime or null | |

**auth_devices** (BranchScoped): a browser or phone a person has signed in on.
| Field | Type | Notes |
|---|---|---|
| person_id | str, FK person, index | |
| kind | str | `browser`, `mobile` |
| name | str | for example "iPhone, Mia app"; shown in the device list |
| secret_hash | str or null | SHA-256 of the device secret (mobile binding) |
| status | str | `active`, `revoked` |
| last_seen_at | datetime or null | written on refresh |
| revoked_at, revoked_by | datetime, str, null | |

**auth_sessions** (BranchScoped): one signed-in session, person or client.
| Field | Type | Notes |
|---|---|---|
| subject_type | str | `person` or `client` |
| subject_id | str, index | person id or auth_clients id |
| device_id | str or null, FK auth_devices | |
| method | str | `password_totp`, `passkey`, `phone_otp`, `device`, `wa_link`, `client`, `enrol` |
| aal | str | `aal1`, `aal2`, `client`, `enrol` |
| access_hash | str, unique | |
| access_expires_at | datetime | |
| refresh_hash | str or null, unique | null for clients |
| prev_refresh_hash | str or null | reuse detection |
| refresh_expires_at, absolute_expires_at | datetime or null | |
| stepped_up_at | datetime or null | PIN step-up |
| status | str | `active`, `revoked` |
| ip | str | first IP, for the person's session list |

**auth_clients** (BranchScoped): an outside agent or service (A2A, scripts).
| Field | Type | Notes |
|---|---|---|
| name | str | |
| client_id | str, unique | `mia_` plus random |
| secret_hash | str | scrypt |
| roles | JSON list | agent roles, loaded into rbac like manifest roles |
| status | str | `active`, `revoked` |
| expires_at | datetime or null | |
| created_by | str | person id |
| last_used_at | datetime or null | |

### 12.2 Changed tables
- **channel_link_codes renamed auth_codes**, plus `address` (str or null, where the code was
  sent) and `tries` (int). New purposes besides `invite` and `self`: `otp_login`, `link_login`,
  `mfa`, `enrol`. Same HMAC keyed storage, single use, expiry. One table for every one-time
  code instead of a second table of the same shape.
- **channel_link_attempts renamed auth_attempts**, `channel` and `address` become `kind`
  (`link_code`, `password`, `otp`, `pin`, `client_secret`, `mfa`) and `key` (address, login,
  IP or person id, as an HMAC for logins so typed passwords in the login field are not stored).
- `person`: no change. Phone numbers stay in `channel_identities` (ADR 007); the login email
  lives on the `password` credential. Note: the spec says contact details are encrypted
  fields; when field encryption lands, `login` gets a blind index (HMAC) and an encrypted copy.
- `events`: no change. Auth events use the existing columns.

### 12.3 Events (all in the hash chain)
`auth.login_succeeded`, `auth.login_failed`, `auth.mfa_failed`, `auth.locked`, `auth.unlocked`,
`auth.mfa_enrolled`, `auth.passkey_added`, `auth.recovery_code_used`, `auth.password_set`,
`auth.reset`, `auth.session_revoked`, `auth.refresh_reused`, `auth.device_bound`,
`auth.device_revoked`, `auth.otp_sent`, `auth.otp_failed`, `auth.link_sent`, `auth.pin_set`,
`auth.pin_failed`, `auth.step_up`, `auth.client_created`, `auth.client_revoked`,
`auth.client_token_issued`, `auth.dev_header_used` (once per process and person in dev mode).

Routine access-token checks and refreshes are not events (they would be most of the log);
`rbac.allow` and `rbac.deny` already record every decision. Failures before the person is known
use the system principal `auth` with the branch of the node and the HMAC of the login as
entity id. Event data never holds passwords, codes, PINs, tokens or full IP history beyond the
attempt.

## 13. Dependencies and external services **APPROVAL NEEDED for each**

Versions checked on PyPI on 2026-10-05.

| Need | Recommendation | Alternative | Licence | Status |
|---|---|---|---|---|
| Password, PIN, client secret hashing | **stdlib `hashlib.scrypt`** (N=2^17, r=8, p=1, OWASP) | `argon2-cffi` 25.1.0 (Argon2id, OWASP first choice; one C extension) | PSF / MIT | argon2-cffi last release June 2025, stable and widely used |
| Tokens, codes | **stdlib `secrets`, `hashlib`, `hmac`** | PyJWT 2.15.1 (Sept 2026, MIT) | PSF | JWT not needed: one issuer, one verifier, DB lookup |
| TOTP | **stdlib `hmac`** (RFC 6238) | `pyotp` 2.10.0 (June 2026, MIT, no deps) | PSF | pyotp adds nothing we cannot test in 20 lines |
| HKDF | **stdlib `hmac`** (RFC 5869) | `cryptography` 50.0.2 (Sept 2026, Apache-2.0 or BSD) | PSF | `cryptography` is already in the spec's stack for field encryption; take it then |
| Passkeys (WebAuthn) | **`webauthn` (py_webauthn, Duo Labs) 3.0.1** (Sept 2026), in step 11 only | `fido2` 2.2.1 (Yubico, June 2026, Apache-2.0) | BSD-3-Clause | Active; pulls `cryptography`, `cbor2`, `pyOpenSSL`, `pyasn1`, `pyasn1-modules`. Do not hand-roll CBOR, COSE and attestation |
| Rate limiting | **database table** (section 10) | `slowapi` 0.1.10 (MIT) | n/a | slowapi keeps counts in memory or Redis; neither fits |
| OAuth2 server | **hand-written token endpoint** (client credentials only, one grant) | `authlib` 1.8.0 (BSD-3) | n/a | Authlib's server is built for many grants; one grant is about 40 lines |
| Staff codes delivery | **WhatsApp authentication template through the existing channel** (no new service) | SMS provider | n/a | Meta template approval needed (category authentication); per-message fee under the existing Meta account |
| SMS (only if staff without WhatsApp exist) | **not now**; when needed, an SMS channel adapter on `46elks` (Stockholm, EU, simple REST, Finnish numbers) | Twilio Programmable SMS or Verify (global incl. Philippines; Verify adds about USD 0.05 per verification on top of the SMS fee); Semaphore (Philippine provider) for Philippine branches | n/a | External service: needs DPA and egress through channels/transport.py. Prices to confirm before choosing |

Total new runtime dependencies in the recommended first build: **none**. Passkeys add one
(`webauthn`, with `cryptography` among its dependencies). Each addition needs its one-line
reason in the pull request (CLAUDE.md).

## 14. Migration away from X-Mia-Actor

1. Add `MIA_AUTH_MODE` with default `required`; `.env.example` and `node/tests/conftest.py` set
   `dev`, so nothing breaks on the day `current_auth` lands.
2. In dev mode `current_auth` still prefers a real token; X-Mia-Actor is accepted only when the
   TCP peer is loopback and no `CF-Connecting-IP` or `CF-Ray` header is present. It never works
   on A2A routes or `/auth/*`.
3. Startup check: dev mode with `MIA_PUBLIC_URL` not on localhost refuses to start with a clear
   message. `/health` shows `auth_mode`.
4. Tests: a `login(client, person)` fixture creates a session through the service function and
   sets the cookie; new tests use it. Existing tests move from the header to the fixture file by
   file; a test asserts that in `required` mode the header gives 401.
5. The dev chat page (`static/index.html`) and `/persons` work only in dev mode; in required
   mode the page shows the login form.
6. Architecture test: no module except the dev branch of `current_auth` reads `X-Mia-Actor`,
   and every route other than `/health`, `/auth/*`, webhooks and `/.well-known/*` depends on
   `CurrentAuth`.
7. After the pilot install runs on `required`, remove `ChatRequest.actor_id` and the
   `ActorHeader` alias.

## 15. Testing

- Unit (core/auth): scrypt hash and verify, wrong password, parameters stored with the hash;
  TOTP against RFC 6238 test vectors, step reuse refused, window edges; HKDF against RFC 5869
  vectors; token issue, verify, expiry, rotation, reuse detection revokes; codes single use,
  expiry, tries; rate limit windows; PIN rules and lock.
- API: each login flow happy path; session cookie flags; CSRF origin check; refresh rotation;
  sign-out; device revoke ends sessions at once; client credentials token and expiry.
- Negative (required by CLAUDE.md for risky paths):
  - X-Mia-Actor in required mode gives 401; in dev mode from a Cloudflare peer gives 401;
    on `/a2a` gives 401 in every mode.
  - Owner without MFA gets only an enrolment session (every other route 403).
  - Inactive person with a valid token gives 403; role removed takes effect on the next request.
  - Staff token cannot read another person's visits (rbac unchanged, now with a real actor).
  - Deciding an app_only approval with aal1, without step-up, with step-up older than 5
    minutes, or over WhatsApp: refused, and an event is written.
  - A2A client cannot hold or use `approve`; on_behalf_of claim does not widen permissions.
  - Reused refresh token revokes the session; reused code, expired code, code for another
    number refused; unknown phone gets the same response and nothing is sent.
  - Lockout after the limits in section 10; unknown login takes the same time as a known one
    (within tolerance).
  - No secret, code, token or PIN appears in events, logs or error responses (scan test).
- Event chain verifies after a full login, step-up, approval and sign-out run.

## 16. Implementation plan

Ordered, each step shippable (tests green, nothing user-visible breaks). Estimates in hours for
one senior developer, tests included. Steps marked APPROVAL wait for the decisions in 13.

| # | Step | Tests (including negative) | Hours | Depends on | Parallel with |
|---|---|---|---|---|---|
| 1 | APPROVAL: data standard 1.3 (models, migration 0004, renames with data copy, `STANDARD_VERSION`), ADR 011 accepted, layout.md (`core/auth.py`, `core/keys.py`, `api/auth.py`) | migration up and down on a seeded DB; existing link-code tests pass on renamed tables | 4 | decisions | none |
| 2 | `core/keys.py`: master key file, `mia keys init`, HKDF subkeys, `MIA_NODE_SECRET` fallback | RFC 5869 vectors; missing or world-readable key file refused | 2 | 1 | 3 |
| 3 | `core/auth.py` hashing and attempts: scrypt, attempts and lockout (moves the link-code lockout onto `auth_attempts`) | wrong password; limits per pair, login, IP; equal timing | 3 | 1 | 2 |
| 4 | Sessions and `current_auth`: issue, verify, rotate, revoke; `MIA_AUTH_MODE`; dev header rules; startup check; all routes switched to `CurrentAuth`; `approvals.decide` channel from the context; login fixture; architecture test | header refused in required mode, from Cloudflare peers, on A2A; inactive person 403; reuse detection | 7 | 2, 3 | none |
| 5 | Office login: password, TOTP enrolment and check, recovery codes, MFA-required roles, cookies, CSRF origin check, minimal login page in `static/` | owner without MFA restricted; TOTP step reuse; cross-origin POST refused | 7 | 4 | 7, 8, 9, 10 |
| 6 | Bootstrap and recovery CLI: `mia auth bootstrap`, `reset`, `unlock`, enrolment links | link single use and expiry; events carry `via: cli` | 2 | 5 | 7, 8, 9 |
| 7 | Staff: login link over WhatsApp, phone code via authentication template, device binding, device login, sign-out, supervisor revoke, deactivate revokes all | unknown phone same response, nothing sent; send limit; revoked device 401 at once; forwarded link used twice refused | 7 | 4 (and Meta template approval) | 5, 8, 9, 10 |
| 8 | PIN and step-up for app_only approvals | aal1, no step-up, stale step-up, WhatsApp decision all refused; PIN lock after 5 | 4 | 4 | 5, 7, 9, 10 |
| 9 | Clients: `auth_clients`, `mia auth client add`, `/auth/token`, client roles in rbac, A2A routes accept only client tokens | client never gets `approve`; on_behalf_of claim ignored for RBAC; revoked client 401 | 4 | 4 | 5, 7, 8, 10 |
| 10 | Admin endpoints: list and revoke sessions and devices, reset a user, own session list; permissions `data:core.auth_*` in policy.csv | staff cannot list others' devices; admin reset writes event with both actors | 3 | 4 | 5, 7, 8, 9 |
| 11 | APPROVAL: passkeys with `webauthn` | enrol only from aal2; wrong RP id refused; sign counter regression refused | 6 | 5 | 7 to 10 |
| 12 | Edge and docs: cloudflared ingress allowlist, reduced public `/health`, README, `.env.example`, install guide (WhatsApp two-step verification advice), secret-scan test | public `/health` has no version or model | 3 | 4 | 5 to 11 |
| 13 | APPROVAL, only if needed: SMS channel adapter for staff without WhatsApp | contract suite for the new adapter | 5 | 7 | any |

Total without passkeys and SMS: 46 hours; with passkeys 52; with passkeys and SMS 57.
Critical path: 1, then 2 and 3 together, then 4, then 5 to 10 in parallel (27 hours for one
developer, about 14 for two).
The plan's Sprint 1 budget is 70 hours for all of "core data and access"; the hours above are
for authentication only and need the re-estimate the plan already calls for.

## 17. Open questions

Recorded in docs/questions.md as Q10 to Q16 with assumed answers: Q10 data standard 1.3
(blocking), Q11 no email resets, Q12 on_behalf_of from outside agents, Q13 one PIN as step-up,
Q14 staff codes over WhatsApp, Q15 dependencies, Q16 supervisor MFA and session lifetimes.
