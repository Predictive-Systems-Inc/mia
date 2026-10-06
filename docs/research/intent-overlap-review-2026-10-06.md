# Intent overlap review: one message, one label (6 Oct 2026)

The owner's rule (D30): a message gets exactly one label. The classifier sees only the text, not
the sender, so two intents that the same message fits are merged or sharpened; code routes by
sender and role after classification. Three rules decide each pair:

1. **Questions about rules or company knowledge** go to the shared conversation `kb_*` intents
   (node/mia/learning/catalogue/conversation.yaml).
2. **Doing something stays with the role**: the role intent keeps action messages; any record
   in it that is really a question moves to the `kb_*` intent, and the descriptions say which is
   which.
3. **Same message, separated only by sender role**, becomes one intent with one owner.

Where a record still fitted two labels after the rules, it was not rewritten but removed from
intents.jsonl and listed at the end. Where an action intent fell below 15 messages after its
questions moved out, new action messages were added (marked below). Records that were word for
word examples of conversation.yaml were removed (12). The earlier merge of four site manager
intents into conversation intents is recorded in D30.

## Decisions

| Pair | Decision | Rule | Records moved |
| --- | --- | --- | --- |
| hr.payday / conversation.kb_payday | hr.payday removed | 1 | 23 to kb_payday, 1 ambiguous |
| sales.price_question / kb_prices | sales.price_question removed | 1 | 20 to kb_prices |
| sales.household_deduction / kb_household_tax_deduction | sales.household_deduction removed | 1 | 13 to kb_household_tax_deduction, 3 ambiguous (requests for a labour-cost statement; no intent yet) |
| hr.employment_terms / kb_employment_terms | hr.employment_terms removed; pay for working on a holiday counts as employment terms, not leave rules | 1 | 18 to kb_employment_terms, 3 ambiguous |
| hr.training / kb_training | hr.training keeps enrolment and "who needs it"; course questions move | 1, 2 | 8 to kb_training, 1 ambiguous, 7 new action messages |
| hr.sick_note / kb_sick_leave_rules | hr.sick_note keeps sending a note; rules questions move | 1, 2 | 4 to kb_sick_leave_rules, 3 new action messages |
| client_service.service_faq / kb_services, kb_eco_products, kb_pets, kb_insurance_damages, kb_surface_care | client_service.service_faq removed; each record to its topic | 1 | 4 kb_services, 4 kb_eco_products, 1 kb_pets, 1 kb_insurance_damages, 1 kb_surface_care, 7 ambiguous (no single topic) |
| recruiter.job_question / kb_jobs | recruiter.job_question removed | 1 | 17 to kb_jobs |
| client_service.compliment / conversation.compliment | client_service.compliment removed | 1 | 19 to compliment |
| hr.grievance / harassment_report | hr.grievance removed; HR owns the follow-up | 1 | 14 to harassment_report, 4 ambiguous (unfair treatment, not harassment) |
| bookkeeper.expense_claim / kb_expenses_travel | kept; a specific amount is a claim, "where" or "how long" is a question | 2 | 2 to kb_expenses_travel |
| bookkeeper.mileage_claim / kb_expenses_travel | kept; kilometres driven is a claim, rates and rules are questions | 2 | 3 to kb_expenses_travel, 2 new action messages |
| recruiter.apply / kb_jobs | kept; applying or sending a CV is the action, "are you hiring", "how do I apply" are questions | 2 | 5 to kb_jobs, 2 new action messages |
| hr.offboard_employee / admin.archive_record / admin.remove_access | all kept; whole leaver process vs one record vs Mia access only | 2 | 0 (descriptions sharpened) |
| recruiter.publish_job_ad / marketing.publish_post | kept; any job vacancy (ad or hiring post) is the recruiter's | 2 | 1 publish_post to publish_job_ad ("schedule the hiring post") |
| client_service.update_contact / admin.update_client / bookkeeper.billing_details | one intent: **admin.update_client** (client or office sender) | 3 | 17 + 21 to admin.update_client |
| client_service.change_access / admin.update_site | one intent: **admin.update_site** (client, supervisor or office sender) | 3 | 20 to admin.update_site |
| client_service.damage_claim / site_manager.report_damage / kb_insurance_damages | one intent: **site_manager.report_damage** (staff or client sender); general policy questions stay kb_insurance_damages | 3 | 19 to report_damage |
| site_manager.report_injury / injury_minor, emergency, chemical_exposure | kept only for a supervisor or the office reporting someone else's injury; the injured person's own message goes to the conversation intent | split | 15 to injury_minor, 1 to chemical_exposure, 0 to emergency, 2 ambiguous, 11 new supervisor and office messages |
| site_manager.chemical_safety / kb_chemical_safety, chemical_exposure, kb_safety_data_sheet | site_manager.chemical_safety removed | split | 9 to kb_chemical_safety, 5 to chemical_exposure, 2 to kb_safety_data_sheet, 1 ambiguous |
| conversation.kb_cleaning_howto / kb_surface_care | narrower wins: a named material (marble, steel, parquet, leather, induction, vinyl, rubber) is surface care | narrower | 9 to kb_surface_care (no dilution records) |
| conversation.emergency / personal_threat | narrower wins: the sender is threatened, followed or held | narrower | 4 to personal_threat |
| purchaser.broken_equipment / conversation.hazard_report | dangerous now (sparks, smoke, hot water leak, unsafe ladder) is a hazard, else broken equipment; rule in both descriptions | narrower | 4 to hazard_report |
| site_manager.data_breach / dispatcher.lost_key | kept; a physical key alone is lost_key, anything with data (phone, papers, codes) is a breach | 2 | 0 (descriptions sharpened) |
| admin.reset_login / dispatcher.cannot_access_site | kept; Mia login vs physical site door | 2 | 0, 1 ambiguous ("locked out") |
| dispatcher.directions / conversation.oos_directions_transport | kept; a company site or visit is dispatcher.directions, anywhere else is out of scope | 2 | 0 (descriptions sharpened) |

