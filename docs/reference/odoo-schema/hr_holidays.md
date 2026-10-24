# Odoo 17.0 module `hr_holidays`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 6. Models extended here: 9.

## `hr.department` (extension)

Adds fields to `hr.department`, defined in another module. Every field below is added by this module.
Source: `hr_department.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `absence_of_today` | Integer |  |  | no |  | Absence by Today | compute `_compute_leave_count` |
| `leave_to_approve_count` | Integer |  |  | no |  | Time Off to Approve | compute `_compute_leave_count` |
| `allocation_to_approve_count` | Integer |  |  | no |  | Allocation to Approve | compute `_compute_leave_count` |

## `hr.employee` (extension)

Adds fields to `hr.employee`, defined in another module. Every field below is added by this module.
Source: `hr_employee.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `current_leave_id` | Many2one | `hr.leave.type` |  | no |  | Current Time Off Type | compute `_compute_current_leave` |

## `hr.employee.base` (extension)

Adds fields to `hr.employee.base`, defined in another module. Every field below is added by this module.
Source: `hr_employee_base.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `leave_manager_id` | Many2one | `res.users` |  | yes |  | Time Off | compute `_compute_leave_manager` |
| `remaining_leaves` | Float |  |  | no |  | Remaining Paid Time Off | compute `_compute_remaining_leaves` |
| `current_leave_state` | Selection |  |  | no | `draft` New, `confirm` Waiting Approval, `refuse` Refused, `validate1` Waiting Second Approval, `validate` Approved, `cancel` Cancelled | Current Time Off Status | compute `_compute_leave_status` |
| `leave_date_from` | Date |  |  | no |  | From Date | compute `_compute_leave_status` |
| `leave_date_to` | Date |  |  | no |  | To Date | compute `_compute_leave_status` |
| `leaves_count` | Float |  |  | no |  | Number of Time Off | compute `_compute_remaining_leaves` |
| `allocation_count` | Float |  |  | no |  | Total number of days allocated. | compute `_compute_allocation_count` |
| `allocations_count` | Integer |  |  | no |  | Total number of allocations | compute `_compute_allocation_count` |
| `show_leaves` | Boolean |  |  | no |  | Able to see Remaining Time Off | compute `_compute_show_leaves` |
| `is_absent` | Boolean |  |  | no |  | Absent Today | compute `_compute_leave_status` |
| `allocation_display` | Char |  |  | no |  |  | compute `_compute_allocation_remaining_display` |
| `allocation_remaining_display` | Char |  |  | no |  |  | compute `_compute_allocation_remaining_display` |
| `hr_icon_display` | Selection |  |  | yes | added: `presence_holiday_absent` On leave, `presence_holiday_present` Present but on leave |  |  |

## `hr.leave`

Table `hr_leave`.
Description: Time Off.
Inherits: `mail.thread.main.attachment`, `mail.activity.mixin`.
Order: `date_from desc`.
Source: `hr_leave.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `name` | Char |  |  | no |  | Description | compute `_compute_description` |
| `private_name` | Char |  |  | yes |  | Time Off Description |  |
| `state` | Selection |  |  | yes | `draft` To Submit, `confirm` To Approve, `refuse` Refused, `validate1` Second Approval, `validate` Approved | Status | compute `_compute_state` |
| `report_note` | Text |  |  | yes |  | HR Comments |  |
| `user_id` | Many2one | `res.users` |  | yes |  | User | related `employee_id.user_id` |
| `manager_id` | Many2one | `hr.employee` |  | yes |  |  | compute `_compute_from_employee_id` |
| `is_user_only_responsible` | Boolean |  |  | no |  |  | compute `_compute_is_user_only_responsible` |
| `holiday_status_id` | Many2one | `hr.leave.type` | yes | yes |  | Time Off Type | compute `_compute_from_employee_id` |
| `color` | Integer |  |  | no |  | Color | related `holiday_status_id.color` |
| `validation_type` | Selection |  |  | no |  | Validation Type | related `holiday_status_id.leave_validation_type` |
| `employee_id` | Many2one | `hr.employee` |  | yes |  | Employee | compute `_compute_from_employee_ids` |
| `employee_company_id` | Many2one | (from related) |  | yes |  | Employee Company | related `employee_id.company_id` |
| `company_id` | Many2one | `res.company` |  | yes |  |  | compute `_compute_company_id` |
| `active_employee` | Boolean |  |  | no |  | Employee Active | related `employee_id.active` |
| `tz_mismatch` | Boolean |  |  | no |  |  | compute `_compute_tz_mismatch` |
| `tz` | Selection |  |  | no | (dynamic: _tz_get) |  | compute `_compute_tz` |
| `department_id` | Many2one | `hr.department` |  | yes |  | Department | compute `_compute_department_id` |
| `notes` | Text |  |  | yes |  | Reasons |  |
| `resource_calendar_id` | Many2one | `resource.calendar` |  | yes |  |  | compute `_compute_resource_calendar_id` |
| `date_from` | Datetime |  |  | yes |  | Start Date | compute `_compute_date_from_to` |
| `date_to` | Datetime |  |  | yes |  | End Date | compute `_compute_date_from_to` |
| `number_of_days` | Float |  |  | yes |  | Duration (Days) | compute `_compute_duration` |
| `number_of_hours` | Float |  |  | yes |  | Duration (Hours) | compute `_compute_duration` |
| `last_several_days` | Boolean |  |  | no |  | All day | compute `_compute_last_several_days` |
| `number_of_days_display` | Float |  |  | no |  | Duration in days | compute `_compute_number_of_days_display` |
| `number_of_hours_display` | Float |  |  | no |  | Duration in hours | compute `_compute_number_of_hours_display` |
| `number_of_hours_text` | Char |  |  | no |  |  | compute `_compute_number_of_hours_text` |
| `duration_display` | Char |  |  | yes |  | Requested (Days/Hours) | compute `_compute_duration_display` |
| `meeting_id` | Many2one | `calendar.event` |  | yes |  | Meeting |  |
| `parent_id` | Many2one | `hr.leave` |  | yes |  | Parent |  |
| `linked_request_ids` | One2many | `hr.leave` (inverse `parent_id`) |  | no (inverse) |  | Linked Requests |  |
| `holiday_type` | Selection |  | yes | yes | `employee` By Employee, `company` By Company, `department` By Department, `category` By Employee Tag; default: `'employee'` | Allocation Mode |  |
| `employee_ids` | Many2many | `hr.employee` |  | yes |  | Employees | compute `_compute_from_holiday_type` |
| `multi_employee` | Boolean |  |  | yes |  |  | compute `_compute_from_employee_ids` |
| `category_id` | Many2one | `hr.employee.category` |  | yes |  | Employee Tag | compute `_compute_from_holiday_type` |
| `mode_company_id` | Many2one | `res.company` |  | yes |  | Company Mode | compute `_compute_from_holiday_type` |
| `first_approver_id` | Many2one | `hr.employee` |  | yes |  | First Approval |  |
| `second_approver_id` | Many2one | `hr.employee` |  | yes |  | Second Approval |  |
| `can_reset` | Boolean |  |  | no |  | Can reset | compute `_compute_can_reset` |
| `can_approve` | Boolean |  |  | no |  | Can Approve | compute `_compute_can_approve` |
| `can_cancel` | Boolean |  |  | no |  | Can Cancel | compute `_compute_can_cancel` |
| `attachment_ids` | One2many | `ir.attachment` (inverse `res_id`) |  | no (inverse) |  | Attachments |  |
| `supported_attachment_ids` | Many2many | `ir.attachment` |  | no |  | Attach File | compute `_compute_supported_attachment_ids` |
| `supported_attachment_ids_count` | Integer |  |  | no |  |  | compute `_compute_supported_attachment_ids` |
| `all_employee_ids` | Many2many | `hr.employee` |  | no |  |  | compute `_compute_all_employees` |
| `leave_type_request_unit` | Selection |  |  | no |  |  | related `holiday_status_id.request_unit` |
| `leave_type_support_document` | Boolean |  |  | no |  |  | related `holiday_status_id.support_document` |
| `request_date_from` | Date |  |  | yes |  | Request Start Date |  |
| `request_date_to` | Date |  |  | yes |  | Request End Date |  |
| `request_hour_from` | Selection |  |  | yes | `0` 12:00 AM, `0.5` 12:30 AM, `1` 1:00 AM, `1.5` 1:30 AM, `2` 2:00 AM, `2.5` 2:30 AM, `3` 3:00 AM, `3.5` 3:30 AM, `4` 4:00 AM, `4.5` 4:30 AM, `5` 5:00 AM, `5.5` 5:30 AM, `6` 6:00 AM, `6.5` 6:30 AM, `7` 7:00 AM, `7.5` 7:30 AM, `8` 8:00 AM, `8.5` 8:30 AM, `9` 9:00 AM, `9.5` 9:30 AM, `10` 10:00 AM, `10.5` 10:30 AM, `11` 11:00 AM, `11.5` 11:30 AM, `12` 12:00 PM, `12.5` 12:30 PM, `13` 1:00 PM, `13.5` 1:30 PM, `14` 2:00 PM, `14.5` 2:30 PM, `15` 3:00 PM, `15.5` 3:30 PM, `16` 4:00 PM, `16.5` 4:30 PM, `17` 5:00 PM, `17.5` 5:30 PM, `18` 6:00 PM, `18.5` 6:30 PM, `19` 7:00 PM, `19.5` 7:30 PM, `20` 8:00 PM, `20.5` 8:30 PM, `21` 9:00 PM, `21.5` 9:30 PM, `22` 10:00 PM, `22.5` 10:30 PM, `23` 11:00 PM, `23.5` 11:30 PM | Hour from |  |
| `request_hour_to` | Selection |  |  | yes | `0` 12:00 AM, `0.5` 12:30 AM, `1` 1:00 AM, `1.5` 1:30 AM, `2` 2:00 AM, `2.5` 2:30 AM, `3` 3:00 AM, `3.5` 3:30 AM, `4` 4:00 AM, `4.5` 4:30 AM, `5` 5:00 AM, `5.5` 5:30 AM, `6` 6:00 AM, `6.5` 6:30 AM, `7` 7:00 AM, `7.5` 7:30 AM, `8` 8:00 AM, `8.5` 8:30 AM, `9` 9:00 AM, `9.5` 9:30 AM, `10` 10:00 AM, `10.5` 10:30 AM, `11` 11:00 AM, `11.5` 11:30 AM, `12` 12:00 PM, `12.5` 12:30 PM, `13` 1:00 PM, `13.5` 1:30 PM, `14` 2:00 PM, `14.5` 2:30 PM, `15` 3:00 PM, `15.5` 3:30 PM, `16` 4:00 PM, `16.5` 4:30 PM, `17` 5:00 PM, `17.5` 5:30 PM, `18` 6:00 PM, `18.5` 6:30 PM, `19` 7:00 PM, `19.5` 7:30 PM, `20` 8:00 PM, `20.5` 8:30 PM, `21` 9:00 PM, `21.5` 9:30 PM, `22` 10:00 PM, `22.5` 10:30 PM, `23` 11:00 PM, `23.5` 11:30 PM | Hour to |  |
| `request_date_from_period` | Selection |  |  | yes | `am` Morning, `pm` Afternoon; default: `'am'` | Date Period Start |  |
| `request_unit_half` | Boolean |  |  | yes |  | Half Day | compute `_compute_request_unit_half` |
| `request_unit_hours` | Boolean |  |  | yes |  | Custom Hours | compute `_compute_request_unit_hours` |
| `is_hatched` | Boolean |  |  | no |  | Hatched | compute `_compute_is_hatched` |
| `is_striked` | Boolean |  |  | no |  | Striked | compute `_compute_is_hatched` |
| `has_mandatory_day` | Boolean |  |  | no |  |  | compute `_compute_has_mandatory_day` |
| `leave_type_increases_duration` | Boolean |  |  | no |  |  | compute `_compute_leave_type_increases_duration` |

