# Capabilities and intents of a cleaning company

The master list of what Mia's agents do for a cleaning company, in English (D26: intents are
defined and measured in English first; translation is a separate layer). It is organised by
owning agent, a hired role that mirrors a human job (D16), and every row is tagged with the
end-to-end process it belongs to. docs/plan.md ("Agents, processes and capabilities beyond
Phase 1") explains the model; this file is the list.

The tables are machine-read: node/tests/evals/test_intent_classification.py takes the intent
ids and meanings from here, and node/tests/test_intent_metrics.py checks that every
message-triggered intent has test messages in node/tests/evals/intents_en.yaml. Keep one row per
intent and the column order below.

## Legend

| Column | Values |
| --- | --- |
| Intent | `agent.intent`, stable snake_case id. `other` is the out-of-scope label (small talk the agent cannot help with, other topics, injection attempts). |
| Who | C cleaner, S supervisor, O office or owner, A accountant, CL client, L lead (prospective client), AP applicant |
| Trig | msg (a person's message), event (something happened in Mia or a connected system), sched (a time or a deadline) |
| Risk | read, write (internal write), money, external (leaves the company: client, authority, public), delete. Money, external and delete always need an approval (rule 3). |
| Sens | n normal, p personal data, sc special category or equally sensitive (health, ID documents, union, criminal); sc never goes to a cloud model, even pseudonymised |
| Approval / SoD | who approves, and separation-of-duties pairs (preparer is not approver). "instr." means the person's explicit instruction is the approval (D1). "-" none. |
| Legal | y when the action has legal effect (contract, termination, statutory filing, liability); a person decides, the agent drafts |
| SoR | system of record: Mia, Acct (accounting system), Payroll (payroll system), Bank, Auth (authority portal), Social (social media, review sites), Jobs (job boards) |
| Ctry | both, FI, PH |
| Ph | phase: 1, 2 or 3 (docs/plan.md) |
| Built | yes if Mia handles it today, part if partly, no |
| Proc | L2C Lead-to-Contract, C2S Contract-to-Service, S2C Service-to-Cash, H2R Hire-to-Retire, P2P Procure-to-Pay, R2R Record-to-Report, Plat (platform, no business process) |

Roles marked "proposed" are not yet in the roster of docs/plan.md (see docs/questions.md Q18):
quality (quality, safety and compliance coordinator) and office (office manager: master data,
administration, management reporting). `chat` is the platform's cross-cutting layer, not a
hired role.

Built today: the dispatcher's six classifier intents (node/mia/agents/dispatcher/classifier.py,
`IntentName`), small talk answered without tools, and WhatsApp account linking by code
(node/mia/channels/linking.py). Everything else is planned.

## Dispatcher (Operations): scheduling, dispatch, field work, keys

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dispatcher.report_absence | Staff member says they cannot work (sick, other reason), will be late, or must leave early | C, S | msg | write | p (sc if health details) | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.absence_scope | Answer to which visits a just-reported absence covers (whole day, morning, afternoon) | C | msg | write | p | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.my_visits | Ask about own visits, shifts or schedule; supervisors may ask about someone else's | C, S, O | msg | read | p | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.find_cover | Supervisor asks who could take over a visit or shift | S, O | msg | read | p | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.assign | Supervisor names whom to assign as cover after candidates were shown | S, O | msg | write | p | instr.; rule break: admin or owner | n | Mia | both | 1 | yes | C2S |
| dispatcher.cover_reply | Cleaner accepts or declines a cover request sent to them | C | msg | write | n | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.missed_check_in | No check-in some minutes after a visit starts: ask the cleaner, alert the supervisor | - | event | write | p | - | n | Mia | both | 1 | no | C2S |
| dispatcher.unstaffed_visits | Daily check for tomorrow's visits without a cleaner | - | sched | read | n | - | n | Mia | both | 1 | no | C2S |
| dispatcher.daily_plan | Evening message to each cleaner with tomorrow's visits | - | sched | write | p | - | n | Mia | both | 1 | no | C2S |
| dispatcher.check_in | Cleaner says they arrived at the site (or shares location) | C | msg, event | write | p | - | n | Mia | both | 1 | no | C2S |
| dispatcher.check_out | Cleaner says the visit is finished and they are leaving | C | msg, event | write | p | - | n | Mia | both | 1 | no | S2C |
| dispatcher.cannot_access_site | Cleaner is at the site but cannot get in (locked, no key, wrong code, alarm) | C | msg | write | n | - | n | Mia | both | 1 | no | C2S |
| dispatcher.site_problem | Site conditions stop or change the work (no water or power, renovation, event, client still there) | C | msg | write | n | - | n | Mia | both | 1 | no | C2S |
| dispatcher.visit_details | Ask practical details of a visit: address, door code, where things are, special instructions | C | msg | read | p | - | n | Mia | both | 1 | no | C2S |
| dispatcher.checklist | Ask for or tick off the visit checklist | C | msg | write | n | - | n | Mia | both | 1 | no | C2S |
| dispatcher.send_photos | Send before or after photos as proof of work | C | msg | write | p | - | n | Mia | both | 1 | no | C2S |
| dispatcher.extra_time | Ask to stay longer than planned to finish the job | C | msg | write | n | supervisor | n | Mia | both | 2 | no | S2C |
| dispatcher.extra_work_on_site | Client on site asked the cleaner for extra work not in the order | C | msg | write | n | supervisor (priced by code) | n | Mia | both | 2 | no | S2C |
| dispatcher.swap_shift | Cleaner proposes to swap a visit with a named colleague | C | msg | write | p | supervisor | n | Mia | both | 2 | no | C2S |
| dispatcher.offer_shifts | Cleaner says they want more hours or can pick up extra visits | C | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| dispatcher.set_availability | Set recurring availability or unavailability (no Tuesdays, only mornings, holiday dates) | C | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| dispatcher.who_is_working | Staffing status: who works where today, is site X covered | S, O | msg | read | p | - | n | Mia | both | 2 | no | C2S |
| dispatcher.reschedule_visit | Office moves a visit to another time or date | S, O | msg | write | n | client notice via client service | n | Mia | both | 2 | no | C2S |
| dispatcher.add_visit | Office adds a one-off visit to the schedule | S, O | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| dispatcher.plan_roster | Build next week's or month's roster from agreements (code plans, supervisor publishes) | S, O | msg, sched | write | p | supervisor publishes | n | Mia | both | 2 | no | C2S |
| dispatcher.route_plan | Order a day's visits into an efficient route | S | msg | read | n | - | n | Mia | both | 3 | no | C2S |
| dispatcher.key_location | Where is the key or access card for a site, who has it | C, S | msg | read | n | - | n | Mia | both | 2 | no | C2S |
| dispatcher.key_handover | Record a key or card given to or returned by someone | C, S | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| dispatcher.lost_key | A key, card or remote for a client site is lost | C, S | msg | external | n | office (client notice) | y | Mia | both | 2 | no | C2S |
| dispatcher.book_vehicle | Ask to use a company car or van for visits | C, S | msg | write | n | supervisor | n | Mia | both | 2 | no | C2S |
| dispatcher.directions | How to get to a site, parking, public transport | C | msg | read | n | - | n | Mia | both | 2 | no | C2S |

## Client service (Customer service)

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| client_service.book_cleaning | Existing client books an extra or one-off cleaning within their agreement or price list | CL | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| client_service.change_booking | Client moves a booked visit to another day or time | CL | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| client_service.cancel_booking | Client cancels one visit (late cancellation fee by code) | CL | msg | write | n | fee: office | n | Mia | both | 2 | no | C2S |
| client_service.pause_service | Client pauses the recurring service for a period (holiday, renovation) | CL | msg | write | n | office | n | Mia | both | 2 | no | C2S |
| client_service.visit_status | Client asks whether or when the cleaner is coming, or whether the visit was done | CL | msg | read | p | - | n | Mia | both | 2 | no | C2S |
| client_service.special_instructions | Client leaves instructions for coming visits (skip a room, extra attention somewhere) | CL | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| client_service.change_access | Client gives new access details (door code, key, alarm, opening hours) | CL | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| client_service.add_extra_task | Client adds a priced extra to a booked visit (oven, windows, fridge) | CL | msg | write | n | - | n | Mia | both | 2 | no | S2C |
| client_service.cleaner_preference | Client asks for the same cleaner, or not to send a particular one | CL | msg | write | p | supervisor | n | Mia | both | 2 | no | C2S |
| client_service.complaint | Client complains about the quality of a visit | CL | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| client_service.request_reclean | Client asks for the job to be redone | CL | msg | write | n | supervisor (free or charged) | n | Mia | both | 2 | no | C2S |
| client_service.damage_claim | Client says the cleaner damaged or broke something and wants compensation | CL | msg | money | p | owner | y | Mia | both | 2 | no | C2S |
| client_service.missing_item | Client says something is missing or was moved after a visit | CL | msg | write | p | owner informed | n | Mia | both | 2 | no | C2S |
| client_service.compliment | Client gives positive feedback about a visit or cleaner | CL | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| client_service.service_faq | General question about the service (products used, insurance, pets, what is included) | CL, L | msg | read | n | - | n | Mia | both | 2 | no | C2S |
| client_service.update_contact | Client changes contact person, phone or email | CL | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| client_service.service_notice | Tell the client about a change (other cleaner, delay, cancelled visit) | - | event | external | p | office | n | Mia | both | 2 | no | C2S |
| client_service.visit_report | Send the client a visit report with checklist and photos | - | event | external | p | - | n | Mia | both | 2 | no | C2S |
| client_service.satisfaction_survey | Ask for a rating after visits | - | sched | external | n | - | n | Mia | both | 3 | no | C2S |

## Sales (Sales)

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sales.new_enquiry | A prospect asks about getting cleaning services (first contact) | L | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| sales.request_quote | Lead or client asks for a price offer for a described scope | L, CL | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| sales.price_question | Quick question about rates or price list, no quote yet | L, CL | msg | read | n | - | n | Mia | both | 2 | no | L2C |
| sales.book_site_survey | Arrange a site visit to measure and scope before quoting | L, O | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| sales.record_survey | Record survey results (areas, rooms, floor types, frequency) | O | msg | write | n | - | n | Mia | both | 2 | no | L2C |
| sales.calculate_quote | Calculate a price for a scope (code calculates) | O | msg | read | n | - | n | Mia | both | 2 | no | L2C |
| sales.send_quote | Send a quote to the lead | O | msg | external | p | owner (prices) | y | Mia | both | 2 | no | L2C |
| sales.quote_follow_up | Follow up quotes with no answer | - | sched | external | p | - | n | Mia | both | 2 | no | L2C |
| sales.lead_status | Lead asks what happened to their quote or enquiry | L | msg | read | p | - | n | Mia | both | 2 | no | L2C |
| sales.accept_quote | Lead accepts the quote and wants to start | L | msg | write | p | owner signs contract | y | Mia | both | 2 | no | L2C |
| sales.negotiate_price | Lead or client asks for a discount or better price | L, CL | msg | money | n | owner | n | Mia | both | 2 | no | L2C |
| sales.decline_quote | Lead says no thanks to the quote | L | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| sales.draft_contract | Draft the service agreement from an accepted quote | O | msg | write | p | owner signs | y | Mia | both | 2 | no | L2C |
| sales.contract_change | Change scope, frequency or price of an existing agreement | CL, O | msg | money | n | owner | y | Mia | both | 2 | no | L2C |
| sales.terminate_contract | Client wants to end the whole service agreement | CL | msg | write | n | owner decides | y | Mia | both | 2 | no | L2C |
| sales.renewal_due | Agreement end date approaching | - | sched | write | n | - | n | Mia | both | 2 | no | L2C |
| sales.index_increase | Annual index price increase per agreement clause (code calculates, notice to client) | - | sched | money | n | owner | y | Mia | both | 2 | no | L2C |
| sales.pipeline | Office asks about open leads, quotes and win rate | O | msg | read | n | - | n | Mia | both | 2 | no | L2C |
| sales.mark_lost | Record a lead as lost, with the reason | O | msg | write | n | - | n | Mia | both | 2 | no | L2C |
| sales.household_deduction | Question about the household tax credit for cleaning (kotitalousvähennys) | L, CL | msg | read | n | - | n | Mia | FI | 2 | no | L2C |
| sales.tender | Prepare a bid for a public or corporate tender (Hilma, PhilGEPS) | O | msg | external | n | owner | y | Mia | both | 3 | no | L2C |

## Marketing assistant (Sales)

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| marketing.draft_post | Draft a social media post | O | msg | write | n | - | n | Mia | both | 3 | no | L2C |
| marketing.publish_post | Publish an approved post | O | msg | external | n | owner | n | Social | both | 3 | no | L2C |
| marketing.campaign | Plan a campaign or special offer | O | msg | money | n | owner | n | Mia | both | 3 | no | L2C |
| marketing.new_review | A new online review arrived | - | event | read | p | - | n | Social | both | 3 | no | L2C |
| marketing.reply_review | Draft a reply to an online review | O | msg | external | p | owner | n | Social | both | 3 | no | L2C |
| marketing.newsletter | Draft an email newsletter to clients who consented | O | msg | external | p | owner | n | Mia | both | 3 | no | L2C |
| marketing.website_update | Change website text, photos or prices | O | msg | external | n | owner | n | Social | both | 3 | no | L2C |
| marketing.referral | Client recommends a friend or asks about the referral bonus | CL | msg | money | p | office | n | Mia | both | 3 | no | L2C |
| marketing.unsubscribe | Stop marketing messages to me | CL, L | msg | write | p | - | y | Mia | both | 2 | no | L2C |
| marketing.results | How campaigns and posts performed | O | msg | read | n | - | n | Mia | both | 3 | no | L2C |

## Recruiter (HR)

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recruiter.draft_job_ad | Draft a job advertisement | O | msg | write | n | - | n | Mia | both | 3 | no | H2R |
| recruiter.publish_job_ad | Publish a job ad on job boards | O | msg | external | n | owner | n | Jobs | both | 3 | no | H2R |
| recruiter.apply | Someone wants to apply for a job or sends a CV | AP | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.job_question | Applicant asks about pay, hours, location or requirements of a job | AP | msg | read | n | - | n | Mia | both | 3 | no | H2R |
| recruiter.application_status | Applicant asks how their application is going | AP | msg | read | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.screening | Ask the screening questions (right to work, availability, licence) after an application | - | event | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.schedule_interview | Arrange a job interview | O, AP | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.reschedule_interview | Applicant asks to move their interview | AP | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.withdraw_application | Applicant withdraws | AP | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.interview_notes | Record interview notes and a score | O | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.make_offer | Draft a job offer | O | msg | external | p | owner | y | Mia | both | 3 | no | H2R |
| recruiter.reject_applicant | Send a rejection | O | msg | external | p | owner | n | Mia | both | 3 | no | H2R |
| recruiter.reference_check | Contact referees, with the applicant's consent | O | msg | external | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.candidates | How many applicants and where they are in the process | O | msg | read | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.retention_purge | Delete applicant data after the retention period | - | sched | delete | p | admin | y | Mia | both | 3 | no | H2R |

## HR and payroll administrator (HR)

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hr.onboard_employee | Start onboarding a new hire (contract, tax card, bank details, IDs, induction) | O | msg | write | sc | owner signs contract | y | Mia | both | 2 | no | H2R |
| hr.submit_document | Employee sends a document (tax card, ID, work permit, certificate, TIN, SSS number) | C | msg | write | sc | - | n | Mia | both | 2 | no | H2R |
| hr.document_expiring | Work permit, ID, hygiene passport or safety card about to expire | - | sched | write | sc | - | n | Mia | both | 2 | no | H2R |
| hr.update_details | Employee changes address, phone, emergency contact or bank account | C | msg | write | p | bank account: office confirms | n | Mia | both | 2 | no | H2R |
| hr.request_time_off | Ask for vacation, unpaid leave or a day off in advance | C | msg | write | p | supervisor | n | Mia | both | 2 | no | H2R |
| hr.time_off_balance | How many holiday or leave days are left | C | msg | read | p | - | n | Payroll | both | 2 | no | H2R |
| hr.sick_note | Send or ask about a sick note or medical certificate | C | msg | write | sc | - | n | Mia | both | 2 | no | H2R |
| hr.family_leave | Maternity, paternity, parental or other family leave | C | msg | write | sc | owner | y | Payroll | both | 3 | no | H2R |
| hr.my_hours | Hours worked in a period, timesheet, overtime | C | msg | read | p | - | n | Mia | both | 2 | no | H2R |
| hr.correct_timesheet | Fix own recorded hours (forgot to check out, wrong times) | C | msg | write | p | supervisor | n | Mia | both | 2 | no | H2R |
| hr.approve_timesheets | Supervisor approves the period's timesheets | S | msg | write | p | SoD: not own hours | n | Mia | both | 2 | no | H2R |
| hr.payslip | Where is my payslip, or why is my pay different | C | msg | read | p | - | n | Payroll | both | 2 | no | H2R |
| hr.payday | When is payday | C | msg | read | n | - | n | Payroll | both | 2 | no | H2R |
| hr.salary_advance | Ask for an advance on salary (cash advance, vale) | C | msg | money | p | owner | n | Payroll | both | 2 | no | H2R |
| hr.prepare_payroll | Export hours, supplements and allowances to payroll at cut-off (code calculates) | - | sched | money | p | SoD: accountant prepares, owner approves | n | Payroll | both | 2 | no | H2R |
| hr.thirteenth_month | 13th-month pay calculation, paid by 24 December | - | sched | money | p | owner | y | Payroll | PH | 2 | no | H2R |
| hr.statutory_contributions | Monthly SSS, PhilHealth and Pag-IBIG reports and remittances | - | sched | external | p | accountant | y | Auth | PH | 2 | no | H2R |
| hr.contribution_question | Employee asks whether SSS, PhilHealth or Pag-IBIG contributions were paid | C | msg | read | p | - | n | Payroll | PH | 2 | no | H2R |
| hr.incomes_register | Report wages to the Incomes Register within five days of payment | - | sched | external | p | accountant | y | Auth | FI | 2 | no | H2R |
| hr.employment_terms | Question on pay rates, supplements, holiday pay or the collective agreement | C | msg | read | n | - | n | Mia | both | 2 | no | H2R |
| hr.employment_certificate | Ask for a certificate of employment | C | msg | write | p | office | y | Mia | both | 2 | no | H2R |
| hr.resign | Employee says they are quitting or gives notice | C | msg | write | p | owner acknowledges | y | Mia | both | 2 | no | H2R |
| hr.terminate_employment | Office wants to end someone's employment | O | msg | write | p | owner decides | y | Mia | both | 3 | no | H2R |
| hr.disciplinary | Warning or disciplinary note for an employee | O | msg | write | p | owner | y | Mia | both | 3 | no | H2R |
| hr.offboard_employee | Offboarding: keys back, access removed, final pay | O | msg | write | p | owner | n | Mia | both | 2 | no | H2R |
| hr.grievance | Confidential complaint about a colleague or supervisor, harassment | C | msg | write | sc | owner only | y | Mia | both | 2 | no | H2R |
| hr.occupational_health | Occupational health care appointment or question | C | msg | read | sc | - | n | Mia | FI | 3 | no | H2R |
| hr.work_injury_claim | Statutory accident insurance or ECC claim after a work injury | O | msg | external | sc | owner | y | Auth | both | 3 | no | H2R |
| hr.training | Sign up for or ask about training (induction, hygiene passport, safety card) | C, O | msg | write | n | - | n | Mia | both | 3 | no | H2R |
| hr.performance_review | Schedule or record a performance review | O | msg | write | p | - | n | Mia | both | 3 | no | H2R |

## Bookkeeper (Finance)

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bookkeeper.invoice_run | Month-end invoicing from completed visits (code calculates; Finvoice, BIR invoice) | - | sched | money | n | SoD: accountant prepares, owner approves | y | Acct | both | 2 | no | S2C |
| bookkeeper.create_invoice | Make a one-off invoice | O, A | msg | money | n | owner | y | Acct | both | 2 | no | S2C |
| bookkeeper.invoice_question | Client asks what an invoice or a line on it is for | CL | msg | read | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.invoice_copy | Client asks for a copy of an invoice or an official receipt | CL | msg | read | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.dispute_invoice | Client says an invoice is wrong and will not pay it as is | CL | msg | write | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.payment_notice | Client says they have paid or sends proof of payment | CL | msg | write | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.payment_received | A bank payment was matched to an invoice | - | event | write | n | - | n | Bank | both | 2 | no | S2C |
| bookkeeper.payment_reminder | Overdue reminders and collection (Interest Act fees, collection agency) | - | sched | external | n | collection: owner | y | Acct | both | 2 | no | S2C |
| bookkeeper.payment_plan | Client asks to pay later or in instalments | CL | msg | money | n | owner | y | Acct | both | 2 | no | S2C |
| bookkeeper.credit_note | Credit all or part of an invoice | O, A | msg | money | n | SoD: preparer is not approver | y | Acct | both | 2 | no | S2C |
| bookkeeper.billing_details | Client changes billing address, e-invoice address, VAT or TIN details | CL | msg | write | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.receivables | Who owes us money, what is overdue | O, A | msg | read | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.expense_claim | Employee claims back money spent for work (receipt) | C | msg | money | p | supervisor | n | Acct | both | 2 | no | P2P |
| bookkeeper.mileage_claim | Employee claims kilometre allowance for driving their own car | C | msg | money | p | supervisor | n | Payroll | both | 2 | no | P2P |
| bookkeeper.supplier_invoice | Supplier invoice received; match to order and delivery | - | event | money | n | SoD: approver is not the orderer | n | Acct | both | 3 | no | P2P |
| bookkeeper.approve_supplier_invoice | Approve or question a supplier invoice | O | msg | money | n | SoD: approver is not the orderer | n | Acct | both | 3 | no | P2P |
| bookkeeper.pay_suppliers | Prepare the supplier payment batch (a person pays in the bank) | - | sched | money | n | owner | n | Bank | both | 3 | no | P2P |
| bookkeeper.withholding_certificate | Client asks for or sends a withholding tax certificate (BIR 2307) | CL | msg | read | n | - | n | Acct | PH | 3 | no | S2C |
| bookkeeper.vat_report | VAT return (OmaVero; BIR 2550Q) through the accounting system | - | sched | external | n | accountant | y | Auth | both | 3 | no | R2R |
| bookkeeper.month_end_close | Reconcile bank, accruals and open items at month end | A | msg, sched | write | n | accountant | n | Acct | both | 3 | no | R2R |
| bookkeeper.cash_position | How much money we have, cash flow outlook | O, A | msg | read | n | - | n | Bank | both | 3 | no | R2R |
| bookkeeper.annual_accounts | Year-end support for the financial statements and tax return | A | msg, sched | external | n | owner signs | y | Acct | both | 3 | no | R2R |

## Purchaser (Operations): supplies, equipment, fleet, subcontractors

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| purchaser.low_supplies | Supplies are running low or out at a site or in the van | C, S | msg | write | n | - | n | Mia | both | 2 | no | P2P |
| purchaser.request_supplies | Ask for specific items or equipment to be ordered | C, S | msg | write | n | supervisor above limit | n | Mia | both | 2 | no | P2P |
| purchaser.purchase_order | Office places an order with a supplier | O | msg | money | n | owner above limit; SoD | y | Acct | both | 3 | no | P2P |
| purchaser.delivery_status | When will an order arrive | C, S, O | msg | read | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.receive_delivery | Record that an order arrived (complete, short, damaged) | S, O | msg | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.stock_level | How much of an item is in stock | S, O | msg | read | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.reorder_alert | Stock below the minimum | - | event | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.broken_equipment | Equipment is broken or not working (vacuum, scrubber, ladder) | C, S | msg | write | n | - | n | Mia | both | 2 | no | P2P |
| purchaser.reserve_equipment | Reserve shared equipment for a job | S | msg | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.equipment_service_due | Equipment maintenance or inspection due | - | sched | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.vehicle_problem | Problem with a company vehicle (breakdown, warning light, accident damage) | C | msg | write | n | - | n | Mia | both | 2 | no | P2P |
| purchaser.vehicle_service_due | Vehicle service, inspection or registration due | - | sched | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.traffic_fine | Parking ticket or traffic fine received for a company vehicle | C | msg | money | p | owner | y | Acct | both | 3 | no | P2P |
| purchaser.add_subcontractor | Add a subcontractor with the required checks (Contractor's Liability Act; DOLE D.O. 174) | O | msg | write | n | owner | y | Mia | both | 3 | no | P2P |
| purchaser.contractor_checks_due | Yearly Contractor's Liability Act documents due again | - | sched | write | n | - | y | Mia | FI | 3 | no | P2P |
| purchaser.order_subcontract | Order a job from a subcontractor (windows, carpets) | O | msg | money | n | owner | y | Mia | both | 3 | no | P2P |
| purchaser.compare_suppliers | Find a better price or another supplier for an item | O | msg | read | n | - | n | Mia | both | 3 | no | P2P |

## Quality (proposed: quality, safety and compliance coordinator)

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| quality.emergency | Someone is in danger or there is an emergency on site now | C | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| quality.report_injury | Staff member was injured or had an accident at work | C, S | msg | write | sc | - | y | Mia | both | 2 | no | C2S |
| quality.report_damage | Staff member damaged or broke something at a site | C | msg | write | n | owner (insurance) | y | Mia | both | 2 | no | C2S |
| quality.report_hazard | Unsafe condition or near miss (needles, slippery floor, aggressive person, faulty wiring) | C | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| quality.chemical_safety | Chemical question, safety data sheet, spill or exposure | C | msg | read | n | - | n | Mia | both | 2 | no | C2S |
| quality.work_instructions | How to clean something, which method or product to use | C | msg | read | n | - | n | Mia | both | 2 | no | C2S |
| quality.site_inspection | Supervisor records a quality inspection of a site (INSTA 800) | S | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| quality.schedule_inspections | Plan quality inspections across sites | - | sched | write | n | - | n | Mia | both | 3 | no | C2S |
| quality.complaint_follow_up | Corrective action after a client complaint | - | event | write | p | supervisor | n | Mia | both | 2 | no | C2S |
| quality.quality_scores | Quality scores and complaints per site, cleaner or period | S, O | msg | read | p | - | n | Mia | both | 3 | no | C2S |
| quality.company_permits_due | Company insurance, permits and registrations due for renewal (business permit, BIR, trade register) | - | sched | write | n | owner | y | Mia | both | 3 | no | R2R |
| quality.privacy_request | Data subject request: see, correct or delete my data (GDPR; Data Privacy Act) | C, CL, L, AP | msg | delete | p | admin | y | Mia | both | 2 | no | Plat |
| quality.data_breach | Possible data breach (lost phone, codes sent to the wrong person) | C, S, O | msg | write | p | owner (72 h notice to authority) | y | Mia | both | 2 | no | Plat |
| quality.audit_trail | Who changed what and when (event log) | O | msg | read | p | - | n | Mia | both | 2 | no | Plat |

## Office (proposed: office manager): master data, administration, management reporting

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| office.add_client | Create a new client record | O | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| office.update_client | Change a client's master data | O | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| office.add_site | Add a site or location to a client | O | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| office.update_site | Change a site's details (address, area, access, checklist) | O, S | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| office.add_employee | Create an employee record | O | msg | write | p | - | n | Mia | both | 2 | no | H2R |
| office.update_employee | Change an employee's role, contract hours, work limits or skills | O | msg | write | p | owner | n | Mia | both | 2 | no | H2R |
| office.archive_record | Archive or delete a client, site or employee record | O | msg | delete | p | admin | n | Mia | both | 2 | no | R2R |
| office.price_list | Change service prices in the price list | O | msg | money | n | owner | n | Mia | both | 2 | no | L2C |
| office.invite_user | Give someone access to Mia | O | msg | write | p | - | n | Mia | both | 1 | no | Plat |
| office.change_role | Change what someone may do in Mia (role, permissions) | O | msg | write | p | owner; SoD: not own role | n | Mia | both | 1 | no | Plat |
| office.remove_access | Remove someone's access to Mia | O | msg | write | p | - | n | Mia | both | 1 | no | Plat |
| office.reset_login | Locked out, forgot PIN or password, new phone | C, S, O | msg | write | p | admin | n | Mia | both | 1 | no | Plat |
| office.pending_approvals | Show approvals waiting for me (decided in the app, never by the agent) | O | msg | read | n | - | n | Mia | both | 1 | part | Plat |
| office.agent_settings | Change an agent's organisation instructions or settings | O | msg | write | n | owner | n | Mia | both | 2 | no | Plat |
| office.branch_settings | Branch settings: opening hours, public holidays, time zone | O | msg | write | n | owner | n | Mia | both | 2 | no | Plat |
| office.system_status | Is Mia working, are backups and channels OK | O | msg | read | n | - | n | Mia | both | 1 | part | Plat |
| office.operations_report | Visits done, hours, absences, cover for a period | O | msg | read | p | - | n | Mia | both | 2 | no | R2R |
| office.absence_report | Sickness absence rate and patterns | O | msg | read | sc | - | n | Mia | both | 2 | no | R2R |
| office.profitability_report | Margin per client, site or service | O | msg | read | n | - | n | Acct | both | 3 | no | R2R |
| office.revenue_report | Sales and revenue for a period, compared | O, A | msg | read | n | - | n | Acct | both | 3 | no | R2R |
| office.headcount_report | Staff numbers, hires, leavers, turnover | O | msg | read | p | - | n | Mia | both | 3 | no | R2R |
| office.weekly_summary | Weekly summary to the owner | - | sched | read | p | - | n | Mia | both | 2 | no | R2R |
| office.export_data | Export a list or report to a spreadsheet | O | msg | read | p | - | n | Mia | both | 2 | no | R2R |
| office.staffing_forecast | How many staff hours next month needs | O | msg | read | n | - | n | Mia | both | 3 | no | R2R |

## Chat (platform, cross-cutting)

| Intent | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chat.greeting | Hello, good morning, small talk opener | all | msg | read | n | - | n | Mia | both | 1 | part | Plat |
| chat.thanks | Thanks, ok great, acknowledgement that closes a topic | all | msg | read | n | - | n | Mia | both | 1 | part | Plat |
| chat.help | What can you do, how does this work | all | msg | read | n | - | n | Mia | both | 1 | no | Plat |
| chat.talk_to_human | Wants a person (supervisor, office, manager) instead of the bot | all | msg | write | n | - | n | Mia | both | 1 | no | Plat |
| chat.change_language | Asks Mia to use another language | all | msg | write | n | - | n | Mia | both | 1 | no | Plat |
| chat.cancel | Stop, never mind, undo what was just asked | all | msg | write | n | - | n | Mia | both | 1 | no | Plat |
| chat.clarify | Did not understand Mia's last message, asks to repeat or explain | all | msg | read | n | - | n | Mia | both | 1 | no | Plat |
| chat.request_status | Did you get my message, what happened to what I asked | all | msg | read | n | - | n | Mia | both | 2 | no | Plat |
| chat.app_feedback | Feedback or complaint about Mia itself | all | msg | write | n | - | n | Mia | both | 2 | no | Plat |
| chat.privacy_question | What happens to my data, who can see my messages | all | msg | read | n | - | n | Mia | both | 1 | no | Plat |
| chat.who_am_i | Which account or role am I using | all | msg | read | p | - | n | Mia | both | 1 | no | Plat |
| chat.link_account | Link this WhatsApp number with a code or invite | C, S, O | msg | write | p | - | n | Mia | both | 1 | yes | Plat |

## Summary

| Agent | Intents | Message-triggered | Built |
| --- | --- | --- | --- |
| dispatcher | 31 | 28 | 6 |
| client_service | 19 | 16 | 0 |
| sales | 21 | 18 | 0 |
| marketing | 10 | 9 | 0 |
| recruiter | 15 | 13 | 0 |
| hr | 30 | 25 | 0 |
| bookkeeper | 22 | 16 | 0 |
| purchaser | 17 | 13 | 0 |
| quality | 14 | 11 | 0 |
| office | 24 | 23 | 0 (2 part) |
| chat | 12 | 12 | 1 (2 part) |
| total | 215 | 184 | 7 |

Every intent also has a hand-off rule when the sender may not use it (for example a cleaner
asking `dispatcher.find_cover` is answered with "permission denied" by the tool, rule 4); the
classifier names the intent, permissions decide.

## Notes

- Country rules behind the FI and PH rows are listed in docs/plan.md ("Country rules to design
  for"). Most rows are `both` with a country variant inside the code (pay supplements, holiday
  rules, invoice format), not a different intent.
- Phase 1 candidates for distilled local classifiers are the high-volume field intents:
  report_absence, absence_scope, my_visits, cover_reply, check_in, check_out, cannot_access_site,
  site_problem, visit_details, low_supplies, broken_equipment.
- Message-triggered intents have 8 to 12 English test messages each in
  node/tests/evals/intents_en.yaml; event and schedule triggers are tested by their code, not by
  classification.