### Owners chosen for rule 3

- **admin.update_client**: the client record is master data, which D30 gives to admin; the
  client service and the bookkeeper are notified of the change. The three intents read the same
  ("new email", "invoices to this address", "new contact person").
- **admin.update_site**: door codes, keys, alarm and opening hours are fields of the site record;
  a client's "the door code changed" and a supervisor's "fix the alarm instructions" are the same
  change.
- **site_manager.report_damage**: damage at a site is an incident the site manager follows up
  (insurance, cause), whoever reports it; the claim towards the client is the follow-up, and
  "your cleaner broke my vase" and "I broke a vase" carry the same facts.

## Ambiguous records removed (not relabelled)

| Old id | Message | Between |
| --- | --- | --- |
| hr.payday/en/024 | can i get my salary earlier this month, i have a problem | kb_payday, hr.salary_advance |
| sales.household_deduction/en/007 | i need a summary of last year's cleaning costs for my tax return deduction | a statement request (no intent), kb_household_tax_deduction |
| sales.household_deduction/en/015 | for the tax credit I need the labour costs for 2026, and pls send to my email | same |
| sales.household_deduction/en/016 | Could you confirm the labour share of my invoices for the household expense deduction? | same, bookkeeper.invoice_question |
| hr.employment_terms/en/007 | do we get paid for travel time between sites | kb_employment_terms, kb_expenses_travel |
| hr.employment_terms/en/018 | can i see my employment contract again | a document request (no intent), kb_employment_terms |
| hr.employment_terms/en/019 | do we get paid extra for using our own phone for work? | kb_employment_terms, kb_expenses_travel |
| hr.training/en/017 | i passed the hygiene passport test, here is the certificate | hr.submit_document, hr.training |
| client_service.service_faq/en/001 | what products do you use? are they safe for cats | kb_eco_products, kb_pets |
| client_service.service_faq/en/003 | do I need to be home when the cleaner comes | kb_booking_process, kb_keys_security |
| client_service.service_faq/en/006 | Are your staff background checked? | kb_keys_security, kb_services |
| client_service.service_faq/en/007 | what happens if the cleaner is sick on our day, does someone else come? | kb_services, kb_cancellation_policy |
| client_service.service_faq/en/009 | do the cleaners speak english? my husband doesn't speak finnish | kb_services (no closer topic) |
| client_service.service_faq/en/010 | Do you also clean on weekends and public holidays? | kb_services, kb_opening_hours_contact |
| client_service.service_faq/en/016 | do you work evenings? and do you have insurance? we're a small office | two topics (multiple_requests) |
| hr.grievance/en/007 | Sanna treats me unfair, i want to report it | harassment_report, an HR grievance (no intent) |
| hr.grievance/en/010 | i need to report something serious about a colleague, privately | same |
| hr.grievance/en/016 | is there someone outside my team i can talk to about a problem at work | same, kb_who_to_contact |
| hr.grievance/en/017 | my colleague is always late and i have to do her work, not fair | an HR grievance (no intent), client_service.complaint |
| site_manager.report_injury/en/010 | needle stick from a bag at the clinic | injury_minor, emergency (needs urgent care) |
| site_manager.report_injury/en/019 | my hands are bleeding and cracked from the new chemical, cant hold the mop | injury_minor, chemical_exposure |
| site_manager.chemical_safety/en/009 | someone put chemical in a water bottle with no label, what is it | kb_chemical_safety, hazard_report |
| dispatcher.cannot_access_site/en/014 | locked out | cannot_access_site, admin.reset_login |

## Open

- An HR grievance that is not harassment (unfair treatment, workload) has no intent now; four
  messages wait for that decision.
- A household deduction statement (labour costs for the tax return) is an action with no intent.
