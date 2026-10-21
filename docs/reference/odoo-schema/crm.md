# Odoo 17.0 module `crm`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 6. Models extended here: 10.

## `calendar.event` (extension)

Adds fields to `calendar.event`, defined in another module. Every field below is added by this module.
Source: `calendar.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `opportunity_id` | Many2one | `crm.lead` |  | yes |  | Opportunity |  |

## `crm.lead`

Table `crm_lead`.
Description: Lead/Opportunity.
Inherits: `mail.thread.cc`, `mail.thread.blacklist`, `mail.thread.phone`, `mail.activity.mixin`, `utm.mixin`, `format.address.mixin`, `mail.tracking.duration.mixin`.
Order: `priority desc, id desc`.
Source: `crm_lead.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Opportunity | compute `_compute_name` |
| `user_id` | Many2one | `res.users` |  | yes | default: (computed) | Salesperson |  |
| `user_company_ids` | Many2many | `res.company` |  | no |  |  | compute `_compute_user_company_ids` |
| `team_id` | Many2one | `crm.team` |  | yes |  | Sales Team | compute `_compute_team_id` |
| `lead_properties` | Properties |  |  | yes |  | Properties |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | compute `_compute_company_id` |
| `referred` | Char |  |  | yes |  | Referred By |  |
| `description` | Html |  |  | yes |  | Notes |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `type` | Selection |  | yes | yes | `lead` Lead, `opportunity` Opportunity; default: (computed) |  |  |
| `priority` | Selection |  |  | yes | `0` Low, `1` Medium, `2` High, `3` Very High; default: (computed) | Priority |  |
| `stage_id` | Many2one | `crm.stage` |  | yes |  | Stage | compute `_compute_stage_id` |
| `kanban_state` | Selection |  |  | no | `grey` No next activity planned, `red` Next activity late, `green` Next activity is planned | Kanban State | compute `_compute_kanban_state` |
| `tag_ids` | Many2many | `crm.tag` (table `crm_tag_rel`) |  | yes |  | Tags |  |
| `color` | Integer |  |  | yes | default: `0` | Color Index |  |
| `expected_revenue` | Monetary |  |  | yes |  | Expected Revenue |  |
| `prorated_revenue` | Monetary |  |  | yes |  | Prorated Revenue | compute `_compute_prorated_revenue` |
| `recurring_revenue` | Monetary |  |  | yes |  | Recurring Revenues |  |
| `recurring_plan` | Many2one | `crm.recurring.plan` |  | yes |  | Recurring Plan |  |
| `recurring_revenue_monthly` | Monetary |  |  | yes |  | Expected MRR | compute `_compute_recurring_revenue_monthly` |
| `recurring_revenue_monthly_prorated` | Monetary |  |  | yes |  | Prorated MRR | compute `_compute_recurring_revenue_monthly_prorated` |
| `recurring_revenue_prorated` | Monetary |  |  | yes |  | Prorated Recurring Revenues | compute `_compute_recurring_revenue_prorated` |
| `company_currency` | Many2one | `res.currency` |  | no |  | Currency | compute `_compute_company_currency` |
| `date_closed` | Datetime |  |  | yes |  | Closed Date |  |
| `date_automation_last` | Datetime |  |  | yes |  | Last Action |  |
| `date_open` | Datetime |  |  | yes |  | Assignment Date | compute `_compute_date_open` |
| `day_open` | Float |  |  | yes |  | Days to Assign | compute `_compute_day_open` |
| `day_close` | Float |  |  | yes |  | Days to Close | compute `_compute_day_close` |
| `date_last_stage_update` | Datetime |  |  | yes |  | Last Stage Update | compute `_compute_date_last_stage_update` |
| `date_conversion` | Datetime |  |  | yes |  | Conversion Date |  |
| `date_deadline` | Date |  |  | yes |  | Expected Closing |  |
| `partner_id` | Many2one | `res.partner` |  | yes |  | Customer |  |
| `partner_is_blacklisted` | Boolean |  |  | no |  | Partner is blacklisted | related `partner_id.is_blacklisted` |
| `contact_name` | Char |  |  | yes |  | Contact Name | compute `_compute_contact_name` |
| `partner_name` | Char |  |  | yes |  | Company Name | compute `_compute_partner_name` |
| `function` | Char |  |  | yes |  | Job Position | compute `_compute_function` |
| `title` | Many2one | `res.partner.title` |  | yes |  | Title | compute `_compute_title` |
| `email_from` | Char |  |  | yes |  | Email | compute `_compute_email_from` |
| `email_normalized` | Char |  |  | yes |  |  |  |
| `email_domain_criterion` | Char |  |  | yes |  | Email Domain Criterion | compute `_compute_email_domain_criterion` |
| `phone` | Char |  |  | yes |  | Phone | compute `_compute_phone` |
| `mobile` | Char |  |  | yes |  | Mobile | compute `_compute_mobile` |
| `phone_sanitized` | Char |  |  | yes |  |  |  |
| `phone_state` | Selection |  |  | yes | `correct` Correct, `incorrect` Incorrect | Phone Quality | compute `_compute_phone_state` |
| `email_state` | Selection |  |  | yes | `correct` Correct, `incorrect` Incorrect | Email Quality | compute `_compute_email_state` |
| `website` | Char |  |  | yes |  | Website | compute `_compute_website` |
| `lang_id` | Many2one | `res.lang` |  | yes |  | Language | compute `_compute_lang_id` |
| `lang_code` | Char |  |  | no |  |  | related `lang_id.code` |
| `lang_active_count` | Integer |  |  | no |  |  | compute `_compute_lang_active_count` |
| `street` | Char |  |  | yes |  | Street | compute `_compute_partner_address_values` |
| `street2` | Char |  |  | yes |  | Street2 | compute `_compute_partner_address_values` |
| `zip` | Char |  |  | yes |  | Zip | compute `_compute_partner_address_values` |
| `city` | Char |  |  | yes |  | City | compute `_compute_partner_address_values` |
| `state_id` | Many2one | `res.country.state` |  | yes |  | State | compute `_compute_partner_address_values` |
| `country_id` | Many2one | `res.country` |  | yes |  | Country | compute `_compute_partner_address_values` |
| `probability` | Float |  |  | yes |  | Probability | compute `_compute_probabilities` |
| `automated_probability` | Float |  |  | yes |  | Automated Probability | compute `_compute_probabilities` |
| `is_automated_probability` | Boolean |  |  | no |  | Is automated probability? | compute `_compute_is_automated_probability` |
| `lost_reason_id` | Many2one | `crm.lost.reason` |  | yes |  | Lost Reason |  |
| `calendar_event_ids` | One2many | `calendar.event` (inverse `opportunity_id`) |  | no (inverse) |  | Meetings |  |
| `duplicate_lead_ids` | Many2many | `crm.lead` |  | no |  | Potential Duplicate Lead | compute `_compute_potential_lead_duplicates` |
| `duplicate_lead_count` | Integer |  |  | no |  | Potential Duplicate Lead Count | compute `_compute_potential_lead_duplicates` |
| `meeting_display_date` | Date |  |  | no |  |  | compute `_compute_meeting_display` |
| `meeting_display_label` | Char |  |  | no |  |  | compute `_compute_meeting_display` |
| `partner_email_update` | Boolean |  |  | no |  | Partner Email will Update | compute `_compute_partner_email_update` |
| `partner_phone_update` | Boolean |  |  | no |  | Partner Phone will Update | compute `_compute_partner_phone_update` |
| `is_partner_visible` | Boolean |  |  | no |  | Is Partner Visible | compute `_compute_is_partner_visible` |
| `campaign_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `medium_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `source_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |

SQL constraints:

- `check_probability`: `check(probability >= 0 and probability <= 100)`

## `crm.lead.scoring.frequency`

Table `crm_lead_scoring_frequency`.
Description: Lead Scoring Frequency.
Source: `crm_lead_scoring_frequency.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `variable` | Char |  |  | yes |  | Variable |  |
| `value` | Char |  |  | yes |  | Value |  |
| `won_count` | Float |  |  | yes |  | Won Count |  |
| `lost_count` | Float |  |  | yes |  | Lost Count |  |
| `team_id` | Many2one | `crm.team` |  | yes |  | Sales Team |  |

