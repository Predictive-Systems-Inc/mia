# Rollout at Hype: runbook

Status: written 2026-10-12 for plan Sprint 5 ("whole Hype team onboarded; two weeks of
supported use"). The steps below are the real-world part of the plan; everything they call
exists on the node. Decisions they depend on: D19 (a Mac mini on site), D20 (cleaners work
over WhatsApp, no app; agree it with Hype first), D13 (no Mia Cloud).

## 0. Before the install

- Hype agrees to WhatsApp instead of an app (D20) and names the payroll system (Q24).
- A Meta business account with a WhatsApp Business phone number (docs/whatsapp-setup.md, 1).
- The Mac mini (24 GB or more, D19) on Hype's network, Docker Desktop installed.
- The people list, the sites and the jobs from Hype's current schedule, as the YAML below.

## 1. Install the node

Follow deploy/install.md: get the code, settings in `deploy/.env` (`MIA_MODEL=local/<model>`
once Ollama runs on the mini, `MIA_EGRESS_LEVEL=none` for real data), build, start, check
`/health`, then the first backup and restore test (install.md 5 and 6). The update procedure
is install.md "Updates".

## 2. Keys and the first owner

```
uv run mia keys init            # the master key file (ADR 011); back it up separately
uv run mia migrate
uv run mia auth bootstrap --email owner@hype.example --name "Owner Name"
```

The owner opens the enrolment link once (password and TOTP app) and can then sign in on the
office page.

## 3. Master data

Write Hype's people, clients, sites and jobs to a YAML file and import it. The import is safe to
re-run: rows whose name already exists in the branch are skipped, so the file can grow week by
week. Access notes are stored as given (they show in the app only, never in a message that
stays on a phone).

```yaml
organisation: {name: Hype Siivous Oy, country: FI, default_language: fi}   # first import only
branch: {name: Helsinki, timezone: Europe/Helsinki}                        # first import only
people:
  - name: Sanna Virtanen
    roles: [supervisor]
    language: fi
  - name: Juha Laine
    roles: [staff]
    skills: [general, windows]
    language: fi
    home_address: Vilhonvuorenkatu 11, 00500 Helsinki
    availability: {start: "06:00", end: "20:00", days: [0, 1, 2, 3, 4]}
    max_weekly_minutes: 2400
clients:
  - name: Kalasatama Office Oy
    locations:
      - name: Kalasatama office
        address: Hermannin rantatie 2, 00580 Helsinki
        site_type: office
        instructions: Vastaanotto avaa oven klo 6.
        access_notes: Koodi 1234
        geofence_radius_m: 100
jobs:
  - name: Kalasatama morning clean
    location: Kalasatama office
    recurrence: FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
    start_time: "06:30"
    duration_minutes: 120
    required_skills: [general]
    checklist: [Roskat, Pinnat, Lattiat]
```

```
uv run mia import hype.yaml
uv run mia geocode                    # home bases and sites (needs MIA_GEOCODER_KEY, egress)
uv run mia schedule generate          # the next 28 days of visits; the node keeps them ahead
```

Assign the first visits from the office page or the API (`POST /visits/{id}/assign`); from
then on generation copies the last assignment of each job on the same weekday.

## 4. Link the staff phones

For each cleaner: `uv run mia invite "Juha Laine" --as "Sanna Virtanen"` prints a one-time
WhatsApp link; the cleaner opens it and sends the prefilled `LINK <code>` message. The welcome
reply confirms the link. Supervisors sign in on the office page the same way as the owner
(`mia auth link NAME` sends a login link over WhatsApp).

## 5. The first week (supported use)

- Morning: the supervisor opens `/supervisor/summary` (unfilled visits, late check-ins,
  check-ins outside a fence, open site problems, pending approvals).
- Cleaners: check in by text ("Olen perillä") or a location share, ask the door code, tick the
  checklist, send a photo, report a problem, check out.
- Evening: the daily plan goes out at 17:00 (`alerts.daily_plan_time`), unstaffed visits for
  tomorrow at 15:00.
- Friday: `uv run mia billing export --month YYYY-MM` and the timesheets of the week on
  `/timesheets` (correct, approve); `uv run mia payroll export --from --to` for the approved
  rows.
- Every day: `/health` shows the events chain, the channels and the skill models; the backup
  runs on its own (Litestream), the restore test weekly.

## 6. What to watch

- The intent catalogue's "needs work" rows (docs/capabilities.md) and `chat.turn_capped`
  events: each is a message Mia could not handle; the supervisor notice names the person.
- Finnish edge cases from real messages become labelled examples for the next role skill
  model (`mia skills generate`, README "Role skill models").
- Questions that need the owner: docs/questions.md (Q19 board, Q20 timesheets in core, Q24
  payroll format).
