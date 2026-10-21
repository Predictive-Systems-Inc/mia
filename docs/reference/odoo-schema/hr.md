# Odoo 17.0 module `hr`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 9. Models extended here: 12.

## `base` (extension)

Adds fields to `base`, defined in another module. Every field below is added by this module.
Source: `models.py`.

## `discuss.channel` (extension)

Adds fields to `discuss.channel`, defined in another module. Every field below is added by this module.
Source: `discuss_channel.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `subscription_department_ids` | Many2many | `hr.department` |  | yes |  | HR Departments |  |

## `hr.contract.type`

Table `hr_contract_type`.
Description: Contract Type.
Order: `sequence`.
Source: `hr_contract_type.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `code` | Char |  |  | yes |  |  | compute `_compute_code` |
| `sequence` | Integer |  |  | yes |  |  |  |
| `country_id` | Many2one | `res.country` |  | yes |  |  |  |

## `hr.department`

Table `hr_department`.
Description: Department.
Inherits: `mail.thread`.
Order: `name`.
Display name field: `complete_name`.
Source: `hr_department.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Department Name |  |
| `complete_name` | Char |  |  | yes |  | Complete Name | compute `_compute_complete_name` |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `parent_id` | Many2one | `hr.department` |  | yes |  | Parent Department |  |
| `child_ids` | One2many | `hr.department` (inverse `parent_id`) |  | no (inverse) |  | Child Departments |  |
| `manager_id` | Many2one | `hr.employee` |  | yes |  | Manager |  |
| `member_ids` | One2many | `hr.employee` (inverse `department_id`) |  | no (inverse) |  | Members |  |
| `total_employee` | Integer |  |  | no |  | Total Employee | compute `_compute_total_employee` |
| `jobs_ids` | One2many | `hr.job` (inverse `department_id`) |  | no (inverse) |  | Jobs |  |
| `plan_ids` | One2many | `mail.activity.plan` (inverse `department_id`) |  | no (inverse) |  |  |  |
| `plans_count` | Integer |  |  | no |  |  | compute `_compute_plan_count` |
| `note` | Text |  |  | yes |  | Note |  |
| `color` | Integer |  |  | yes |  | Color Index |  |
| `parent_path` | Char |  |  | yes |  |  |  |
| `master_department_id` | Many2one | `hr.department` |  | yes |  | Master Department | compute `_compute_master_department_id` |

## `hr.departure.reason`

Table `hr_departure_reason`.
Description: Departure Reason.
Order: `sequence`.
Source: `hr_departure_reason.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sequence` | Integer |  |  | yes | default: `10` | Sequence |  |
| `name` | Char |  | yes | yes |  | Reason |  |
| `reason_code` | Integer |  |  | yes |  |  |  |

## `hr.employee`

Table `hr_employee`.
Description: Employee.
Inherits: `hr.employee.base`, `mail.thread.main.attachment`, `mail.activity.mixin`, `resource.mixin`, `avatar.mixin`.
Order: `name`.
Source: `hr_employee.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  | Employee Name | related `resource_id.name` |
| `user_id` | Many2one | `res.users` |  | yes |  | User | related `resource_id.user_id` |
| `user_partner_id` | Many2one | (from related) |  | no |  | User's partner | related `user_id.partner_id` |
| `active` | Boolean |  |  | yes | default: `True` | Active | related `resource_id.active` |
| `resource_calendar_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `department_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `company_id` | Many2one | `res.company` | yes | yes |  |  |  |
| `company_country_id` | Many2one | `res.country` |  | no |  | Company Country | related `company_id.country_id` |
| `company_country_code` | Char |  |  | no |  |  | related `company_country_id.code` |
| `private_street` | Char |  |  | yes |  | Private Street |  |
| `private_street2` | Char |  |  | yes |  | Private Street2 |  |
| `private_city` | Char |  |  | yes |  | Private City |  |
| `private_state_id` | Many2one | `res.country.state` |  | yes |  | Private State |  |
| `private_zip` | Char |  |  | yes |  | Private Zip |  |
| `private_country_id` | Many2one | `res.country` |  | yes |  | Private Country |  |
| `private_phone` | Char |  |  | yes |  | Private Phone |  |
| `private_email` | Char |  |  | yes |  | Private Email |  |
| `lang` | Selection |  |  | yes | (dynamic: _lang_get) | Lang |  |
| `country_id` | Many2one | `res.country` |  | yes |  | Nationality (Country) |  |
| `gender` | Selection |  |  | yes | `male` Male, `female` Female, `other` Other |  |  |
| `marital` | Selection |  |  | yes | `single` Single, `married` Married, `cohabitant` Legal Cohabitant, `widower` Widower, `divorced` Divorced; default: `'single'` | Marital Status |  |
| `spouse_complete_name` | Char |  |  | yes |  | Spouse Complete Name |  |
| `spouse_birthdate` | Date |  |  | yes |  | Spouse Birthdate |  |
| `children` | Integer |  |  | yes |  | Number of Dependent Children |  |
| `place_of_birth` | Char |  |  | yes |  | Place of Birth |  |
| `country_of_birth` | Many2one | `res.country` |  | yes |  | Country of Birth |  |
| `birthday` | Date |  |  | yes |  | Date of Birth |  |
| `ssnid` | Char |  |  | yes |  | SSN No |  |
| `sinid` | Char |  |  | yes |  | SIN No |  |
| `identification_id` | Char |  |  | yes |  | Identification No |  |
| `passport_id` | Char |  |  | yes |  | Passport No |  |
| `bank_account_id` | Many2one | `res.partner.bank` |  | yes |  | Bank Account Number |  |
| `permit_no` | Char |  |  | yes |  | Work Permit No |  |
| `visa_no` | Char |  |  | yes |  | Visa No |  |
| `visa_expire` | Date |  |  | yes |  | Visa Expiration Date |  |
| `work_permit_expiration_date` | Date |  |  | yes |  | Work Permit Expiration Date |  |
| `has_work_permit` | Binary |  |  | yes |  | Work Permit |  |
| `work_permit_scheduled_activity` | Boolean |  |  | yes | default: `False` |  |  |
| `work_permit_name` | Char |  |  | no |  | work_permit_name | compute `_compute_work_permit_name` |
| `additional_note` | Text |  |  | yes |  | Additional Note |  |
| `certificate` | Selection |  |  | yes | `graduate` Graduate, `bachelor` Bachelor, `master` Master, `doctor` Doctor, `other` Other; default: `'other'` | Certificate Level |  |
| `study_field` | Char |  |  | yes |  | Field of Study |  |
| `study_school` | Char |  |  | yes |  | School |  |
| `emergency_contact` | Char |  |  | yes |  | Contact Name |  |
| `emergency_phone` | Char |  |  | yes |  | Contact Phone |  |
| `km_home_work` | Integer |  |  | yes |  | Home-Work Distance |  |
| `employee_type` | Selection |  | yes | yes | `employee` Employee, `student` Student, `trainee` Trainee, `contractor` Contractor, `freelance` Freelancer; default: `'employee'` | Employee Type |  |
| `job_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `child_ids` | One2many | `hr.employee` (inverse `parent_id`) |  | no (inverse) |  | Direct subordinates |  |
| `category_ids` | Many2many | `hr.employee.category` (table `employee_category_rel`) |  | yes |  | Tags |  |
| `notes` | Text |  |  | yes |  | Notes |  |
| `color` | Integer |  |  | yes | default: `0` | Color Index |  |
| `barcode` | Char |  |  | yes |  | Badge ID |  |
| `pin` | Char |  |  | yes |  | PIN |  |
| `departure_reason_id` | Many2one | `hr.departure.reason` |  | yes |  | Departure Reason |  |
| `departure_description` | Html |  |  | yes |  | Additional Information |  |
| `departure_date` | Date |  |  | yes |  | Departure Date |  |
| `message_main_attachment_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `id_card` | Binary |  |  | yes |  | ID Card Copy |  |
| `driving_license` | Binary |  |  | yes |  | Driving License |  |
| `private_car_plate` | Char |  |  | yes |  |  |  |
| `currency_id` | Many2one | `res.currency` |  | no |  |  | related `company_id.currency_id` |
| `employee_properties` | Properties |  |  | yes |  | Properties |  |

