# WhatsApp setup (Meta Cloud API)

The node talks to WhatsApp through the Meta Cloud API. Meta's screens change often; follow what
they show. Everything below runs on the node's own server.

## 1. Meta app and test number
1. Sign in at developers.facebook.com, create an app (type Business), and add the WhatsApp product.
2. From WhatsApp, API setup, copy the Phone number ID and the temporary access token. Add your own
   phone as a recipient (up to 5 test recipients; each confirms with a code).
3. From App settings, Basic, copy the App secret.
4. For anything that runs unattended, create a System user in Business Settings, give it the app
   and the WhatsApp account, and generate a permanent token.

## 2. Node settings (`.env`, never committed)
```
MIA_NODE_SECRET=<python -c "import secrets; print(secrets.token_hex(32))">
MIA_PUBLIC_URL=https://<your tunnel hostname>
MIA_WA_TOKEN=<access token>
MIA_WA_APP_SECRET=<app secret>
MIA_WA_VERIFY_TOKEN=<any string you choose>
MIA_WA_PHONE_NUMBER_ID=<phone number id>
MIA_WA_NUMBER=<the WhatsApp number, digits only, for invite links>
```
Then switch the channel on in `node/config/org/<org>/settings.yaml`:
```
channels:
  whatsapp: {enabled: true}
```

## 3. Public webhook through Cloudflare Tunnel
1. Install `cloudflared`, log in, and create a named tunnel with a stable hostname.
2. Route the hostname to `http://localhost:8000` and run the tunnel as a service beside `mia serve`.
3. In Meta, WhatsApp, Configuration, set the callback URL to
   `https://<hostname>/channels/whatsapp/webhook` and the verify token to `MIA_WA_VERIFY_TOKEN`.
   Subscribe to the `messages` field.

## 4. Templates (needed for messages Mia starts)
Outside the 24 hour window WhatsApp only delivers approved templates. Create these in WhatsApp
Manager, in Finnish (`fi`) and English (`en`; if Meta names it `en_US`, use that code in
`node/mia/channels/whatsapp/templates.py`), category Utility:

| Name | Body | Buttons |
|---|---|---|
| `mia_new_message` | Mia: sinulle on uusi viesti työasioista. Vastaa nähdäksesi sen. | Quick reply: Näytä |
| `mia_cover_request` | Hei {{1}}, voitko tuurata käynnin {{3}} klo {{4}}, {{2}}? | Quick reply: Hyväksyn, En pysty |

English: "Mia: you have a new message about work. Reply to see it." [Show]; "Hi {{1}}, can you
cover the visit on {{3}} at {{4}}, {{2}}?" [Accept] [Decline]. Until a template is approved,
messages to people outside the window stay in the app only (the outbox marks them failed).

## 5. Check it
1. `uv run mia serve` (with the tunnel running). Meta's "Verify and save" must succeed.
2. `uv run mia invite <your name in the seed or one you added>`; open the link on your phone and send.
3. Mia answers with a welcome. Try the demo from the README over WhatsApp.
4. `GET /health` and the `channel_outbox` table show what was sent and its delivery status.
