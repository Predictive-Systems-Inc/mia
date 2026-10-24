# ADR 021: The simulator channel runs only in dev mode

## Status

Accepted (21 Oct 2026, a security fix).

## Context

A security review of 840d46d found that the sim channel (`SimAdapter`, node/mia/channels/simulator.py)
verifies its webhook with the fixed secret `sim-secret`, which is public in the source. 840d46d
enabled `channels.sim` in the Ferino's settings, and the demo organisation already had it. A
deployed node with sim enabled accepted `POST /channels/sim/webhook` signed with that secret from
anyone on the internet. Channel identities are keyed by channel and address, so the caller could
impersonate any linked staff number and drive the OTP login over the channel.

## Decision

- The simulator is registered only when `MIA_AUTH_MODE=dev`, which check_mode allows on a
  localhost public URL only (ADR 011). In required mode it is never registered: an enabled
  `channels.sim` setting is ignored with one warning line at startup, and the sim webhook answers
  404 like any disabled channel.
- `mia channels sim` refuses in required mode with a message naming dev mode.
- `MIA_SIM_SECRET` sets the sim webhook secret; empty keeps the public `sim-secret` default, which
  can now only be reached in dev mode.

## Consequences

- Organisation settings may keep `sim: {enabled: true}` for local trials; on a server it has no
  effect. Both settings.yaml files and docs/testing-ferinos.md say so.
- Tests run in dev mode (the test conftest) or register `SimAdapter` directly, so they are
  unchanged. node/tests/channels/test_sim_dev_only.py pins the required mode refusal (webhook
  404, nothing stored, the CLI refuses) and the dev mode path.
- A dev node may still be bound to 0.0.0.0 (or run in docker with the default localhost URL),
  so the startup check alone does not keep the LAN out. The sim webhook therefore checks each
  request: it answers 404 unless the peer is loopback and no `cf-connecting-ip` or `cf-ray`
  header is present (the same check as the dev actor header, `deps.direct_loopback`).
  `MIA_SIM_SECRET` remains a second guard.