SQL constraints:

- `type_value`: `CHECK((holiday_type='employee' AND (employee_id IS NOT NULL OR multi_employee IS TRUE)) or (holiday_type='company' AND mode_company_id IS NOT NULL) or (holiday_type='category' AND category_id IS NOT NULL) or (holiday_type='department' AND department_id IS NOT NULL) )`
- `date_check2`: `CHECK ((date_from <= date_to))`
- `date_check3`: `CHECK ((request_date_from <= request_date_to))`
- `duration_check`: `CHECK ( number_of_days >= 0 )`

## `hr.leave.accrual.level`

Table `hr_leave_accrual_level`.
Description: Accrual Plan Level.
Order: `sequence asc`.
Source: `hr_leave_accrual_plan_level.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sequence` | Integer |  |  | yes |  | sequence | compute `_compute_sequence` |
| `accrual_plan_id` | Many2one | `hr.leave.accrual.plan` | yes | yes |  | Accrual Plan |  |
| `accrued_gain_time` | Selection |  |  | no |  |  | related `accrual_plan_id.accrued_gain_time` |
| `start_count` | Integer |  |  | yes | default: `'1'` | Start after |  |
| `start_type` | Selection |  | yes | yes | `day` Days, `month` Months, `year` Years; default: `'day'` |   |  |
| `added_value` | Float |  | yes | yes | default: `1` | Rate |  |
| `added_value_type` | Selection |  | yes | yes | `day` Days, `hour` Hours; default: `'day'` |  | compute `_compute_added_value_type` |
| `frequency` | Selection |  | yes | yes | `hourly` Hourly, `daily` Daily, `weekly` Weekly, `bimonthly` Twice a month, `monthly` Monthly, `biyearly` Twice a year, `yearly` Yearly; default: `'daily'` | Frequency |  |
| `week_day` | Selection |  | yes | yes | `mon` Monday, `tue` Tuesday, `wed` Wednesday, `thu` Thursday, `fri` Friday, `sat` Saturday, `sun` Sunday; default: `'mon'` | Allocation on |  |
| `first_day` | Integer |  |  | yes | default: `1` |  |  |
| `first_day_display` | Selection |  |  | no | (dynamic: _get_selection_days) |  | compute `_compute_days_display` |
| `second_day` | Integer |  |  | yes | default: `15` |  |  |
| `second_day_display` | Selection |  |  | no | (dynamic: _get_selection_days) |  | compute `_compute_days_display` |
| `first_month_day` | Integer |  |  | yes | default: `1` |  |  |
| `first_month_day_display` | Selection |  |  | no | (dynamic: _get_selection_days) |  | compute `_compute_days_display` |
| `first_month` | Selection |  |  | yes | `jan` January, `feb` February, `mar` March, `apr` April, `may` May, `jun` June; default: `'jan'` |  |  |
| `second_month_day` | Integer |  |  | yes | default: `1` |  |  |
| `second_month_day_display` | Selection |  |  | no | (dynamic: _get_selection_days) |  | compute `_compute_days_display` |
| `second_month` | Selection |  |  | yes | `jul` July, `aug` August, `sep` September, `oct` October, `nov` November, `dec` December; default: `'jul'` |  |  |
| `yearly_month` | Selection |  |  | yes | `jan` January, `feb` February, `mar` March, `apr` April, `may` May, `jun` June, `jul` July, `aug` August, `sep` September, `oct` October, `nov` November, `dec` December; default: `'jan'` |  |  |
| `yearly_day` | Integer |  |  | yes | default: `1` |  |  |
| `yearly_day_display` | Selection |  |  | no | (dynamic: _get_selection_days) |  | compute `_compute_days_display` |
| `cap_accrued_time` | Boolean |  |  | yes | default: `True` | Cap accrued time |  |
| `maximum_leave` | Float |  |  | yes |  | Limit to | compute `_compute_maximum_leave` |
| `action_with_unused_accruals` | Selection |  | yes | yes | `lost` None. Accrued time reset to 0, `all` All accrued time carried over, `maximum` Carry over with a maximum; default: `'all'` | Carry over |  |
| `postpone_max_days` | Integer |  |  | yes |  | Maximum amount of accruals to transfer |  |
| `can_modify_value_type` | Boolean |  |  | no |  |  | compute `_compute_can_modify_value_type` |

