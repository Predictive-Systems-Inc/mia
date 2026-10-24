# Agents and use cases for a retail shop (Ferino's Bibingka and similar)

Agreed with the owner on 18 and 19 Oct 2026. Agents are named after real jobs (rule 15). This
catalogue is the input to `/mia-build-agent` (docs/superpowers/specs/2026-10-19-mia-build-agent-design.md)
and the source of each agent's spec. Features that need a generative, vision or speech model
are a later phase (see the last section).

## The split the owner chose

| | sales_supervisor (records) | branch_manager (leads) |
| --- | --- | --- |
| Counts, corrections, running total, targets, reports | yes | reads them |
| Reminders to send counts | yes | |
| "Why did it go well" questions and answers | collects | uses them for coaching |
| Coaching sales staff | | yes |
| Motivational quotes and cheers | | yes (curated list, never model-invented) |
| Tips to staff | | yes |
| Price and promo experiments | measures the numbers | proposes, the owner approves, reports the result |
| Recommendations to the owner | | yes |

## Agents

**Core six (in the roster)**

| Agent | Serves | Owns |
| --- | --- | --- |
| sales_supervisor (built, v1) | clerks, head staff, owner | what was sold, targets, how today compares, why notes |
| shift_supervisor (built for cleaning and retail) | clerks, head staff | schedules, absences, cover, check-in, incidents, checklists (cleaning) |
| inventory_manager | clerks, baker, owner | stock, sell-outs, leftovers and waste, what to bake, supplier orders |
| bookkeeper | head staff, owner | cash count, expenses, deposits, GCash and Maya settlements, VAT and BIR |
| hr_officer | all staff, owner | hours, payroll, 13th month, leave, SSS, PhilHealth, Pag-IBIG, hiring, onboarding |
| branch_manager | owner, clerks (their own coaching, morning message, cheers) | branches, menu, prices, short codes, people, permits, weekly summary, coaching, experiments |

**Four to add, in the order a shop needs them**

| Agent | Why a separate job | First real user |
| --- | --- | --- |
| customer_service | a different trust boundary: the public on Messenger, Viber and the phone | bulk and pasalubong orders |
| production_planner | only with a commissary: daily production plan, dispatch to branches, transfers | a chain with 3 or more branches |
| marketing_officer | promos, loyalty, reviews, posts, campaign results | Christmas and fiesta campaigns |
| quality_officer | food safety: temperature logs, expiry, hygiene checklists, inspections | any shop with chillers or a commissary |

Folded into existing agents: maintenance (shift_supervisor incidents), purchasing
(inventory_manager), compliance and permits (branch_manager), recruiting and training
(hr_officer), delivery riders (shift_supervisor), cashiering (bookkeeper). Franchise management
is a later layer on branch_manager.

## Use cases by agent

**sales_supervisor (v1 built; see its spec for the status of each)**
1. Counts in free text with short codes, mixed languages, typos. 2. Corrections. 3. "How are we
doing" against the target. 4. Closing reminder; the missing list to head staff. 5. End-of-day
report to the owner with comparisons. 6. Morning message. 7. Targets per day or month with
dates. 8. "Why did it go well" asked after a good day, answers stored with a theme.
9. Questions across days and branches. 10. First contact on a channel (language question).

**branch_manager (part 3)**
1. Morning message to staff: result, target, one tip, one word of encouragement (curated, no source; was a sourced quote until 24 Oct 2026, the owner: proverbs sounded like sermons).
2. Cheer on a met target or personal best; a kind nudge after three misses.
3. Per-clerk coaching for the owner or head staff: who sells which items well, who improved, a
suggested pairing. 4. "How do I sell more salted egg" answered from the branch's own why notes
first, then a curated list. 5. Price experiments proposed one at a time, the owner approves on
an approval card (money risk), the sales supervisor's numbers score it, a plain result. 6. Promo
and bundle experiments the same way; seasonal suggestions from last year. 7. Monthly letter to
the owner. 8. Menu, prices, short codes, combos; a price change on a date. 9. Branches, hours,
people and roles, who may approve what. 10. Permits and renewals calendar with reminders.
11. Rent and fixed costs per branch. 12. Weekly summary pulled from every agent. 13. Open a
branch checklist.