SQL constraints:

- `barcode_uniq`: `unique (barcode)`
- `user_uniq`: `unique (user_id, company_id)`

## `hr.employee.base`

Abstract model (mixin), no table of its own.
Description: Basic Employee.
Order: `name`.
Source: `hr_employee_base.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  |  |  |
| `active` | Boolean |  |  | yes |  | Active |  |
| `color` | Integer |  |  | yes | default: `0` | Color Index |  |
| `department_id` | Many2one | `hr.department` |  | yes |  | Department |  |
| `member_of_department` | Boolean |  |  | no |  | Member of department | compute `_compute_part_of_department` |
| `job_id` | Many2one | `hr.job` |  | yes |  | Job Position |  |
| `job_title` | Char |  |  | yes |  | Job Title | compute `_compute_job_title` |
| `company_id` | Many2one | `res.company` |  | yes |  | Company |  |
| `address_id` | Many2one | `res.partner` |  | yes |  | Work Address | compute `_compute_address_id` |
| `work_phone` | Char |  |  | yes |  | Work Phone | compute `_compute_phones` |
| `mobile_phone` | Char |  |  | yes |  | Work Mobile | compute `_compute_work_contact_details` |
| `work_email` | Char |  |  | yes |  | Work Email | compute `_compute_work_contact_details` |
| `work_contact_id` | Many2one | `res.partner` |  | yes |  | Work Contact |  |
| `work_location_id` | Many2one | `hr.work.location` |  | yes |  | Work Location |  |
| `user_id` | Many2one | `res.users` |  | yes |  |  |  |
| `resource_id` | Many2one | `resource.resource` |  | yes |  |  |  |
| `resource_calendar_id` | Many2one | `resource.calendar` |  | yes |  |  |  |
| `parent_id` | Many2one | `hr.employee` |  | yes |  | Manager | compute `_compute_parent_id` |
| `coach_id` | Many2one | `hr.employee` |  | yes |  | Coach | compute `_compute_coach` |
| `tz` | Selection |  |  | no |  | Timezone | related `resource_id.tz` |
| `hr_presence_state` | Selection |  |  | no | `present` Present, `absent` Absent, `to_define` To Define; default: `'to_define'` |  | compute `_compute_presence_state` |
| `last_activity` | Date |  |  | no |  |  | compute `_compute_last_activity` |
| `last_activity_time` | Char |  |  | no |  |  | compute `_compute_last_activity` |
| `hr_icon_display` | Selection |  |  | no | `presence_present` Present, `presence_absent_active` Present but not active, `presence_absent` Absent, `presence_to_define` To define, `presence_undetermined` Undetermined |  | compute `_compute_presence_icon` |
| `show_hr_icon_display` | Boolean |  |  | no |  |  | compute `_compute_presence_icon` |
| `newly_hired` | Boolean |  |  | no |  | Newly Hired | compute `_compute_newly_hired` |

## `hr.employee.category`

Table `hr_employee_category`.
Description: Employee Category.
Source: `hr_employee_category.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Tag Name |  |
| `color` | Integer |  |  | yes | default: (computed) | Color Index |  |
| `employee_ids` | Many2many | `hr.employee` (table `employee_category_rel`) |  | yes |  | Employees |  |

