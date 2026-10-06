# Intent overlap reference pairs

Pairs that a person confirmed as real overlaps (one message could fairly get either label).
The Decisions table below is what `mia skills overlap --expect` parses (bare kb_* names mean
conversation.kb_*); recall against it is a reference number, not a bar, because this list is not
exhaustive. Add a row whenever the owner confirms a new pair. The "## Not overlaps" table keeps
rejected pairs so they are not asked again.

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
| conversation.compliment / conversation.thanks | owner confirmed 2026-10-06 (overlap tool, top 10) | 1 | 0 |
| conversation.goodbye / conversation.thanks | owner confirmed 2026-10-06 | 1 | 0 |
| conversation.confusion / conversation.rephrase_simpler | owner confirmed 2026-10-06 | 1 | 0 |
| conversation.emergency / conversation.hazard_report | owner confirmed 2026-10-06; sharpen, do not merge (different handling) | 2 | 0 |
| site_manager.report_damage / site_manager.report_injury | owner confirmed 2026-10-06 | 2 | 0 |
| admin.update_client / hr.update_details | owner confirmed 2026-10-06; same words, two record types | 3 | 0 |

## Not overlaps

| Pair | Why |
| --- | --- |
| dispatcher.add_visit / dispatcher.reschedule_visit | same topic, different action |
| client_service.book_cleaning / client_service.change_booking | same topic, different action |
| admin.add_site / admin.update_site | same topic, different action |
| conversation.kb_cleaning_howto / chemical exposure | shared topic only |