## `crm.lead.scoring.frequency.field`

Table `crm_lead_scoring_frequency_field`.
Description: Fields that can be used for predictive lead scoring computation.
Source: `crm_lead_scoring_frequency.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | no |  |  | related `field_id.field_description` |
| `field_id` | Many2one | `ir.model.fields` | yes | yes |  |  |  |

## `crm.lost.reason`

Table `crm_lost_reason`.
Description: Opp. Lost Reason.
Source: `crm_lost_reason.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Description |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `leads_count` | Integer |  |  | no |  | Leads Count | compute `_compute_leads_count` |

## `crm.recurring.plan`

Table `crm_recurring_plan`.
Description: CRM Recurring revenue plans.
Order: `sequence`.
Source: `crm_recurring_plan.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Plan Name |  |
| `number_of_months` | Integer |  | yes | yes |  | # Months |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `sequence` | Integer |  |  | yes | default: `10` | Sequence |  |

SQL constraints:

- `check_number_of_months`: `CHECK(number_of_months >= 0)`

## `crm.stage`

Table `crm_stage`.
Description: CRM Stages.
Order: `sequence, name, id`.
Display name field: `name`.
Source: `crm_stage.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Stage Name |  |
| `sequence` | Integer |  |  | yes | default: `1` | Sequence |  |
| `is_won` | Boolean |  |  | yes |  | Is Won Stage? |  |
| `requirements` | Text |  |  | yes |  | Requirements |  |
| `team_id` | Many2one | `crm.team` |  | yes |  | Sales Team |  |
| `fold` | Boolean |  |  | yes |  | Folded in Pipeline |  |
| `team_count` | Integer |  |  | no |  | team_count | compute `_compute_team_count` |