SQL constraints:

- `name_uniq`: `unique (name)`

## `hr.employee.public`

Table `hr_employee_public`. Not auto-created (`_auto = False`, SQL view).
Description: Public Employee.
Inherits: `hr.employee.base`.
Order: `name`.
Source: `hr_employee_public.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `create_date` | Datetime |  |  | yes |  |  |  |
| `name` | Char |  |  | yes |  |  |  |
| `active` | Boolean |  |  | yes |  |  |  |
| `department_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `job_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `job_title` | Char |  |  | yes |  |  |  |
| `company_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `address_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `mobile_phone` | Char |  |  | yes |  |  |  |
| `work_phone` | Char |  |  | yes |  |  |  |
| `work_email` | Char |  |  | yes |  |  |  |
| `work_contact_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `work_location_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `user_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `resource_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `tz` | Selection |  |  | yes |  |  |  |
| `color` | Integer |  |  | yes |  |  |  |
| `is_manager` | Boolean |  |  | no |  |  | compute `_compute_is_manager` |
| `employee_id` | Many2one | `hr.employee` |  | no |  | Employee | compute `_compute_employee_id` |
| `child_ids` | One2many | `hr.employee.public` (inverse `parent_id`) |  | no (inverse) |  | Direct subordinates |  |
| `image_1920` | Image |  |  | no |  | Image | related `employee_id.image_1920` |
| `image_1024` | Image |  |  | no |  | Image 1024 | related `employee_id.image_1024` |
| `image_512` | Image |  |  | no |  | Image 512 | related `employee_id.image_512` |
| `image_256` | Image |  |  | no |  | Image 256 | related `employee_id.image_256` |
| `image_128` | Image |  |  | no |  | Image 128 | related `employee_id.image_128` |
| `avatar_1920` | Image |  |  | no |  | Avatar | related `employee_id.avatar_1920` |
| `avatar_1024` | Image |  |  | no |  | Avatar 1024 | related `employee_id.avatar_1024` |
| `avatar_512` | Image |  |  | no |  | Avatar 512 | related `employee_id.avatar_512` |
| `avatar_256` | Image |  |  | no |  | Avatar 256 | related `employee_id.avatar_256` |
| `avatar_128` | Image |  |  | no |  | Avatar 128 | related `employee_id.avatar_128` |
| `parent_id` | Many2one | `hr.employee.public` |  | yes |  | Manager |  |
| `coach_id` | Many2one | `hr.employee.public` |  | yes |  | Coach |  |
| `user_partner_id` | Many2one | (from related) |  | no |  | User's partner | related `user_id.partner_id` |

## `hr.job`

Table `hr_job`.
Description: Job Position.
Inherits: `mail.thread`.
Order: `sequence`.
Source: `hr_job.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `name` | Char |  | yes | yes |  | Job Position |  |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |
| `expected_employees` | Integer |  |  | yes |  | Total Forecasted Employees | compute `_compute_employees` |
| `no_of_employee` | Integer |  |  | yes |  | Current Number of Employees | compute `_compute_employees` |
| `no_of_recruitment` | Integer |  |  | yes | default: `1` | Target |  |
| `no_of_hired_employee` | Integer |  |  | yes |  | Hired Employees |  |
| `employee_ids` | One2many | `hr.employee` (inverse `job_id`) |  | no (inverse) |  | Employees |  |
| `description` | Html |  |  | yes | default: `'Perform assigned responsibilities, collaborate with team members, and adhere to company policies. Strong communication, problem-solving, and work ethic required. Adaptability, initiative, and willingness to learn are valued.'` | Job Description |  |
| `requirements` | Text |  |  | yes |  | Requirements |  |
| `department_id` | Many2one | `hr.department` |  | yes |  | Department |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `contract_type_id` | Many2one | `hr.contract.type` |  | yes |  | Employment Type |  |

