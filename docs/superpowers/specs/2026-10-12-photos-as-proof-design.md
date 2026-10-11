# Photos as proof of work: design

Date: 2026-10-12. Status: built (plan item 5, Sprint 3; the Phase 1 intent
`dispatcher.send_photos`; spec.md "visit: proof refs"). Builds on field work over chat.

## Goal

A cleaner sends a photo on WhatsApp (or the in-app chat later) during a visit; the node
downloads it through the channel's own transport (rule 6), stores it under the node's media
folder and records the reference on the visit (`proof_refs`), with an event. The cleaner hears
that it was saved for which site.

## Behaviour

- `InboundMessage` carries `media_id` and `media_kind` (image, document, video, audio) when the
  channel delivered media; the WhatsApp adapter reads them from the message; the simulator
  takes `media` as an id with bytes registered on the adapter.
- `ChannelAdapter.fetch_media(media_id) -> bytes | None`: WhatsApp resolves the media id to its
  URL on the Graph API and downloads it, both through the adapter's client (the channel
  transport); the simulator returns the registered bytes.
- Inbound handling: a message with media from a linked person goes to the proof step, not the
  chat turn. The visit is the person's current one today (in progress, else the nearest ahead),
  as check-in picks it. The file lands in `MIA_MEDIA_DIR/<branch>/<visit>/<ulid>.<ext>` (0600),
  the reference `media/<branch>/<visit>/<file>` is appended to `visit.proof_refs` through
  `store.update` (event `visit.proof_added`, the reference only, never the bytes), and the
  reply says "Photo saved for {location}." A person without a visit now gets "I found no visit
  to attach the photo to"; a download failure gets the generic error reply and the inbound row
  is marked failed.
- Text sent with the photo (a caption) is ignored for the chat turn in this build.

## Out of scope

Photos from the in-app chat (the chat API has no file upload yet), viewing photos in the app,
retention and deletion (follow the backup policy, spec "Keys and backup").

## Tests

WhatsApp: media id and kind from the image sample; `fetch_media` through a mock transport (two
requests, bearer header). Simulator end to end: a photo during a visit in progress saves the
file and the reference and replies; no visit replies without saving; a failed download marks
the inbound row failed.