## `crm.team` (extension)

Adds fields to `crm.team`, defined in another module. Every field below is added by this module.
Description: Sales Team.
Inherits: `mail.alias.mixin`.
Source: `crm_team.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `use_leads` | Boolean |  |  | yes |  | Leads |  |
| `use_opportunities` | Boolean |  |  | yes | default: `True` | Pipeline |  |
| `alias_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `assignment_enabled` | Boolean |  |  | no |  | Lead Assign | compute `_compute_assignment_enabled` |
| `assignment_auto_enabled` | Boolean |  |  | no |  | Auto Assignment | compute `_compute_assignment_enabled` |
| `assignment_optout` | Boolean |  |  | yes |  | Skip auto assignment |  |
| `assignment_max` | Integer |  |  | no |  | Lead Average Capacity | compute `_compute_assignment_max` |
| `assignment_domain` | Char |  |  | yes |  | Assignment Domain |  |
| `lead_unassigned_count` | Integer |  |  | no |  | # Unassigned Leads | compute `_compute_lead_unassigned_count` |
| `lead_all_assigned_month_count` | Integer |  |  | no |  | # Leads/Opps assigned this month | compute `_compute_lead_all_assigned_month_count` |
| `lead_all_assigned_month_exceeded` | Boolean |  |  | no |  | Exceed monthly lead assignement | compute `_compute_lead_all_assigned_month_count` |
| `opportunities_count` | Integer |  |  | no |  | # Opportunities | compute `_compute_opportunities_data` |
| `opportunities_amount` | Monetary |  |  | no |  | Opportunities Revenues | compute `_compute_opportunities_data` |
| `opportunities_overdue_count` | Integer |  |  | no |  | # Overdue Opportunities | compute `_compute_opportunities_overdue_data` |
| `opportunities_overdue_amount` | Monetary |  |  | no |  | Overdue Opportunities Revenues | compute `_compute_opportunities_overdue_data` |
| `lead_properties_definition` | PropertiesDefinition |  |  | yes |  | Lead Properties |  |

## `crm.team.member` (extension)

Adds fields to `crm.team.member`, defined in another module. Every field below is added by this module.
Source: `crm_team_member.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `assignment_enabled` | Boolean |  |  | no |  |  | related `crm_team_id.assignment_enabled` |
| `assignment_domain` | Char |  |  | yes |  | Assignment Domain |  |
| `assignment_optout` | Boolean |  |  | yes |  | Skip auto assignment |  |
| `assignment_max` | Integer |  |  | yes | default: `30` | Average Leads Capacity (on 30 days) |  |
| `lead_month_count` | Integer |  |  | no |  | Leads (30 days) | compute `_compute_lead_month_count` |

## `digest.digest` (extension)

Adds fields to `digest.digest`, defined in another module. Every field below is added by this module.
Source: `digest.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `kpi_crm_lead_created` | Boolean |  |  | yes |  | New Leads |  |
| `kpi_crm_lead_created_value` | Integer |  |  | no |  |  | compute `_compute_kpi_crm_lead_created_value` |
| `kpi_crm_opportunities_won` | Boolean |  |  | yes |  | Opportunities Won |  |
| `kpi_crm_opportunities_won_value` | Integer |  |  | no |  |  | compute `_compute_kpi_crm_opportunities_won_value` |