SQL constraints:

- `check_dates`: `CHECK( (frequency IN ('daily', 'hourly')) or(week_day IS NOT NULL AND frequency = 'weekly') or (first_day > 0 AND second_day > first_day AND first_day <= 31 AND second_day <= 31 AND frequency = 'bimonthly') or (first_day > 0 AND first_day <= 31 AND frequency = 'monthly')or (first_month_day > 0 AND first_month_day <= 31 AND second_month_day > 0 AND second_month_day <= 31 AND frequency = 'biyearly') or (yearly_day > 0 AND yearly_day <= 31 AND frequency = 'yearly'))`
- `start_count_check`: `CHECK( start_count >= 0 )`
- `added_value_greater_than_zero`: `CHECK(added_value > 0)`

## `hr.leave.accrual.plan`

Table `hr_leave_accrual_plan`.
Description: Accrual Plan.
Source: `hr_leave_accrual_plan.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `name` | Char |  | yes | yes |  | Name |  |
| `time_off_type_id` | Many2one | `hr.leave.type` |  | yes |  | Time Off Type |  |
| `employees_count` | Integer |  |  | no |  | Employees | compute `_compute_employee_count` |
| `level_ids` | One2many | `hr.leave.accrual.level` (inverse `accrual_plan_id`) |  | no (inverse) |  | Milestone |  |
| `allocation_ids` | One2many | `hr.leave.allocation` (inverse `accrual_plan_id`) |  | no (inverse) |  |  |  |
| `company_id` | Many2one | `res.company` |  | True |  | Company | compute `_compute_company_id` |
| `transition_mode` | Selection |  | yes | yes | `immediately` Immediately, `end_of_accrual` After this accrual's period; default: `'immediately'` | Milestone Transition |  |
| `show_transition_mode` | Boolean |  |  | no |  |  | compute `_compute_show_transition_mode` |
| `is_based_on_worked_time` | Boolean |  |  | yes |  | Based on worked time | compute `_compute_is_based_on_worked_time` |
| `accrued_gain_time` | Selection |  | yes | yes | `start` At the start of the accrual period, `end` At the end of the accrual period; default: `'end'` |  |  |
| `carryover_date` | Selection |  | yes | yes | `year_start` At the start of the year, `allocation` At the allocation date, `other` Other; default: `'year_start'` | Carry-Over Time |  |
| `carryover_day` | Integer |  |  | yes | default: `1` |  |  |
| `carryover_day_display` | Selection |  |  | no | (dynamic: _get_selection_days) |  | compute `_compute_carryover_day_display` |
| `carryover_month` | Selection |  |  | yes | `jan` January, `feb` February, `mar` March, `apr` April, `may` May, `jun` June, `jul` July, `aug` August, `sep` September, `oct` October, `nov` November, `dec` December; default: `'jan'` |  |  |
| `added_value_type` | Selection |  |  | yes | `day` Days, `hour` Hours |  | compute `_compute_added_value_type` |
| `level_count` | Integer |  |  | no |  | Levels | compute `_compute_level_count` |

## `hr.leave.allocation`

Table `hr_leave_allocation`.
Description: Time Off Allocation.
Inherits: `mail.thread`, `mail.activity.mixin`.
Order: `create_date desc`.
Source: `hr_leave_allocation.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | no |  | Description | compute `_compute_description` |
| `name_validity` | Char |  |  | no |  | Description with validity | compute `_compute_description_validity` |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `private_name` | Char |  |  | yes |  | Allocation Description |  |
| `state` | Selection |  |  | yes | `confirm` To Approve, `refuse` Refused, `validate` Approved; default: `'confirm'` | Status |  |
| `date_from` | Date |  | yes | yes | default: (computed) | Start Date |  |
| `date_to` | Date |  |  | yes |  | End Date |  |
| `holiday_status_id` | Many2one | `hr.leave.type` | yes | yes | default: (computed) | Time Off Type | compute `_compute_holiday_status_id` |
| `employee_id` | Many2one | `hr.employee` |  | yes |  | Employee | compute `_compute_from_employee_ids` |
| `employee_company_id` | Many2one | (from related) |  | yes |  |  | related `employee_id.company_id` |
| `active_employee` | Boolean |  |  | no |  | Active Employee | related `employee_id.active` |
| `manager_id` | Many2one | `hr.employee` |  | yes |  | Manager | compute `_compute_manager_id` |
| `notes` | Text |  |  | yes |  | Reasons |  |
| `number_of_days` | Float |  |  | yes | default: `1` | Number of Days | compute `_compute_from_holiday_status_id` |
| `number_of_days_display` | Float |  |  | no |  | Duration (days) | compute `_compute_number_of_days_display` |
| `number_of_hours_display` | Float |  |  | no |  | Duration (hours) | compute `_compute_number_of_hours_display` |
| `duration_display` | Char |  |  | no |  | Allocated (Days/Hours) | compute `_compute_duration_display` |
| `parent_id` | Many2one | `hr.leave.allocation` |  | yes |  | Parent |  |
| `linked_request_ids` | One2many | `hr.leave.allocation` (inverse `parent_id`) |  | no (inverse) |  | Linked Requests |  |
| `approver_id` | Many2one | `hr.employee` |  | yes |  | First Approval |  |
| `validation_type` | Selection |  |  | no |  | Validation Type | related `holiday_status_id.allocation_validation_type` |
| `can_approve` | Boolean |  |  | no |  | Can Approve | compute `_compute_can_approve` |
| `type_request_unit` | Selection |  |  | no | `hour` Hours, `half_day` Half Day, `day` Day |  | compute `_compute_type_request_unit` |
| `holiday_type` | Selection |  | yes | yes | `employee` By Employee, `company` By Company, `department` By Department, `category` By Employee Tag; default: `'employee'` | Allocation Mode |  |
| `employee_ids` | Many2many | `hr.employee` |  | yes |  | Employees | compute `_compute_from_holiday_type` |
| `multi_employee` | Boolean |  |  | yes |  |  | compute `_compute_from_employee_ids` |
| `mode_company_id` | Many2one | `res.company` |  | yes |  | Company Mode | compute `_compute_from_holiday_type` |
| `department_id` | Many2one | `hr.department` |  | yes |  | Department | compute `_compute_department_id` |
| `category_id` | Many2one | `hr.employee.category` |  | yes |  | Employee Tag | compute `_compute_from_holiday_type` |
| `lastcall` | Date |  |  | yes |  | Date of the last accrual allocation |  |
| `nextcall` | Date |  |  | yes | default: `False` | Date of the next accrual allocation |  |
| `already_accrued` | Boolean |  |  | yes |  |  |  |
| `allocation_type` | Selection |  | yes | yes | `regular` Regular Allocation, `accrual` Accrual Allocation; default: `'regular'` | Allocation Type |  |
| `is_officer` | Boolean |  |  | no |  |  | compute `_compute_is_officer` |
| `accrual_plan_id` | Many2one | `hr.leave.accrual.plan` |  | yes |  |  | compute `_compute_from_holiday_status_id` |
| `max_leaves` | Float |  |  | no |  |  | compute `_compute_leaves` |
| `leaves_taken` | Float |  |  | no |  | Time off Taken | compute `_compute_leaves` |
| `has_accrual_plan` | Boolean |  |  | no |  | Accrual Plan Available | compute `_compute_has_accrual_plan` |

