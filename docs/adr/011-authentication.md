# 011: Authentication and identity on the node

## Status
Accepted (decision D17, answers to Q10 to Q16).

## Context
The actor still comes from the unverified X-Mia-Actor header (architecture rule 4). The node is
reachable from the internet through a Cloudflare Tunnel, so anyone can act as anyone. The plan
moves authentication first: it blocks the pilot with real people, WhatsApp in production and
A2A, where D14 and ADR 008 require OAuth2 or mTLS and forbid the header. The spec fixes the
shape (office users: email and password or passkey, MFA for owner, admin and accountant; staff:
phone code and a bound device; short access tokens with refresh tokens; node-issued agent
credentials; a PIN for risky approvals by voice) but not the mechanism.

## Decision
- Tokens are opaque random values (stdlib `secrets`) stored as SHA-256 hashes; no JWT, because
  the node is the only issuer and verifier and a lookup gives instant revocation. Access tokens
  last 15 minutes; refresh tokens rotate on every use and a reused one revokes the session.
  Web keeps both in HttpOnly, Secure, SameSite=Strict cookies with an Origin check; mobile and
  A2A use bearer tokens.
- Office users: email and password (stdlib scrypt), then TOTP (stdlib hmac, RFC 6238) with ten
  recovery codes; MFA required for owner, admin and accountant. Passkeys follow as a later step
  with the `webauthn` library once approved.
- Staff: a code sent to their linked WhatsApp number with a Meta authentication template, then
  a bound device holding a device secret. WhatsApp-linked staff can also get a one-time login
  link. The phone number is the existing channel identity, so person gets no phone field. No
  SMS provider until someone without WhatsApp needs one.
- Outside agents and services: OAuth2 client credentials issued by the node, opaque tokens for
  one hour, roles loaded like manifest agent roles, never `approve`. mTLS is not used because
  TLS ends at Cloudflare. A2A routes accept only client tokens.
- One FastAPI dependency (`CurrentAuth`) derives the actor for every route: the person from the
  session (reloaded each request, roles from `person`), wrapped with `as_agent` when an agent
  runs; outside clients act only as themselves, and any on_behalf_of they claim is logged, not
  trusted. `rbac.require` is unchanged. `approvals.decide` takes its channel from the session.
- Money, external and delete approvals need an aal2 session plus a 6-digit PIN entered within
  the last 5 minutes.
- Secrets: one master key file (root-only, Docker secret) with HKDF subkeys for code HMACs and
  TOTP seeds, so no TOTP seed is stored. Limits and lockouts are counted in the database.
- Every login, failure, lockout, enrolment, reset, revocation, step-up and client token is an
  event; secrets never appear in events or logs.
- `MIA_AUTH_MODE=dev` keeps X-Mia-Actor for development and tests, only from loopback without
  Cloudflare headers; the node refuses to start in dev mode with a public URL.
- PROPOSED data standard 1.3 (needs approval): new auth_credentials, auth_devices,
  auth_sessions, auth_clients; channel_link_codes and channel_link_attempts renamed to
  auth_codes and auth_attempts and generalised.

## Consequences
- The first build adds no runtime dependency and no external service; passkeys add `webauthn`
  (with `cryptography`), SMS would add a provider. Each needs approval and a one-line reason.
- New modules core/auth.py, core/keys.py and api/auth.py are added to docs/layout.md when built.
- Tests move from the X-Mia-Actor header to a login fixture; an architecture test keeps the
  header out of every route except the dev path.
- Password resets need an admin, the linked WhatsApp or the node CLI, because the node sends no
  email. A lost master key forces every MFA user to re-enrol.
- Meta must approve an authentication template before staff can log in to the app by phone.
- Field encryption, when it lands, wraps the TOTP key as a data key so master key rotation does
  not break authenticators, and adds a blind index for the login email.