## `ir.config_parameter` (extension)

Adds fields to `ir.config_parameter`, defined in another module. Every field below is added by this module.
Source: `ir_config_parameter.py`.

## `mail.activity` (extension)

Adds fields to `mail.activity`, defined in another module. Every field below is added by this module.
Source: `mail_activity.py`.

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `group_use_lead` | Boolean |  |  | yes |  | Leads |  |
| `group_use_recurring_revenues` | Boolean |  |  | yes |  | Recurring Revenues |  |
| `is_membership_multi` | Boolean |  |  | yes |  | Multi Teams |  |
| `crm_use_auto_assignment` | Boolean |  |  | yes |  | Rule-Based Assignment |  |
| `crm_auto_assignment_action` | Selection |  |  | yes | `manual` Manually, `auto` Repeatedly | Auto Assignment Action | compute `_compute_crm_auto_assignment_data` |
| `crm_auto_assignment_interval_type` | Selection |  |  | yes | `minutes` Minutes, `hours` Hours, `days` Days, `weeks` Weeks | Auto Assignment Interval Unit | compute `_compute_crm_auto_assignment_data` |
| `crm_auto_assignment_interval_number` | Integer |  |  | yes |  | Repeat every | compute `_compute_crm_auto_assignment_data` |
| `crm_auto_assignment_run_datetime` | Datetime |  |  | yes |  | Auto Assignment Next Execution Date | compute `_compute_crm_auto_assignment_data` |
| `module_crm_iap_mine` | Boolean |  |  | yes |  | Generate new leads based on their country, industries, size, etc. |  |
| `module_crm_iap_enrich` | Boolean |  |  | yes |  | Enrich your leads automatically with company data based on their email address. |  |
| `module_website_crm_iap_reveal` | Boolean |  |  | yes |  | Create Leads/Opportunities from your website's traffic |  |
| `lead_enrich_auto` | Selection |  |  | yes | `manual` Enrich leads on demand only, `auto` Enrich all leads automatically; default: `'auto'` | Enrich lead automatically |  |
| `lead_mining_in_pipeline` | Boolean |  |  | yes |  | Create a lead mining request directly from the opportunity pipeline. |  |
| `predictive_lead_scoring_start_date` | Date |  |  | no |  | Lead Scoring Starting Date | compute `_compute_pls_start_date` |
| `predictive_lead_scoring_start_date_str` | Char |  |  | yes |  | Lead Scoring Starting Date in String |  |
| `predictive_lead_scoring_fields` | Many2many | `crm.lead.scoring.frequency.field` |  | no |  | Lead Scoring Frequency Fields | compute `_compute_pls_fields` |
| `predictive_lead_scoring_fields_str` | Char |  |  | yes |  | Lead Scoring Frequency Fields in String |  |
| `predictive_lead_scoring_field_labels` | Char |  |  | no |  |  | compute `_compute_predictive_lead_scoring_field_labels` |

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `team_id` | Many2one | `crm.team` |  | yes |  | Sales Team | compute `_compute_team_id` |
| `opportunity_ids` | One2many | `crm.lead` (inverse `partner_id`) |  | no (inverse) |  | Opportunities |  |
| `opportunity_count` | Integer |  |  | no |  | Opportunity | compute `_compute_opportunity_count` |

## `res.users` (extension)

Adds fields to `res.users`, defined in another module. Every field below is added by this module.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `target_sales_won` | Integer |  |  | yes |  | Won in Opportunities Target |  |
| `target_sales_done` | Integer |  |  | yes |  | Activities Done Target |  |

## `utm.campaign` (extension)

Adds fields to `utm.campaign`, defined in another module. Every field below is added by this module.
Source: `utm.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `use_leads` | Boolean |  |  | no |  | Use Leads | compute `_compute_use_leads` |
| `crm_lead_count` | Integer |  |  | no |  | Leads/Opportunities count | compute `_compute_crm_lead_count` |