SQL constraints:

- `type_value`: `CHECK( (holiday_type='employee' AND (employee_id IS NOT NULL OR multi_employee IS TRUE)) or (holiday_type='category' AND category_id IS NOT NULL) or (holiday_type='department' AND department_id IS NOT NULL) or (holiday_type='company' AND mode_company_id IS NOT NULL))`
- `duration_check`: `CHECK( ( number_of_days > 0 AND allocation_type='regular') or (allocation_type != 'regular'))`

## `hr.leave.mandatory.day`

Table `hr_leave_mandatory_day`.
Description: Mandatory Day.
Order: `start_date desc, end_date desc`.
Source: `hr_leave_mandatory_day.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) |  |  |
| `start_date` | Date |  | yes | yes |  |  |  |
| `end_date` | Date |  | yes | yes |  |  |  |
| `color` | Integer |  |  | yes | default: (computed) |  |  |
| `resource_calendar_id` | Many2one | `resource.calendar` |  | yes |  | Working Hours |  |
| `department_ids` | Many2many | `hr.department` |  | yes |  | Departments |  |

SQL constraints:

- `date_from_after_day_to`: `CHECK(start_date <= end_date)`

## `hr.leave.type`

Table `hr_leave_type`.
Description: Time Off Type.
Order: `sequence`.
Source: `hr_leave_type.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Time Off Type |  |
| `sequence` | Integer |  |  | yes | default: `100` |  |  |
| `create_calendar_meeting` | Boolean |  |  | yes | default: `True` | Display Time Off in Calendar |  |
| `color` | Integer |  |  | yes |  | Color |  |
| `icon_id` | Many2one | `ir.attachment` |  | yes |  | Cover Image |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `max_leaves` | Float |  |  | no |  | Maximum Allowed | compute `_compute_leaves` |
| `leaves_taken` | Float |  |  | no |  | Time off Already Taken | compute `_compute_leaves` |
| `virtual_remaining_leaves` | Float |  |  | no |  | Virtual Remaining Time Off | compute `_compute_leaves` |
| `allocation_count` | Integer |  |  | no |  | Allocations | compute `_compute_allocation_count` |
| `group_days_leave` | Float |  |  | no |  | Group Time Off | compute `_compute_group_days_leave` |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `responsible_ids` | Many2many | `res.users` (table `hr_leave_type_res_users_rel`) |  | yes |  | Notified Time Off Officer |  |
| `leave_validation_type` | Selection |  |  | yes | `no_validation` No Validation, `hr` By Time Off Officer, `manager` By Employee's Approver, `both` By Employee's Approver and Time Off Officer; default: `'hr'` | Time Off Validation |  |
| `requires_allocation` | Selection |  | yes | yes | `yes` Yes, `no` No Limit; default: `'yes'` | Requires allocation |  |
| `employee_requests` | Selection |  | yes | yes | `yes` Extra Days Requests Allowed, `no` Not Allowed; default: `'no'` | Employee Requests |  |
| `allocation_validation_type` | Selection |  |  | yes | `officer` Approved by Time Off Officer, `no` No validation needed; default: `'no'` | Approval | compute `_compute_allocation_validation_type` |
| `has_valid_allocation` | Boolean |  |  | no |  |  | compute `_compute_valid` |
| `time_type` | Selection |  |  | yes | `other` Worked Time, `leave` Absence; default: `'leave'` | Kind of Time Off |  |
| `request_unit` | Selection |  | yes | yes | `day` Day, `half_day` Half Day, `hour` Hours; default: `'day'` | Take Time Off in |  |
| `unpaid` | Boolean |  |  | yes | default: `False` | Is Unpaid |  |
| `leave_notif_subtype_id` | Many2one | `mail.message.subtype` |  | yes | default: (computed) | Time Off Notification Subtype |  |
| `allocation_notif_subtype_id` | Many2one | `mail.message.subtype` |  | yes | default: (computed) | Allocation Notification Subtype |  |
| `support_document` | Boolean |  |  | yes |  | Supporting Document |  |
| `accruals_ids` | One2many | `hr.leave.accrual.plan` (inverse `time_off_type_id`) |  | no (inverse) |  |  |  |
| `accrual_count` | Float |  |  | no |  | Accruals count | compute `_compute_accrual_count` |
| `allows_negative` | Boolean |  |  | yes |  | Allow Negative Cap |  |
| `max_allowed_negative` | Integer |  |  | yes |  | Amount in Negative |  |

