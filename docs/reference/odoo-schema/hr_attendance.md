# Odoo 17.0 module `hr_attendance`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 2. Models extended here: 7.

## `hr.attendance`

Table `hr_attendance`.
Description: Attendance.
Inherits: `mail.thread`.
Order: `check_in desc`.
Source: `hr_attendance.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `employee_id` | Many2one | `hr.employee` | yes | yes | default: (computed) | Employee |  |
| `department_id` | Many2one | `hr.department` |  | no |  | Department | related `employee_id.department_id` |
| `check_in` | Datetime |  | yes | yes | default: (computed) | Check In |  |
| `check_out` | Datetime |  |  | yes |  | Check Out |  |
| `worked_hours` | Float |  |  | yes |  | Worked Hours | compute `_compute_worked_hours` |
| `color` | Integer |  |  | no |  |  | compute `_compute_color` |
| `overtime_hours` | Float |  |  | yes |  | Over Time | compute `_compute_overtime_hours` |
| `in_latitude` | Float |  |  | yes |  | Latitude |  |
| `in_longitude` | Float |  |  | yes |  | Longitude |  |
| `in_country_name` | Char |  |  | yes |  | Country |  |
| `in_city` | Char |  |  | yes |  | City |  |
| `in_ip_address` | Char |  |  | yes |  | IP Address |  |
| `in_browser` | Char |  |  | yes |  | Browser |  |
| `in_mode` | Selection |  |  | yes | `kiosk` Kiosk, `systray` Systray, `manual` Manual; default: `'manual'` | Mode |  |
| `out_latitude` | Float |  |  | yes |  |  |  |
| `out_longitude` | Float |  |  | yes |  |  |  |
| `out_country_name` | Char |  |  | yes |  |  |  |
| `out_city` | Char |  |  | yes |  |  |  |
| `out_ip_address` | Char |  |  | yes |  |  |  |
| `out_browser` | Char |  |  | yes |  |  |  |
| `out_mode` | Selection |  |  | yes | `kiosk` Kiosk, `systray` Systray, `manual` Manual; default: `'manual'` |  |  |

## `hr.attendance.overtime`

Table `hr_attendance_overtime`.
Description: Attendance Overtime.
Order: `date desc`.
Display name field: `employee_id`.
Source: `hr_attendance_overtime.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `employee_id` | Many2one | `hr.employee` | yes | yes | default: (computed) | Employee |  |
| `company_id` | Many2one | (from related) |  | no |  |  | related `employee_id.company_id` |
| `date` | Date |  |  | yes |  | Day |  |
| `duration` | Float |  | yes | yes | default: `0.0` | Extra Hours |  |
| `duration_real` | Float |  |  | yes | default: `0.0` | Extra Hours (Real) |  |
| `adjustment` | Boolean |  |  | yes | default: `False` |  |  |

## `hr.employee` (extension)