SQL constraints:

- `name_company_uniq`: `unique(name, company_id, department_id)`
- `no_of_recruitment_positive`: `CHECK(no_of_recruitment >= 0)`

## `hr.work.location`

Table `hr_work_location`.
Description: Work Location.
Order: `name`.
Source: `hr_work_location.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `name` | Char |  | yes | yes |  | Work Location |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) |  |  |
| `location_type` | Selection |  | yes | yes | `home` Home, `office` Office, `other` Other; default: `'office'` | Cover Image |  |
| `address_id` | Many2one | `res.partner` | yes | yes |  | Work Address |  |
| `location_number` | Char |  |  | yes |  |  |  |

## `ir.ui.menu` (extension)

Adds fields to `ir.ui.menu`, defined in another module. Every field below is added by this module.
Source: `ir_ui_menu.py`.

## `mail.activity.plan` (extension)

Adds fields to `mail.activity.plan`, defined in another module. Every field below is added by this module.
Source: `mail_activity_plan.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `department_id` | Many2one | `hr.department` |  | yes |  |  | compute `_compute_department_id` |

## `mail.activity.plan.template` (extension)

Adds fields to `mail.activity.plan.template`, defined in another module. Every field below is added by this module.
Source: `mail_activity_plan_template.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `responsible_type` | Selection |  |  | yes | added: `coach` Coach, `manager` Manager, `employee` Employee |  |  |

## `mail.alias` (extension)

Adds fields to `mail.alias`, defined in another module. Every field below is added by this module.
Source: `mail_alias.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `alias_contact` | Selection |  |  | yes | added: `employees` Authenticated Employees |  |  |

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Source: `res_company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `hr_presence_control_email_amount` | Integer |  |  | yes |  | # emails to send |  |
| `hr_presence_control_ip_list` | Char |  |  | yes |  | Valid IP addresses |  |
| `employee_properties_definition` | PropertiesDefinition |  |  | yes |  | Employee Properties |  |

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `resource_calendar_id` | Many2one | `resource.calendar` |  | no |  | Company Working Hours | related `company_id.resource_calendar_id` |
| `module_hr_presence` | Boolean |  |  | yes |  | Advanced Presence Control |  |
| `module_hr_skills` | Boolean |  |  | yes |  | Skills Management |  |
| `module_hr_homeworking` | Boolean |  |  | yes |  | Remote Work |  |
| `hr_presence_control_login` | Boolean |  |  | yes |  | Based on user status in system |  |
| `hr_presence_control_email` | Boolean |  |  | yes |  | Based on number of emails sent |  |
| `hr_presence_control_ip` | Boolean |  |  | yes |  | Based on IP Address |  |
| `module_hr_attendance` | Boolean |  |  | yes |  | Based on attendances |  |
| `hr_presence_control_email_amount` | Integer |  |  | no |  |  | related `company_id.hr_presence_control_email_amount` |
| `hr_presence_control_ip_list` | Char |  |  | no |  |  | related `company_id.hr_presence_control_ip_list` |
| `hr_employee_self_edit` | Boolean |  |  | yes |  | Employee Editing |  |

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `employee_ids` | One2many | `hr.employee` (inverse `work_contact_id`) |  | no (inverse) |  | Employees |  |
| `employees_count` | Integer |  |  | no |  |  | compute `_compute_employees_count` |

## `res.partner.bank` (extension)

Adds fields to `res.partner.bank`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

## `res.users` (extension)

Adds fields to `res.users`, defined in another module. Every field below is added by this module.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `employee_ids` | One2many | `hr.employee` (inverse `user_id`) |  | no (inverse) |  | Related employee |  |
| `employee_id` | Many2one | `hr.employee` |  | no |  | Company employee | compute `_compute_company_employee` |
| `job_title` | Char |  |  | no |  |  | related `employee_id.job_title` |
| `work_phone` | Char |  |  | no |  |  | related `employee_id.work_phone` |
| `mobile_phone` | Char |  |  | no |  |  | related `employee_id.mobile_phone` |
| `work_email` | Char |  |  | no |  |  | related `employee_id.work_email` |
| `category_ids` | Many2many | (from related) |  | no |  | Employee Tags | related `employee_id.category_ids` |
| `department_id` | Many2one | (from related) |  | no |  |  | related `employee_id.department_id` |
| `address_id` | Many2one | (from related) |  | no |  |  | related `employee_id.address_id` |
| `work_contact_id` | Many2one | (from related) |  | no |  |  | related `employee_id.work_contact_id` |
| `work_location_id` | Many2one | (from related) |  | no |  |  | related `employee_id.work_location_id` |
| `employee_parent_id` | Many2one | (from related) |  | no |  |  | related `employee_id.parent_id` |
| `coach_id` | Many2one | (from related) |  | no |  |  | related `employee_id.coach_id` |
| `private_street` | Char |  |  | no |  | Private Street | related `employee_id.private_street` |
| `private_street2` | Char |  |  | no |  | Private Street2 | related `employee_id.private_street2` |
| `private_city` | Char |  |  | no |  | Private City | related `employee_id.private_city` |
| `private_state_id` | Many2one | (from related) |  | no |  | Private State | related `employee_id.private_state_id` |
| `private_zip` | Char |  |  | no |  | Private Zip | related `employee_id.private_zip` |
| `private_country_id` | Many2one | (from related) |  | no |  | Private Country | related `employee_id.private_country_id` |
| `private_phone` | Char |  |  | no |  |  | related `employee_id.private_phone` |
| `private_email` | Char |  |  | no |  | Private Email | related `employee_id.private_email` |
| `private_lang` | Selection |  |  | no |  | Employee Lang | related `employee_id.lang` |
| `km_home_work` | Integer |  |  | no |  |  | related `employee_id.km_home_work` |
| `employee_bank_account_id` | Many2one | (from related) |  | no |  | Employee's Bank Account Number | related `employee_id.bank_account_id` |
| `employee_country_id` | Many2one | (from related) |  | no |  | Employee's Country | related `employee_id.country_id` |
| `employee_country_code` | Char |  |  | no |  | Employee's Country Code | related `employee_id.company_country_code` |
| `identification_id` | Char |  |  | no |  |  | related `employee_id.identification_id` |
| `ssnid` | Char |  |  | no |  |  | related `employee_id.ssnid` |
| `passport_id` | Char |  |  | no |  |  | related `employee_id.passport_id` |
| `gender` | Selection |  |  | no |  |  | related `employee_id.gender` |
| `birthday` | Date |  |  | no |  |  | related `employee_id.birthday` |
| `place_of_birth` | Char |  |  | no |  |  | related `employee_id.place_of_birth` |
| `country_of_birth` | Many2one | (from related) |  | no |  |  | related `employee_id.country_of_birth` |
| `marital` | Selection |  |  | no |  |  | related `employee_id.marital` |
| `spouse_complete_name` | Char |  |  | no |  |  | related `employee_id.spouse_complete_name` |
| `spouse_birthdate` | Date |  |  | no |  |  | related `employee_id.spouse_birthdate` |
| `children` | Integer |  |  | no |  |  | related `employee_id.children` |
| `emergency_contact` | Char |  |  | no |  |  | related `employee_id.emergency_contact` |
| `emergency_phone` | Char |  |  | no |  |  | related `employee_id.emergency_phone` |
| `visa_no` | Char |  |  | no |  |  | related `employee_id.visa_no` |
| `permit_no` | Char |  |  | no |  |  | related `employee_id.permit_no` |
| `visa_expire` | Date |  |  | no |  |  | related `employee_id.visa_expire` |
| `additional_note` | Text |  |  | no |  |  | related `employee_id.additional_note` |
| `barcode` | Char |  |  | no |  |  | related `employee_id.barcode` |
| `pin` | Char |  |  | no |  |  | related `employee_id.pin` |
| `certificate` | Selection |  |  | no |  |  | related `employee_id.certificate` |
| `study_field` | Char |  |  | no |  |  | related `employee_id.study_field` |
| `study_school` | Char |  |  | no |  |  | related `employee_id.study_school` |
| `employee_count` | Integer |  |  | no |  |  | compute `_compute_employee_count` |
| `hr_presence_state` | Selection |  |  | no |  |  | related `employee_id.hr_presence_state` |
| `last_activity` | Date |  |  | no |  |  | related `employee_id.last_activity` |
| `last_activity_time` | Char |  |  | no |  |  | related `employee_id.last_activity_time` |
| `employee_type` | Selection |  |  | no |  |  | related `employee_id.employee_type` |
| `employee_resource_calendar_id` | Many2one | (from related) |  | no |  | Employee's Working Hours | related `employee_id.resource_calendar_id` |
| `create_employee` | Boolean |  |  | no | default: `False` | Technical field, whether to create an employee |  |
| `create_employee_id` | Many2one | `hr.employee` |  | no |  | Technical field, bind user to this employee on create |  |
| `can_edit` | Boolean |  |  | no |  |  | compute `_compute_can_edit` |
| `is_system` | Boolean |  |  | no |  |  | compute `_compute_is_system` |

## `resource.resource` (extension)

Adds fields to `resource.resource`, defined in another module. Every field below is added by this module.
Source: `resource.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `user_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `employee_id` | One2many | `hr.employee` (inverse `resource_id`) |  | no (inverse) |  |  |  |
