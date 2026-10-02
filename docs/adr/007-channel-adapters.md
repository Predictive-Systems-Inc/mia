# 007: Channel adapters package and WhatsApp

## Status
Accepted (decision D13), built on branch feat/channels-whatsapp. Design: docs/superpowers/specs/2026-10-02-channel-adapters-whatsapp-design.md.

## Context
D13 brings outside channels into scope for the local node, WhatsApp first. The spec defines a
ChannelAdapter interface but docs/layout.md has no place for channel code beyond
chat/channels.py (in-app notifications and the call stub).

## Decision
- New package node/mia/channels: the adapter protocol, registry, shared rendering, delivery
  service, outbox, linking, a ChannelTransport for HTTP, the webhook router, a simulator
  adapter, and one folder per adapter (whatsapp/ first).
- WhatsApp is called directly through the Meta Cloud API with httpx (already a dependency).
  No messaging provider and no WhatsApp library.
- Data standard 1.2 adds channel_identities, channel_link_codes, channel_link_attempts,
  channel_outbox and channel_inbound (migration 0003). Identities are linked by one-time code;
  person gets no phone field.
- Agents and chat code reach channels only through channels.deliver(); every adapter must pass
  a shared contract suite.

## Consequences
- A new channel is a new folder plus registration; agents do not change.
- Messages to channels carry real names (they cannot be pseudonymised), so ChannelTransport
  refuses sensitive blocks and logs every send; rule 6 covers model egress, this covers
  channel egress.
- The node needs a public HTTPS URL (Cloudflare Tunnel) and Meta-approved templates before
  proactive WhatsApp messages work; until then delivery falls back to the app copy.