Adds fields to `hr.employee`, defined in another module. Every field below is added by this module.
Source: `hr_employee.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `attendance_manager_id` | Many2one | `res.users` |  | yes |  |  |  |
| `attendance_ids` | One2many | `hr.attendance` (inverse `employee_id`) |  | no (inverse) |  |  |  |
| `last_attendance_id` | Many2one | `hr.attendance` |  | yes |  |  | compute `_compute_last_attendance_id` |
| `last_check_in` | Datetime |  |  | yes |  |  | related `last_attendance_id.check_in` |
| `last_check_out` | Datetime |  |  | yes |  |  | related `last_attendance_id.check_out` |
| `attendance_state` | Selection |  |  | no | `checked_out` Checked out, `checked_in` Checked in | Attendance Status | compute `_compute_attendance_state` |
| `hours_last_month` | Float |  |  | no |  |  | compute `_compute_hours_last_month` |
| `hours_today` | Float |  |  | no |  |  | compute `_compute_hours_today` |
| `hours_previously_today` | Float |  |  | no |  |  | compute `_compute_hours_today` |
| `last_attendance_worked_hours` | Float |  |  | no |  |  | compute `_compute_hours_today` |
| `hours_last_month_display` | Char |  |  | no |  |  | compute `_compute_hours_last_month` |
| `overtime_ids` | One2many | `hr.attendance.overtime` (inverse `employee_id`) |  | no (inverse) |  |  |  |
| `total_overtime` | Float |  |  | no |  |  | compute `_compute_total_overtime` |

## `hr.employee.base` (extension)

Adds fields to `hr.employee.base`, defined in another module. Every field below is added by this module.
Source: `hr_employee_base.py`.

## `hr.employee.public` (extension)

Adds fields to `hr.employee.public`, defined in another module. Every field below is added by this module.
Source: `hr_employee_public.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `attendance_state` | Selection |  |  | no |  |  | related `employee_id.attendance_state` |
| `hours_today` | Float |  |  | no |  |  | related `employee_id.hours_today` |
| `last_attendance_id` | Many2one | (from related) |  | no |  |  | related `employee_id.last_attendance_id` |
| `total_overtime` | Float |  |  | no |  |  | related `employee_id.total_overtime` |
| `attendance_manager_id` | Many2one | (from related) |  | no |  |  | related `employee_id.attendance_manager_id` |
| `last_check_in` | Datetime |  |  | no |  |  | related `employee_id.last_check_in` |
| `last_check_out` | Datetime |  |  | no |  |  | related `employee_id.last_check_out` |

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Source: `res_company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `hr_attendance_overtime` | Boolean |  |  | yes |  | Count Extra Hours |  |
| `overtime_start_date` | Date |  |  | yes |  | Extra Hours Starting Date |  |
| `overtime_company_threshold` | Integer |  |  | yes | default: `0` | Tolerance Time In Favor Of Company |  |
| `overtime_employee_threshold` | Integer |  |  | yes | default: `0` | Tolerance Time In Favor Of Employee |  |
| `hr_attendance_display_overtime` | Boolean |  |  | yes |  | Display Extra Hours |  |
| `attendance_kiosk_mode` | Selection |  |  | yes | `barcode` Barcode / RFID, `barcode_manual` Barcode / RFID and Manual Selection, `manual` Manual Selection; default: `'barcode_manual'` | Attendance Mode |  |
| `attendance_barcode_source` | Selection |  |  | yes | `scanner` Scanner, `front` Front Camera, `back` Back Camera; default: `'front'` | Barcode Source |  |
| `attendance_kiosk_delay` | Integer |  |  | yes | default: `10` |  |  |
| `attendance_kiosk_key` | Char |  |  | yes | default: (computed) |  |  |
| `attendance_kiosk_url` | Char |  |  | no |  |  | compute `_compute_attendance_kiosk_url` |
| `attendance_kiosk_use_pin` | Boolean |  |  | yes |  | Employee PIN Identification |  |
| `attendance_from_systray` | Boolean |  |  | yes | default: `True` | Attendance From Systray |  |

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `hr_attendance_overtime` | Boolean |  |  | yes |  | Count Extra Hours |  |
| `overtime_start_date` | Date |  |  | yes |  | Extra Hours Starting Date |  |
| `overtime_company_threshold` | Integer |  |  | yes |  | Tolerance Time In Favor Of Company |  |
| `overtime_employee_threshold` | Integer |  |  | yes |  | Tolerance Time In Favor Of Employee |  |
| `hr_attendance_display_overtime` | Boolean |  |  | no |  |  | related `company_id.hr_attendance_display_overtime` |
| `attendance_kiosk_mode` | Selection |  |  | no |  |  | related `company_id.attendance_kiosk_mode` |
| `attendance_barcode_source` | Selection |  |  | no |  |  | related `company_id.attendance_barcode_source` |
| `attendance_kiosk_delay` | Integer |  |  | no |  |  | related `company_id.attendance_kiosk_delay` |
| `attendance_kiosk_url` | Char |  |  | no |  |  | related `company_id.attendance_kiosk_url` |
| `attendance_kiosk_use_pin` | Boolean |  |  | no |  |  | related `company_id.attendance_kiosk_use_pin` |
| `attendance_from_systray` | Boolean |  |  | no |  |  | related `company_id.attendance_from_systray` |

## `res.users` (extension)

Adds fields to `res.users`, defined in another module. Every field below is added by this module.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `hours_last_month` | Float |  |  | no |  |  | related `employee_id.hours_last_month` |
| `hours_last_month_display` | Char |  |  | no |  |  | related `employee_id.hours_last_month_display` |
| `attendance_state` | Selection |  |  | no |  |  | related `employee_id.attendance_state` |
| `last_check_in` | Datetime |  |  | no |  |  | related `employee_id.last_attendance_id.check_in` |
| `last_check_out` | Datetime |  |  | no |  |  | related `employee_id.last_attendance_id.check_out` |
| `total_overtime` | Float |  |  | no |  |  | related `employee_id.total_overtime` |
| `attendance_manager_id` | Many2one | (from related) |  | no |  |  | related `employee_id.attendance_manager_id` |
| `display_extra_hours` | Boolean |  |  | no |  |  | related `company_id.hr_attendance_display_overtime` |

## `resource.calendar.leaves` (extension)

Adds fields to `resource.calendar.leaves`, defined in another module. Every field below is added by this module.
Source: `resource_calendar_leaves.py`.