SQL constraints:

- `check_negative`: `CHECK(NOT allows_negative OR max_allowed_negative > 0)`

## `mail.activity.type` (extension)

Adds fields to `mail.activity.type`, defined in another module. Every field below is added by this module.
Source: `mail_activity_type.py`.

## `mail.message.subtype` (extension)

Adds fields to `mail.message.subtype`, defined in another module. Every field below is added by this module.
Source: `mail_message_subtype.py`.

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

## `res.users` (extension)

Adds fields to `res.users`, defined in another module. Every field below is added by this module.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `leave_manager_id` | Many2one | (from related) |  | no |  |  | related `employee_id.leave_manager_id` |
| `show_leaves` | Boolean |  |  | no |  |  | related `employee_id.show_leaves` |
| `allocation_count` | Float |  |  | no |  |  | related `employee_id.allocation_count` |
| `leave_date_to` | Date |  |  | no |  |  | related `employee_id.leave_date_to` |
| `current_leave_state` | Selection |  |  | no |  |  | related `employee_id.current_leave_state` |
| `is_absent` | Boolean |  |  | no |  |  | related `employee_id.is_absent` |
| `allocation_remaining_display` | Char |  |  | no |  |  | related `employee_id.allocation_remaining_display` |
| `allocation_display` | Char |  |  | no |  |  | related `employee_id.allocation_display` |
| `hr_icon_display` | Selection |  |  | no |  |  | related `employee_id.hr_icon_display` |

## `resource.calendar` (extension)

Adds fields to `resource.calendar`, defined in another module. Every field below is added by this module.
Source: `resource.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `associated_leaves_count` | Integer |  |  | no |  | Time Off Count | compute `_compute_associated_leaves_count` |

## `resource.calendar.leaves` (extension)

Adds fields to `resource.calendar.leaves`, defined in another module. Every field below is added by this module.
Source: `resource.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `holiday_id` | Many2one | `hr.leave` |  | yes |  | Time Off Request |  |
