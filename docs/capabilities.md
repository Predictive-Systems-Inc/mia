# Capabilities and intents of a cleaning company

The master list of what Mia's agents do for a cleaning company, in English (D26: intents are
defined and measured in English first; translation is a separate layer). It is organised by
owning agent, a hired role that mirrors a human job (D16), and every row is tagged with the
end-to-end process it belongs to. docs/plan.md ("Agents, processes and capabilities beyond
Phase 1") explains the model; this file is the list.

The tables are machine-read: node/tests/evals/intents_catalogue.yaml is generated from them
(`uv run python -m tests.evals.intents` from node/; a unit test fails when it is stale) and is
what dataset generators, trainers and the classification eval read. The utterances live in
node/tests/evals/intents.jsonl. Keep one row per intent and the column order below.

## Legend

| Column | Values |
| --- | --- |
| Intent | `agent.intent`, stable snake_case id. `other` is the out-of-scope label (small talk the agent cannot help with, other topics, injection attempts). |
| Label | Short button label (max 20 characters, the user's words) for a clarifying question: "Did you mean: Can't come / late, Can't get in, Something else". Finnish and Filipino labels come later as i18n strings. "-" for intents no message triggers. |
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

Two roles were added to the roster of docs/plan.md by D30 (docs/questions.md Q18): site_manager
(site manager: supports site quality, safety and compliance work and keeps the human supervisor
in charge of decisions; not the human role S) and admin (master data, users and access,
administration, management reporting). There is no chat role: generic conversation (greetings,
thanks, help, a person instead of the bot, language, undo, confusion, feedback on Mia, privacy
questions) is handled by Mia itself for every role through the shared conversation catalogue,
node/mia/learning/catalogue/conversation.yaml, and is not listed here. Its ids
(`conversation.*`) are valid labels in intents.jsonl beside the ids below.

Built today: the dispatcher's six classifier intents (node/mia/agents/dispatcher/classifier.py,
`IntentName`), small talk answered without tools, and WhatsApp account linking by code
(node/mia/channels/linking.py). Everything else is planned.

## Dispatcher (Operations): scheduling, dispatch, field work, keys

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dispatcher.report_absence | Can't come / late | Staff member says they cannot work (sick, other reason), will be late, or must leave early | C, S | msg | write | p (sc if health details) | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.absence_scope | Which shifts I miss | Answer to which visits a just-reported absence covers (whole day, morning, afternoon) | C | msg | write | p | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.my_visits | Show my shifts | Ask about own visits, shifts or schedule; supervisors may ask about someone else's | C, S, O | msg | read | p | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.find_cover | Find cover | Supervisor asks who could take over a visit or shift | S, O | msg | read | p | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.assign | Assign cover | Supervisor names whom to assign as cover after candidates were shown | S, O | msg | write | p | instr.; rule break: admin or owner | n | Mia | both | 1 | yes | C2S |
| dispatcher.cover_reply | Answer cover request | Cleaner accepts or declines a cover request sent to them | C | msg | write | n | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.missed_check_in | - | No check-in some minutes after a visit starts: ask the cleaner, alert the supervisor | - | event | write | p | - | n | Mia | both | 1 | no | C2S |
| dispatcher.unstaffed_visits | - | Daily check for tomorrow's visits without a cleaner | - | sched | read | n | - | n | Mia | both | 1 | no | C2S |
| dispatcher.daily_plan | - | Evening message to each cleaner with tomorrow's visits | - | sched | write | p | - | n | Mia | both | 1 | no | C2S |
| dispatcher.check_in | I've arrived | Cleaner says they arrived at the site (or shares location) | C | msg, event | write | p | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.check_out | I'm done here | Cleaner says the visit is finished and they are leaving | C | msg, event | write | p | - | n | Mia | both | 1 | yes | S2C |
| dispatcher.cannot_access_site | Can't get in | Cleaner is at a site and cannot get in physically (locked door, no key, wrong door code, alarm). Logging in to Mia is admin.reset_login | C | msg | write | n | - | n | Mia | both | 1 | no | C2S |
| dispatcher.site_problem | Problem at the site | Site conditions stop or change the work (no water or power, renovation, event, client still there) | C | msg | write | n | - | n | Mia | both | 1 | no | C2S |
| dispatcher.visit_details | Job details | Ask practical details of a visit: address, door code, where things are, special instructions | C | msg | read | p | - | n | Mia | both | 1 | yes | C2S |
| dispatcher.checklist | My checklist | Ask for or tick off the visit checklist | C | msg | write | n | - | n | Mia | both | 1 | no | C2S |
| dispatcher.send_photos | Send photos | Send before or after photos as proof of work | C | msg | write | p | - | n | Mia | both | 1 | no | C2S |
| dispatcher.extra_time | Need more time | Ask to stay longer than planned to finish the job | C | msg | write | n | supervisor | n | Mia | both | 2 | no | S2C |
| dispatcher.extra_work_on_site | Client wants extra | Client on site asked the cleaner for extra work not in the order | C | msg | write | n | supervisor (priced by code) | n | Mia | both | 2 | no | S2C |
| dispatcher.swap_shift | Swap a shift | Cleaner proposes to swap a visit with a named colleague | C | msg | write | p | supervisor | n | Mia | both | 2 | no | C2S |
| dispatcher.offer_shifts | I want more shifts | Cleaner says they want more hours or can pick up extra visits | C | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| dispatcher.set_availability | Set when I can work | Set recurring availability or unavailability (no Tuesdays, only mornings, holiday dates) | C | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| dispatcher.who_is_working | Who's working | Staffing status: who works where today, is site X covered | S, O | msg | read | p | - | n | Mia | both | 2 | no | C2S |
| dispatcher.reschedule_visit | Move a visit | Office moves a visit to another time or date | S, O | msg | write | n | client notice via client service | n | Mia | both | 2 | no | C2S |
| dispatcher.add_visit | Add a visit | Office adds a one-off visit to the schedule | S, O | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| dispatcher.plan_roster | Plan the roster | Build next week's or month's roster from agreements (code plans, supervisor publishes) | S, O | msg, sched | write | p | supervisor publishes | n | Mia | both | 2 | no | C2S |
| dispatcher.route_plan | Plan the route | Order a day's visits into an efficient route | S | msg | read | n | - | n | Mia | both | 3 | no | C2S |
| dispatcher.key_location | Where's the key | Where is the key or access card for a site, who has it | C, S | msg | read | n | - | n | Mia | both | 2 | no | C2S |
| dispatcher.key_handover | Key handed over | Record a key or card given to or returned by someone | C, S | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| dispatcher.lost_key | Lost a key | A physical key, card or remote for a client site is lost. A lost phone, codes or documents with data is site_manager.data_breach | C, S | msg | external | n | office (client notice) | y | Mia | both | 2 | no | C2S |
| dispatcher.book_vehicle | Book the van | Ask to use a company car or van for visits | C, S | msg | write | n | supervisor | n | Mia | both | 2 | no | C2S |
| dispatcher.directions | How to get there | How to get to a company site or visit, parking, public transport there. Directions anywhere else are conversation.oos_directions_transport | C | msg | read | n | - | n | Mia | both | 2 | no | C2S |

## Client service (Customer service)

Compliments, service questions and general insurance questions go to the shared conversation
catalogue (conversation.thanks, kb_services, kb_eco_products, kb_pets, kb_insurance_damages;
D30, D31). Contact and access changes are admin.update_client and admin.update_site; damage claims are
site_manager.report_damage. Client service owns the follow-up with the client.

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| client_service.book_cleaning | Book a cleaning | Existing client books an extra or one-off cleaning within their agreement or price list | CL | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| client_service.change_booking | Change a booking | Client moves a booked visit to another day or time | CL | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| client_service.cancel_booking | Cancel a visit | Client cancels one visit (late cancellation fee by code) | CL | msg | write | n | fee: office | n | Mia | both | 2 | no | C2S |
| client_service.pause_service | Pause cleaning | Client pauses the recurring service for a period (holiday, renovation) | CL | msg | write | n | office | n | Mia | both | 2 | no | C2S |
| client_service.visit_status | Is cleaner coming | Client asks whether or when the cleaner is coming, or whether the visit was done | CL | msg | read | p | - | n | Mia | both | 2 | no | C2S |
| client_service.special_instructions | Leave instructions | Client leaves instructions for coming visits (skip a room, extra attention somewhere) | CL | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| client_service.add_extra_task | Add an extra task | Client adds a priced extra to a booked visit (oven, windows, fridge) | CL | msg | write | n | - | n | Mia | both | 2 | no | S2C |
| client_service.cleaner_preference | Choose my cleaner | Client asks for the same cleaner, or not to send a particular one | CL | msg | write | p | supervisor | n | Mia | both | 2 | no | C2S |
| client_service.complaint | Make a complaint | Client complains about the quality of a visit | CL | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| client_service.request_reclean | Redo the cleaning | Client asks for the job to be redone | CL | msg | write | n | supervisor (free or charged) | n | Mia | both | 2 | no | C2S |
| client_service.missing_item | Something's missing | Client says something is missing or was moved after a visit | CL | msg | write | p | owner informed | n | Mia | both | 2 | no | C2S |
| client_service.service_notice | - | Tell the client about a change (other cleaner, delay, cancelled visit) | - | event | external | p | office | n | Mia | both | 2 | no | C2S |
| client_service.visit_report | - | Send the client a visit report with checklist and photos | - | event | external | p | - | n | Mia | both | 2 | no | C2S |
| client_service.satisfaction_survey | - | Ask for a rating after visits | - | sched | external | n | - | n | Mia | both | 3 | no | C2S |

## Sales (Sales)

General price and household deduction questions are conversation.kb_prices and
conversation.kb_household_tax_deduction (D30); sales owns quotes.

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sales.new_enquiry | Get cleaning service | A prospect asks about getting cleaning services (first contact) | L | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| sales.request_quote | Get a quote | Lead or client asks for a price offer for a described scope | L, CL | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| sales.book_site_survey | Book a site visit | Arrange a site visit to measure and scope before quoting | L, O | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| sales.record_survey | Save survey results | Record survey results (areas, rooms, floor types, frequency) | O | msg | write | n | - | n | Mia | both | 2 | no | L2C |
| sales.calculate_quote | Work out a price | Calculate a price for a scope (code calculates) | O | msg | read | n | - | n | Mia | both | 2 | no | L2C |
| sales.send_quote | Send a quote | Send a quote to the lead | O | msg | external | p | owner (prices) | y | Mia | both | 2 | no | L2C |
| sales.quote_follow_up | - | Follow up quotes with no answer | - | sched | external | p | - | n | Mia | both | 2 | no | L2C |
| sales.lead_status | My quote status | Lead asks what happened to their quote or enquiry | L | msg | read | p | - | n | Mia | both | 2 | no | L2C |
| sales.accept_quote | Accept the quote | Lead accepts the quote and wants to start | L | msg | write | p | owner signs contract | y | Mia | both | 2 | no | L2C |
| sales.negotiate_price | Ask for a discount | Lead or client asks for a discount or better price | L, CL | msg | money | n | owner | n | Mia | both | 2 | no | L2C |
| sales.decline_quote | Decline the quote | Lead says no thanks to the quote | L | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| sales.draft_contract | Draft a contract | Draft the service agreement from an accepted quote | O | msg | write | p | owner signs | y | Mia | both | 2 | no | L2C |
| sales.contract_change | Change my contract | Change scope, frequency or price of an existing agreement | CL, O | msg | money | n | owner | y | Mia | both | 2 | no | L2C |
| sales.terminate_contract | End my contract | Client wants to end the whole service agreement | CL | msg | write | n | owner decides | y | Mia | both | 2 | no | L2C |
| sales.renewal_due | - | Agreement end date approaching | - | sched | write | n | - | n | Mia | both | 2 | no | L2C |
| sales.index_increase | - | Annual index price increase per agreement clause (code calculates, notice to client) | - | sched | money | n | owner | y | Mia | both | 2 | no | L2C |
| sales.pipeline | Sales pipeline | Office asks about open leads, quotes and win rate | O | msg | read | n | - | n | Mia | both | 2 | no | L2C |
| sales.mark_lost | Mark lead lost | Record a lead as lost, with the reason | O | msg | write | n | - | n | Mia | both | 2 | no | L2C |
| sales.tender | Prepare a tender | Prepare a bid for a public or corporate tender (Hilma, PhilGEPS) | O | msg | external | n | owner | y | Mia | both | 3 | no | L2C |

## Marketing assistant (Sales)

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| marketing.draft_post | Write a post | Draft a social media post | O | msg | write | n | - | n | Mia | both | 3 | no | L2C |
| marketing.publish_post | Publish a post | Publish an approved marketing post (offers, news, before and after photos). A job vacancy is recruiter.publish_job_ad | O | msg | external | n | owner | n | Social | both | 3 | no | L2C |
| marketing.campaign | Plan a campaign | Plan a campaign or special offer | O | msg | money | n | owner | n | Mia | both | 3 | no | L2C |
| marketing.new_review | - | A new online review arrived | - | event | read | p | - | n | Social | both | 3 | no | L2C |
| marketing.reply_review | Reply to a review | Draft a reply to an online review | O | msg | external | p | owner | n | Social | both | 3 | no | L2C |
| marketing.newsletter | Write a newsletter | Draft an email newsletter to clients who consented | O | msg | external | p | owner | n | Mia | both | 3 | no | L2C |
| marketing.website_update | Update the website | Change website text, photos or prices | O | msg | external | n | owner | n | Social | both | 3 | no | L2C |
| marketing.referral | Refer a friend | Client recommends a friend or asks about the referral bonus | CL | msg | money | p | office | n | Mia | both | 3 | no | L2C |
| marketing.unsubscribe | Stop marketing | Stop marketing messages to me | CL, L | msg | write | p | - | y | Mia | both | 2 | no | L2C |
| marketing.results | Marketing results | How campaigns and posts performed | O | msg | read | n | - | n | Mia | both | 3 | no | L2C |

## Recruiter (HR)

Questions about working here are conversation.kb_jobs (D30); the recruiter owns applications.

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recruiter.draft_job_ad | Write a job ad | Draft a job advertisement | O | msg | write | n | - | n | Mia | both | 3 | no | H2R |
| recruiter.publish_job_ad | Publish a job ad | Publish a job vacancy (ad or hiring post) on job boards, the website or social media | O | msg | external | n | owner | n | Jobs | both | 3 | no | H2R |
| recruiter.apply | Apply for a job | Someone applies for a job: says they want to apply, sends a CV or application. Questions about working here are conversation.kb_jobs | AP | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.application_status | My application | Applicant asks how their application is going | AP | msg | read | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.screening | - | Ask the screening questions (right to work, availability, licence) after an application | - | event | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.schedule_interview | Book an interview | Arrange a job interview | O, AP | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.reschedule_interview | Move my interview | Applicant asks to move their interview | AP | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.withdraw_application | Withdraw application | Applicant withdraws | AP | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.interview_notes | Interview notes | Record interview notes and a score | O | msg | write | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.make_offer | Make a job offer | Draft a job offer | O | msg | external | p | owner | y | Mia | both | 3 | no | H2R |
| recruiter.reject_applicant | Reject applicant | Send a rejection | O | msg | external | p | owner | n | Mia | both | 3 | no | H2R |
| recruiter.reference_check | Check references | Contact referees, with the applicant's consent | O | msg | external | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.candidates | See applicants | How many applicants and where they are in the process | O | msg | read | p | - | n | Mia | both | 3 | no | H2R |
| recruiter.retention_purge | - | Delete applicant data after the retention period | - | sched | delete | p | admin | y | Mia | both | 3 | no | H2R |

## HR and payroll administrator (HR)

Questions on payday, employment terms, training and sick leave rules are conversation.kb_payday,
kb_employment_terms, kb_training and kb_sick_leave_rules; harassment reports are
conversation.harassment_report (D30). HR owns the follow-up.

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hr.onboard_employee | Onboard new hire | Start onboarding a new hire (contract, tax card, bank details, IDs, induction) | O | msg | write | sc | owner signs contract | y | Mia | both | 2 | no | H2R |
| hr.submit_document | Send a document | Employee sends a document (tax card, ID, work permit, certificate, TIN, SSS number) | C | msg | write | sc | - | n | Mia | both | 2 | no | H2R |
| hr.document_expiring | - | Work permit, ID, hygiene passport or safety card about to expire | - | sched | write | sc | - | n | Mia | both | 2 | no | H2R |
| hr.update_details | Update my details | Employee changes address, phone, emergency contact or bank account | C | msg | write | p | bank account: office confirms | n | Mia | both | 2 | no | H2R |
| hr.request_time_off | Ask for time off | Ask for vacation, unpaid leave or a day off in advance | C | msg | write | p | supervisor | n | Mia | both | 2 | no | H2R |
| hr.time_off_balance | Holiday days left | How many holiday or leave days are left | C | msg | read | p | - | n | Payroll | both | 2 | no | H2R |
| hr.sick_note | Sick note | Send a sick note or medical certificate, or ask about one already sent. Rules on certificates are conversation.kb_sick_leave_rules | C | msg | write | sc | - | n | Mia | both | 2 | no | H2R |
| hr.family_leave | Family leave | Maternity, paternity, parental or other family leave | C | msg | write | sc | owner | y | Payroll | both | 3 | no | H2R |
| hr.my_hours | My hours | Hours worked in a period, timesheet, overtime | C | msg | read | p | - | n | Mia | both | 2 | no | H2R |
| hr.correct_timesheet | Fix my hours | Fix own recorded hours (forgot to check out, wrong times) | C | msg | write | p | supervisor | n | Mia | both | 2 | no | H2R |
| hr.approve_timesheets | Approve timesheets | Supervisor approves the period's timesheets | S | msg | write | p | SoD: not own hours | n | Mia | both | 2 | no | H2R |
| hr.payslip | My payslip | Where is my payslip, or why is my pay different | C | msg | read | p | - | n | Payroll | both | 2 | no | H2R |
| hr.salary_advance | Salary advance | Ask for an advance on salary (cash advance, vale) | C | msg | money | p | owner | n | Payroll | both | 2 | no | H2R |
| hr.prepare_payroll | - | Export hours, supplements and allowances to payroll at cut-off (code calculates) | - | sched | money | p | SoD: accountant prepares, owner approves | n | Payroll | both | 2 | no | H2R |
| hr.thirteenth_month | - | 13th-month pay calculation, paid by 24 December | - | sched | money | p | owner | y | Payroll | PH | 2 | no | H2R |
| hr.statutory_contributions | - | Monthly SSS, PhilHealth and Pag-IBIG reports and remittances | - | sched | external | p | accountant | y | Auth | PH | 2 | no | H2R |
| hr.contribution_question | My contributions | Employee asks whether SSS, PhilHealth or Pag-IBIG contributions were paid | C | msg | read | p | - | n | Payroll | PH | 2 | no | H2R |
| hr.incomes_register | - | Report wages to the Incomes Register within five days of payment | - | sched | external | p | accountant | y | Auth | FI | 2 | no | H2R |
| hr.employment_certificate | Work certificate | Ask for a certificate of employment | C | msg | write | p | office | y | Mia | both | 2 | no | H2R |
| hr.resign | I want to quit | Employee says they are quitting or gives notice | C | msg | write | p | owner acknowledges | y | Mia | both | 2 | no | H2R |
| hr.terminate_employment | End employment | Office wants to end someone's employment | O | msg | write | p | owner decides | y | Mia | both | 3 | no | H2R |
| hr.disciplinary | Give a warning | Warning or disciplinary note for an employee | O | msg | write | p | owner | y | Mia | both | 3 | no | H2R |
| hr.workplace_complaint | Raise a complaint | Employee raises a workplace complaint that is not harassment (unfair treatment, workload, conflict with a colleague, fair scheduling). Harassment is conversation.harassment_report; questions about rules are conversation.kb_* | C | msg | write | p | owner only | n | Mia | both | 2 | no | H2R |
| hr.offboard_employee | Offboard someone | Run the whole leaver process for a named person (keys back, access removed, final pay, exit checklist). Only the record is admin.archive_record; only Mia access is admin.remove_access | O | msg | write | p | owner | n | Mia | both | 2 | no | H2R |
| hr.occupational_health | Occupational health | Occupational health care appointment or question | C | msg | read | sc | - | n | Mia | FI | 3 | no | H2R |
| hr.work_injury_claim | Injury claim | Statutory accident insurance or ECC claim after a work injury | O | msg | external | sc | owner | y | Auth | both | 3 | no | H2R |
| hr.training | Training | Enrol someone in training or check who needs it (induction, hygiene passport, safety card). Questions about courses are conversation.kb_training | C, S, O | msg | write | n | - | n | Mia | both | 3 | no | H2R |
| hr.performance_review | Performance review | Schedule or record a performance review | O | msg | write | p | - | n | Mia | both | 3 | no | H2R |

## Bookkeeper (Finance)

Billing detail changes are admin.update_client (D30).

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bookkeeper.invoice_run | - | Month-end invoicing from completed visits (code calculates; Finvoice, BIR invoice) | - | sched | money | n | SoD: accountant prepares, owner approves | y | Acct | both | 2 | no | S2C |
| bookkeeper.create_invoice | Make an invoice | Make a one-off invoice | O, A | msg | money | n | owner | y | Acct | both | 2 | no | S2C |
| bookkeeper.invoice_question | Question on invoice | Client asks what an invoice or a line on it is for | CL | msg | read | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.invoice_copy | Invoice copy | Client asks for a copy of an invoice or an official receipt | CL | msg | read | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.dispute_invoice | Invoice is wrong | Client says an invoice is wrong and will not pay it as is | CL | msg | write | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.payment_notice | I've paid | Client says they have paid or sends proof of payment | CL | msg | write | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.payment_received | - | A bank payment was matched to an invoice | - | event | write | n | - | n | Bank | both | 2 | no | S2C |
| bookkeeper.payment_reminder | - | Overdue reminders and collection (Interest Act fees, collection agency) | - | sched | external | n | collection: owner | y | Acct | both | 2 | no | S2C |
| bookkeeper.payment_plan | Pay later | Client asks to pay later or in instalments | CL | msg | money | n | owner | y | Acct | both | 2 | no | S2C |
| bookkeeper.credit_note | Make a credit note | Credit all or part of an invoice | O, A | msg | money | n | SoD: preparer is not approver | y | Acct | both | 2 | no | S2C |
| bookkeeper.receivables | Who owes us | Who owes us money, what is overdue | O, A | msg | read | n | - | n | Acct | both | 2 | no | S2C |
| bookkeeper.expense_claim | Claim an expense | Employee claims back a specific amount spent for work (receipt). Questions about the rules are conversation.kb_expenses_travel | C | msg | money | p | supervisor | n | Acct | both | 2 | no | P2P |
| bookkeeper.mileage_claim | Claim mileage | Employee claims kilometres driven with their own vehicle. Questions about rates and rules are conversation.kb_expenses_travel | C | msg | money | p | supervisor | n | Payroll | both | 2 | no | P2P |
| bookkeeper.supplier_invoice | - | Supplier invoice received; match to order and delivery | - | event | money | n | SoD: approver is not the orderer | n | Acct | both | 3 | no | P2P |
| bookkeeper.approve_supplier_invoice | Approve a bill | Approve or question a supplier invoice | O | msg | money | n | SoD: approver is not the orderer | n | Acct | both | 3 | no | P2P |
| bookkeeper.pay_suppliers | - | Prepare the supplier payment batch (a person pays in the bank) | - | sched | money | n | owner | n | Bank | both | 3 | no | P2P |
| bookkeeper.withholding_certificate | Tax certificate | Client asks for or sends a withholding tax certificate (BIR 2307) | CL | msg | read | n | - | n | Acct | PH | 3 | no | S2C |
| bookkeeper.household_deduction_statement | Tax credit statement | Client asks for the yearly labour-cost statement of their invoices for the household tax deduction (kotitalousvähennys). How the deduction works is conversation.kb_household_tax_deduction | CL | msg | read | p | - | n | Acct | FI | 2 | no | S2C |
| bookkeeper.vat_report | - | VAT return (OmaVero; BIR 2550Q) through the accounting system | - | sched | external | n | accountant | y | Auth | both | 3 | no | R2R |
| bookkeeper.month_end_close | Close the month | Reconcile bank, accruals and open items at month end | A | msg, sched | write | n | accountant | n | Acct | both | 3 | no | R2R |
| bookkeeper.cash_position | Cash position | How much money we have, cash flow outlook | O, A | msg | read | n | - | n | Bank | both | 3 | no | R2R |
| bookkeeper.annual_accounts | Year-end accounts | Year-end support for the financial statements and tax return | A | msg, sched | external | n | owner signs | y | Acct | both | 3 | no | R2R |

## Purchaser (Operations): supplies, equipment, fleet, subcontractors

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| purchaser.low_supplies | Supplies running low | Supplies are running low or out at a site or in the van | C, S | msg | write | n | - | n | Mia | both | 2 | no | P2P |
| purchaser.request_supplies | Order supplies | Ask for specific items or equipment to be ordered | C, S | msg | write | n | supervisor above limit | n | Mia | both | 2 | no | P2P |
| purchaser.purchase_order | Place an order | Office places an order with a supplier | O | msg | money | n | owner above limit; SoD | y | Acct | both | 3 | no | P2P |
| purchaser.delivery_status | Where's my order | When will an order arrive | C, S, O | msg | read | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.receive_delivery | Delivery arrived | Record that an order arrived (complete, short, damaged) | S, O | msg | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.stock_level | Check stock | How much of an item is in stock | S, O | msg | read | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.reorder_alert | - | Stock below the minimum | - | event | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.broken_equipment | Equipment broken | Equipment is broken or not working (vacuum, scrubber, trolley) and is not dangerous now. Equipment that is dangerous now (sparks, smoke, hot water leak, unsafe ladder) is conversation.hazard_report | C, S | msg | write | n | - | n | Mia | both | 2 | no | P2P |
| purchaser.reserve_equipment | Reserve equipment | Reserve shared equipment for a job | S | msg | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.equipment_service_due | - | Equipment maintenance or inspection due | - | sched | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.vehicle_problem | Car or van problem | Problem with a company vehicle (breakdown, warning light, accident damage) | C | msg | write | n | - | n | Mia | both | 2 | no | P2P |
| purchaser.vehicle_service_due | - | Vehicle service, inspection or registration due | - | sched | write | n | - | n | Mia | both | 3 | no | P2P |
| purchaser.traffic_fine | Got a fine | Parking ticket or traffic fine received for a company vehicle | C | msg | money | p | owner | y | Acct | both | 3 | no | P2P |
| purchaser.add_subcontractor | Add subcontractor | Add a subcontractor with the required checks (Contractor's Liability Act; DOLE D.O. 174) | O | msg | write | n | owner | y | Mia | both | 3 | no | P2P |
| purchaser.contractor_checks_due | - | Yearly Contractor's Liability Act documents due again | - | sched | write | n | - | y | Mia | FI | 3 | no | P2P |
| purchaser.order_subcontract | Hire subcontractor | Order a job from a subcontractor (windows, carpets) | O | msg | money | n | owner | y | Mia | both | 3 | no | P2P |
| purchaser.compare_suppliers | Compare suppliers | Find a better price or another supplier for an item | O | msg | read | n | - | n | Mia | both | 3 | no | P2P |

## Site manager: site quality, safety and compliance (supports the supervisor)

First contact for emergencies, threats, injuries, chemical exposure, hazards, chemical and cleaning
questions and data subject requests is handled by Mia through the shared conversation catalogue
(conversation.emergency, injury_minor, chemical_exposure, hazard_report, kb_safety_data_sheet,
kb_cleaning_howto, privacy_rights_request; D30, D31); the site manager owns the follow-up.

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| site_manager.report_injury | I got hurt | A supervisor or the office reports that a staff member was injured at work (accident record, insurance). The injured person's own message is conversation.injury_minor or conversation.emergency | S, O | msg | write | sc | - | y | Mia | both | 2 | no | C2S |
| site_manager.report_damage | I broke something | Property at a site was damaged or broken, reported by the staff member or claimed by the client (compensation follows). General insurance questions are conversation.kb_insurance_damages | C, CL | msg | write | n | owner (insurance) | y | Mia | both | 2 | no | C2S |
| site_manager.site_inspection | Site inspection | Supervisor records a quality inspection of a site (INSTA 800) | S | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| site_manager.schedule_inspections | - | Plan quality inspections across sites | - | sched | write | n | - | n | Mia | both | 3 | no | C2S |
| site_manager.complaint_follow_up | - | Corrective action after a client complaint | - | event | write | p | supervisor | n | Mia | both | 2 | no | C2S |
| site_manager.quality_scores | Quality scores | Quality scores and complaints per site, cleaner or period | S, O | msg | read | p | - | n | Mia | both | 3 | no | C2S |
| site_manager.company_permits_due | - | Company insurance, permits and registrations due for renewal (business permit, BIR, trade register) | - | sched | write | n | owner | y | Mia | both | 3 | no | R2R |
| site_manager.data_breach | Data leak | Possible data breach: lost or stolen phone or papers with data, codes or personal data sent to the wrong person. A lost physical key alone is dispatcher.lost_key | C, S, O | msg | write | p | owner (72 h notice to authority) | y | Mia | both | 2 | no | Plat |
| site_manager.audit_trail | Who changed what | Who changed what and when (event log) | O | msg | read | p | - | n | Mia | both | 2 | no | Plat |

## Admin: master data, users and access, administration, management reporting

| Intent | Label | Meaning | Who | Trig | Risk | Sens | Approval / SoD | Legal | SoR | Ctry | Ph | Built | Proc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| admin.add_client | Add a client | Create a new client record | O | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| admin.update_client | Edit a client | Change a client's master data: name, contact persons, phone, email, address and billing details (invoice address, e-invoice, VAT or TIN, references), from the client or the office | CL, O | msg | write | p | - | n | Mia | both | 2 | no | L2C |
| admin.add_site | Add a site | Add a site or location to a client | O | msg | write | n | - | n | Mia | both | 2 | no | C2S |
| admin.update_site | Edit a site | Change a site's details: address, area, access (door codes, keys, alarm, opening hours), checklist, from the client, supervisor or office | CL, S, O | msg | write | p | - | n | Mia | both | 2 | no | C2S |
| admin.add_employee | Add an employee | Create an employee record | O | msg | write | p | - | n | Mia | both | 2 | no | H2R |
| admin.update_employee | Edit an employee | Change an employee's role, contract hours, work limits or skills | O | msg | write | p | owner | n | Mia | both | 2 | no | H2R |
| admin.archive_record | Archive a record | Archive or delete one client, site or employee record. Starting the whole leaver process is hr.offboard_employee | O | msg | delete | p | admin | n | Mia | both | 2 | no | R2R |
| admin.price_list | Change prices | Change service prices in the price list | O | msg | money | n | owner | n | Mia | both | 2 | no | L2C |
| admin.invite_user | Invite to Mia | Give someone access to Mia | O | msg | write | p | - | n | Mia | both | 1 | no | Plat |
| admin.change_role | Change access | Change what someone may do in Mia (role, permissions) | O | msg | write | p | owner; SoD: not own role | n | Mia | both | 1 | no | Plat |
| admin.remove_access | Remove access | Remove someone's access to Mia, nothing else | O | msg | write | p | - | n | Mia | both | 1 | no | Plat |
| admin.reset_login | Can't log in | Cannot log in to Mia: locked out of the app, forgot PIN or password, new phone or SIM. A locked site door is dispatcher.cannot_access_site | C, S, O | msg | write | p | admin | n | Mia | both | 1 | no | Plat |
| admin.pending_approvals | My approvals | Show approvals waiting for me (decided in the app, never by the agent) | O | msg | read | n | - | n | Mia | both | 1 | part | Plat |
| admin.agent_settings | Agent settings | Change an agent's organisation instructions or settings | O | msg | write | n | owner | n | Mia | both | 2 | no | Plat |
| admin.branch_settings | Branch settings | Branch settings: opening hours, public holidays, time zone | O | msg | write | n | owner | n | Mia | both | 2 | no | Plat |
| admin.system_status | Is Mia OK | Is Mia working, are backups and channels OK | O | msg | read | n | - | n | Mia | both | 1 | part | Plat |
| admin.operations_report | Operations report | Visits done, hours, absences, cover for a period | O | msg | read | p | - | n | Mia | both | 2 | no | R2R |
| admin.absence_report | Absence report | Sickness absence rate and patterns | O | msg | read | sc | - | n | Mia | both | 2 | no | R2R |
| admin.profitability_report | Profit report | Margin per client, site or service | O | msg | read | n | - | n | Acct | both | 3 | no | R2R |
| admin.revenue_report | Revenue report | Sales and revenue for a period, compared | O, A | msg | read | n | - | n | Acct | both | 3 | no | R2R |
| admin.headcount_report | Staff report | Staff numbers, hires, leavers, turnover | O | msg | read | p | - | n | Mia | both | 3 | no | R2R |
| admin.weekly_summary | - | Weekly summary to the owner | - | sched | read | p | - | n | Mia | both | 2 | no | R2R |
| admin.export_data | Export to Excel | Export a list or report to a spreadsheet | O | msg | read | p | - | n | Mia | both | 2 | no | R2R |
| admin.staffing_forecast | Staffing forecast | How many staff hours next month needs | O | msg | read | n | - | n | Mia | both | 3 | no | R2R |
| admin.who_am_i | My account | Which account or role am I using | all | msg | read | p | - | n | Mia | both | 1 | no | Plat |
| admin.link_account | Link WhatsApp | Link this WhatsApp number with a code or invite | C, S, O | msg | write | p | - | n | Mia | both | 1 | yes | Plat |

## Summary

| Agent | Intents | Message-triggered | Built |
| --- | --- | --- | --- |
| dispatcher | 31 | 28 | 6 |
| client_service | 14 | 11 | 0 |
| sales | 19 | 16 | 0 |
| marketing | 10 | 9 | 0 |
| recruiter | 14 | 12 | 0 |
| hr | 28 | 23 | 0 |
| bookkeeper | 22 | 16 | 0 |
| purchaser | 17 | 13 | 0 |
| site_manager | 9 | 6 | 0 |
| admin | 26 | 25 | 1 (2 part) |
| total | 190 | 159 | 7 (2 part) |

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
- Message-triggered intents have at least 15 English utterances each (more for the high-volume
  ones), plus hard negatives, out-of-scope messages and injection attempts, in
  node/tests/evals/intents.jsonl: one record per utterance (id, intent, lang, text, role, style,
  slots, negative_of, split, and kind for injections), so Finnish and Filipino records can be
  appended later. Event and schedule triggers are tested by their code, not by classification.