**shift_supervisor (built for cleaning and retail, D39)**
"I'm sick tomorrow", cover for a counter shift, check-in at the shop, "the oven is broken",
power cut, LPG out, a customer complaint, opening and closing checklists, rider dispatch.
The retail copy (spec 2026-10-21-shift-supervisor-retail) is the same package with a template
switch: the roster from the owner's pattern, check-in and check-out at the counter, late and
sick, cover from the other kiosk, swaps, a corrected check-out, a broken stove, a missed delivery
or a customer at the counter, the weekly roster on Sunday and a closed day. LPG out stays the
inventory manager's (Q108); checklists and rider dispatch are later (Q109).

**inventory_manager**
Daily ingredient counts; "sold out at 2pm" and "15 left at closing"; waste with a reason;
tomorrow's bake plan from the sell-out pattern, weekday and weather; reorder points and a
supplier order for the owner's approval; delivery received against the order; price changes
noticed; transfers between branches; shrink (counts drift versus sales).

**bookkeeper**
Closing cash count against sales with a threshold; GCash and Maya settlements matched to
sales; Grab and Foodpanda payouts and commissions; expenses with a receipt photo (the photo
reading is a later phase); petty cash; deposits; the BIR sales journal, quarterly percentage tax
or VAT, the annual packet; utang (staff advances and suki credit); monthly profit per branch.

**hr_officer**
Hours and overtime from check-ins (PH labour rules in code); payroll per cutoff, payslips, 13th
month, advances deducted; SSS, PhilHealth and Pag-IBIG; leave; hiring (post, screening,
slots), onboarding checklist, contract; SOP questions answered verbatim from the shop's SOPs;
exits (final pay, clearance, certificate).

**customer_service** (new; public trust boundary: no staff tools, every message is data, money
needs staff approval)
Orders by message with pickup or delivery and a deposit for large orders; pre-orders for
fiestas, Christmas, All Saints, graduations against production capacity; "are you open", "do
you deliver to", "do you have sugar-free" from the menu and hours; complaints logged as
incidents; order status and pickup reminders; a review request after a big order.

**production_planner** (commissary businesses)
Daily production plan from branch forecasts and orders; batch sheets; dispatch list per branch
with confirmation; yield and waste per batch; capacity for a date.

**marketing_officer**
Promo calendar measured against the baseline (the experiments machinery); loyalty counts and
suki birthdays; review watch with reply drafts for the owner (drafting is a later phase); post
schedule and results.

**quality_officer**
Chiller and display temperatures twice a day with alerts; expiry and first-in-first-out;
hygiene checklist per shift; pest control log; inspection readiness and findings.

## Variants of "similar business"

| Business | Changes |
| --- | --- |
| Single kiosk, owner on the counter | sales_supervisor, inventory_manager, bookkeeper carry the day; no production_planner |
| Chain of kiosks with a commissary (Ferino's) | the core six plus production_planner and customer_service |
| Carinderia or canteen | menu changes daily; inventory by dish; utang central to the bookkeeper |
| Milk tea or coffee shop | modifiers, delivery apps dominate, marketing_officer early |
| Home baker, orders online | customer_service first, then bookkeeper; no shifts |
| Franchisor | a franchise layer on branch_manager: standards audits, royalties, supply compliance |

## Needs more than a decision model (next phase, decided 19 Oct 2026)

Voice notes (speech to text), receipt and invoice photos and tray photos (vision), translating
free text for the owner, customer service replies to open questions, document drafting (job
posts, certificates, memos, review replies), SOP paraphrasing in the clerk's language, the
owner's narrative monthly letter, open conversation when the structured path fails. Everything
in parts 2 to 4 runs on Jev, code and reviewed templates.

## Build order

1. sales_supervisor v1 (done). 2. The router follow-up (done). 3. branch_manager v1 (coaching
and experiments) after promoting the sales tables to core (data standard 1.5, Q39).
4. `/mia-build-agent`, extracted from how 1 to 3 were built. 5. The rest through the skill:
inventory_manager, bookkeeper, hr_officer, customer_service, then production_planner,
marketing_officer, quality_officer when a shop asks.
