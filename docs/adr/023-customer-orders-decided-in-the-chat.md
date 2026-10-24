# ADR 023: Customer orders are decided with buttons in the chat

## Status

Accepted (24 Oct 2026, D47; changes a security rule).

## Context

A customer order (`customer_service.place_order`) was a money-risk tool. approvals.request forced
it to `app_only`, decided in the authenticated app with aal2 and a fresh PIN step-up (D37), and
the clerks' card carried the customer's name and number, so every channel rendered it as a
sensitive app link. Kiosk clerks work from their phones; an order waited until someone opened
the app. The owner decided on 24 October 2026 that staff confirm customer orders with buttons in
the chat, not only in the app.

## Decision

- place_order keeps `approval: always` and gains `approval_channel: chat` in its manifest; its
  risk becomes `write_internal` (nothing is paid in the chat, the customer pays at pickup), so
  its approval is created with channel `chat`. `approval_channel` takes `any` or `chat` only,
  and request() still forces money, external and delete risks to `app_only` whatever is asked.
- The order message is plain text with Confirm and Decline buttons, sent to the active clerks
  and supervisors of the order's branch (who got the card before): items, pickup time, the
  customer's first name and the number's last four digits. Its text and blocks are redacted in
  the notification.sent event, which names the approval.
- A tap decides through approvals.decide with channel `chat` and the tapping person as the
  actor: an approver role at the approval's branch, never the requester (the customer), no
  step-up. A tap decides only a `chat` approval of type place_order asked by the person's latest
  message with buttons. The status is read under the write lock: the first tap wins, the others
  asked are told who decided, a later tap gets "Already confirmed by ..." and changes nothing,
  an expired approval says so.
- Money, external-money and delete approvals stay app-only with a fresh PIN; decide refuses a
  chat decision for them (negative test with sales.refund).

## Consequences

- Clerks confirm orders from WhatsApp and the phones page; the app decide route still works.
- The customer's first name and last four digits reach staff phones as text (WhatsApp keeps a
  copy); the full number never leaves the node and the event log holds neither.
- A tap is matched by its label on the person's latest message with buttons (channels report
  the label, not the message); a tap on an older order after a newer message with buttons goes
  the normal chat way, and that order is decided in the app.
