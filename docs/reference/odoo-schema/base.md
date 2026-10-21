# Odoo 17.0 module `base`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 109. Models extended here: 0.

## `_unknown`

Abstract model (mixin), no table of its own.
Description: Unknown.
Source: `ir_model.py`.

## `avatar.mixin`

Abstract model (mixin), no table of its own.
Description: Avatar Mixin.
Inherits: `image.mixin`.
Source: `avatar_mixin.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `avatar_1920` | Image |  |  | no |  | Avatar | compute `_compute_avatar_1920` |
| `avatar_1024` | Image |  |  | no |  | Avatar 1024 | compute `_compute_avatar_1024` |
| `avatar_512` | Image |  |  | no |  | Avatar 512 | compute `_compute_avatar_512` |
| `avatar_256` | Image |  |  | no |  | Avatar 256 | compute `_compute_avatar_256` |
| `avatar_128` | Image |  |  | no |  | Avatar 128 | compute `_compute_avatar_128` |

## `base`

Abstract model (mixin), no table of its own.
Description: Base.
Source: `ir_model.py`, `ir_ui_view.py`.

## `base.enable.profiling.wizard`

Transient model (wizard), table `base_enable_profiling_wizard`, rows purged.
Description: Enable profiling for some time.
Source: `ir_profile.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `duration` | Selection |  |  | yes | `minutes_5` 5 Minutes, `hours_1` 1 Hour, `days_1` 1 Day, `months_1` 1 Month | Enable profiling for |  |
| `expiration` | Datetime |  |  | yes |  | Enable profiling until | compute `_compute_expiration` |

## `change.password.own`

Transient model (wizard), table `change_password_own`, rows purged.
Description: User, change own password wizard.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `new_password` | Char |  |  | yes |  | New Password |  |
| `confirm_password` | Char |  |  | yes |  | New Password (Confirmation) |  |

## `change.password.user`

Transient model (wizard), table `change_password_user`, rows purged.
Description: User, Change Password Wizard.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `wizard_id` | Many2one | `change.password.wizard` | yes | yes |  | Wizard |  |
| `user_id` | Many2one | `res.users` | yes | yes |  | User |  |
| `user_login` | Char |  |  | yes |  | User Login |  |
| `new_passwd` | Char |  |  | yes | default: `''` | New Password |  |

## `change.password.wizard`

Transient model (wizard), table `change_password_wizard`, rows purged.
Description: Change Password Wizard.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `user_ids` | One2many | `change.password.user` (inverse `wizard_id`) |  | no (inverse) | default: (computed) | Users |  |

## `decimal.precision`

Table `decimal_precision`.
Description: Decimal Precision.
Source: `decimal_precision.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Usage |  |
| `digits` | Integer |  | yes | yes | default: `2` | Digits |  |

SQL constraints:

- `name_uniq`: `unique (name)`

## `format.address.mixin`

Abstract model (mixin), no table of its own.
Description: Address Format.
Source: `res_partner.py`.

## `image.mixin`

Abstract model (mixin), no table of its own.
Description: Image Mixin.
Source: `image_mixin.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `image_1920` | Image |  |  | yes |  | Image |  |
| `image_1024` | Image |  |  | yes |  | Image 1024 | related `image_1920` |
| `image_512` | Image |  |  | yes |  | Image 512 | related `image_1920` |
| `image_256` | Image |  |  | yes |  | Image 256 | related `image_1920` |
| `image_128` | Image |  |  | yes |  | Image 128 | related `image_1920` |

## `ir.actions.act_url`

Table `ir_act_url`.
Description: Action URL.
Inherits: `ir.actions.actions`.
Order: `name`.
Source: `ir_actions.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `type` | Char |  |  | yes | default: `'ir.actions.act_url'` |  |  |
| `url` | Text |  | yes | yes |  | Action URL |  |
| `target` | Selection |  | yes | yes | `new` New Window, `self` This Window, `download` Download; default: `'new'` | Action Target |  |

## `ir.actions.act_window`

Table `ir_act_window`.
Description: Action Window.
Inherits: `ir.actions.actions`.
Order: `name`.
Source: `ir_actions.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `type` | Char |  |  | yes | default: `'ir.actions.act_window'` |  |  |
| `view_id` | Many2one | `ir.ui.view` |  | yes |  | View Ref. |  |
| `domain` | Char |  |  | yes |  | Domain Value |  |
| `context` | Char |  | yes | yes | default: `{}` | Context Value |  |
| `res_id` | Integer |  |  | yes |  | Record ID |  |
| `res_model` | Char |  | yes | yes |  | Destination Model |  |
| `target` | Selection |  |  | yes | `current` Current Window, `new` New Window, `inline` Inline Edit, `fullscreen` Full Screen, `main` Main action of Current Window; default: `'current'` | Target Window |  |
| `view_mode` | Char |  | yes | yes | default: `'tree,form'` |  |  |
| `mobile_view_mode` | Char |  |  | yes | default: `'kanban'` |  |  |
| `usage` | Char |  |  | yes |  | Action Usage |  |
| `view_ids` | One2many | `ir.actions.act_window.view` (inverse `act_window_id`) |  | no (inverse) |  | No of Views |  |
| `views` | Binary |  |  | no |  |  | compute `_compute_views` |
| `limit` | Integer |  |  | yes | default: `80` |  |  |
| `groups_id` | Many2many | `res.groups` (table `ir_act_window_group_rel`) |  | yes |  | Groups |  |
| `search_view_id` | Many2one | `ir.ui.view` |  | yes |  | Search View Ref. |  |
| `filter` | Boolean |  |  | yes |  |  |  |

## `ir.actions.act_window.view`

Table `ir_act_window_view`.
Description: Action Window View.
Order: `sequence,id`.
Display name field: `view_id`.
Source: `ir_actions.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sequence` | Integer |  |  | yes |  |  |  |
| `view_id` | Many2one | `ir.ui.view` |  | yes |  | View |  |
| `view_mode` | Selection |  | yes | yes | `tree` Tree, `form` Form, `graph` Graph, `pivot` Pivot, `calendar` Calendar, `gantt` Gantt, `kanban` Kanban | View Type |  |
| `act_window_id` | Many2one | `ir.actions.act_window` |  | yes |  | Action |  |
| `multi` | Boolean |  |  | yes |  | On Multiple Doc. |  |

## `ir.actions.act_window_close`

Table `ir_actions`.
Description: Action Window Close.
Inherits: `ir.actions.actions`.
Source: `ir_actions.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `type` | Char |  |  | yes | default: `'ir.actions.act_window_close'` |  |  |

## `ir.actions.actions`

Table `ir_actions`.
Description: Actions.
Order: `name`.
Source: `ir_actions.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Action Name |  |
| `type` | Char |  | yes | yes |  | Action Type |  |
| `xml_id` | Char |  |  | no |  | External ID | compute `_compute_xml_id` |
| `help` | Html |  |  | yes |  | Action Description |  |
| `binding_model_id` | Many2one | `ir.model` |  | yes |  |  |  |
| `binding_type` | Selection |  | yes | yes | `action` Action, `report` Report; default: `'action'` |  |  |
| `binding_view_types` | Char |  |  | yes | default: `'list,form'` |  |  |

## `ir.actions.client`

Table `ir_act_client`.
Description: Client Action.
Inherits: `ir.actions.actions`.
Order: `name`.
Source: `ir_actions.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `type` | Char |  |  | yes | default: `'ir.actions.client'` |  |  |
| `tag` | Char |  | yes | yes |  | Client action tag |  |
| `target` | Selection |  |  | yes | `current` Current Window, `new` New Window, `fullscreen` Full Screen, `main` Main action of Current Window; default: `'current'` | Target Window |  |
| `res_model` | Char |  |  | yes |  | Destination Model |  |
| `context` | Char |  | yes | yes | default: `'{}'` | Context Value |  |
| `params` | Binary |  |  | no |  | Supplementary arguments | compute `_compute_params` |
| `params_store` | Binary |  |  | yes |  | Params storage |  |

## `ir.actions.report`

Table `ir_act_report_xml`.
Description: Report Action.
Inherits: `ir.actions.actions`.
Order: `name, id`.
Source: `ir_actions_report.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `type` | Char |  |  | yes | default: `'ir.actions.report'` |  |  |
| `binding_type` | Selection |  |  | yes | default: `'report'` |  |  |
| `model` | Char |  | yes | yes |  | Model Name |  |
| `model_id` | Many2one | `ir.model` |  | no |  | Model | compute `_compute_model_id` |
| `report_type` | Selection |  | yes | yes | `qweb-html` HTML, `qweb-pdf` PDF, `qweb-text` Text; default: `'qweb-pdf'` |  |  |
| `report_name` | Char |  | yes | yes |  | Template Name |  |
| `report_file` | Char |  |  | yes |  | Report File |  |
| `groups_id` | Many2many | `res.groups` (table `res_groups_report_rel`) |  | yes |  | Groups |  |
| `multi` | Boolean |  |  | yes |  | On Multiple Doc. |  |
| `paperformat_id` | Many2one | `report.paperformat` |  | yes |  | Paper Format |  |
| `print_report_name` | Char |  |  | yes |  | Printed Report Name |  |
| `attachment_use` | Boolean |  |  | yes |  | Reload from Attachment |  |
| `attachment` | Char |  |  | yes |  | Save as Attachment Prefix |  |

## `ir.actions.server`

Table `ir_act_server`.
Description: Server Actions.
Inherits: `ir.actions.actions`.
Order: `sequence,name`.
Source: `ir_actions.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `type` | Char |  |  | yes | default: `'ir.actions.server'` |  |  |
| `usage` | Selection |  | yes | yes | `ir_actions_server` Server Action, `ir_cron` Scheduled Action; default: `'ir_actions_server'` | Usage |  |
| `state` | Selection |  | yes | yes | `object_write` Update Record, `object_create` Create Record, `code` Execute Code, `webhook` Send Webhook Notification, `multi` Execute Existing Actions; default: `'object_write'` | Type |  |
| `sequence` | Integer |  |  | yes | default: `5` |  |  |
| `model_id` | Many2one | `ir.model` | yes | yes |  | Model |  |
| `available_model_ids` | Many2many | `ir.model` |  | no |  | Available Models | compute `_compute_available_model_ids` |
| `model_name` | Char |  |  | yes |  | Model Name | related `model_id.model` |
| `code` | Text |  |  | yes | default: (computed) | Python Code |  |
| `child_ids` | Many2many | `ir.actions.server` (table `rel_server_actions`) |  | yes |  | Child Actions |  |
| `crud_model_id` | Many2one | `ir.model` |  | yes |  | Record to Create | compute `_compute_crud_relations` |
| `crud_model_name` | Char |  |  | no |  | Target Model Name | related `crud_model_id.model` |
| `link_field_id` | Many2one | `ir.model.fields` |  | yes |  | Link Field | compute `_compute_link_field_id` |
| `groups_id` | Many2many | `res.groups` (table `ir_act_server_group_rel`) |  | yes |  | Allowed Groups |  |
| `update_field_id` | Many2one | `ir.model.fields` |  | yes |  | Field to Update | compute `_compute_crud_relations` |
| `update_path` | Char |  |  | yes | default: (computed) | Field to Update Path |  |
| `update_related_model_id` | Many2one | `ir.model` |  | yes |  |  | compute `_compute_crud_relations` |
| `update_field_type` | Selection |  |  | no |  |  | related `update_field_id.ttype` |
| `update_m2m_operation` | Selection |  |  | yes | `add` Adding, `remove` Removing, `set` Setting it to, `clear` Clearing it; default: `'add'` | Many2many Operations |  |
| `update_boolean_value` | Selection |  |  | yes | `true` Yes (True), `false` No (False); default: `'true'` | Boolean Value |  |
| `value` | Text |  |  | yes |  |  |  |
| `evaluation_type` | Selection |  |  | yes | `value` Update, `equation` Compute; default: `'value'` | Value Type |  |
| `resource_ref` | Reference |  |  | yes | (dynamic: '_selection_target_model') | Record |  |
| `selection_value` | Many2one | `ir.model.fields.selection` |  | yes |  | Custom Value |  |
| `value_field_to_show` | Selection |  |  | no | `value` value, `resource_ref` reference, `update_boolean_value` update_boolean_value, `selection_value` selection_value |  | compute `_compute_value_field_to_show` |
| `webhook_url` | Char |  |  | yes |  | Webhook URL |  |
| `webhook_field_ids` | Many2many | `ir.model.fields` (table `ir_act_server_webhook_field_rel`) |  | yes |  | Webhook Fields |  |
| `webhook_sample_payload` | Text |  |  | no |  | Sample Payload | compute `_compute_webhook_sample_payload` |

## `ir.actions.todo`

Table `ir_actions_todo`.
Description: Configuration Wizards.
Order: `sequence, id`.
Display name field: `action_id`.
Source: `ir_actions.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `action_id` | Many2one | `ir.actions.actions` | yes | yes |  | Action |  |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |
| `state` | Selection |  | yes | yes | `open` To Do, `done` Done; default: `'open'` | Status |  |
| `name` | Char |  |  | yes |  |  |  |

## `ir.asset`

Table `ir_asset`.
Description: Asset.
Order: `sequence, id`.
Source: `ir_asset.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `bundle` | Char |  | yes | yes |  | Bundle name |  |
| `directive` | Selection |  |  | yes | (dynamic: [(APPEND_DIRECTIVE, 'Append'), (PREPEND_DIRECTIVE, 'Prepend'), (AFTER_DIRECTIVE, 'After'), (BEFORE_DIRECTIVE, 'Before'), (REMOVE_DIRECTIVE, 'Remove'), (REPLACE_DIRECTIVE, 'Replace'), (INCLUDE_DIRECTIVE, 'Include')]); default: (computed) | Directive |  |
| `path` | Char |  | yes | yes |  | Path (or glob pattern) |  |
| `target` | Char |  |  | yes |  | Target |  |
| `active` | Boolean |  |  | yes | default: `True` | active |  |
| `sequence` | Integer |  | yes | yes | default: (computed) | Sequence |  |

## `ir.attachment`

Table `ir_attachment`.
Description: Attachment.
Order: `id desc`.
Source: `ir_attachment.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `description` | Text |  |  | yes |  | Description |  |
| `res_name` | Char |  |  | no |  | Resource Name | compute `_compute_res_name` |
| `res_model` | Char |  |  | yes |  | Resource Model |  |
| `res_field` | Char |  |  | yes |  | Resource Field |  |
| `res_id` | Many2oneReference | `Resource ID` |  | yes |  |  |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `type` | Selection |  | yes | yes | `url` URL, `binary` File; default: `'binary'` | Type |  |
| `url` | Char |  |  | yes |  | Url |  |
| `public` | Boolean |  |  | yes |  | Is public document |  |
| `access_token` | Char |  |  | yes |  | Access Token |  |
| `raw` | Binary |  |  | no |  | File Content (raw) | compute `_compute_raw` |
| `datas` | Binary |  |  | no |  | File Content (base64) | compute `_compute_datas` |
| `db_datas` | Binary |  |  | yes |  | Database Data |  |
| `store_fname` | Char |  |  | yes |  | Stored Filename |  |
| `file_size` | Integer |  |  | yes |  | File Size |  |
| `checksum` | Char |  |  | yes |  | Checksum/SHA1 |  |
| `mimetype` | Char |  |  | yes |  | Mime Type |  |
| `index_content` | Text |  |  | yes |  | Indexed Content |  |

## `ir.autovacuum`

Abstract model (mixin), no table of its own.
Description: Automatic Vacuum.
Source: `ir_autovacuum.py`.

## `ir.binary`

Abstract model (mixin), no table of its own.
Description: File streaming helper model for controllers.
Source: `ir_binary.py`.

## `ir.config_parameter`

Table `ir_config_parameter`.
Description: System Parameter.
Order: `key`.
Display name field: `key`.
Source: `ir_config_parameter.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `key` | Char |  | yes | yes |  |  |  |
| `value` | Text |  | yes | yes |  |  |  |

SQL constraints:

- `key_uniq`: `unique (key)`

## `ir.cron`

Table `ir_cron`.
Description: Scheduled Actions.
Order: `cron_name`.
Source: `ir_cron.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `ir_actions_server_id` | Many2one | `ir.actions.server` | yes | yes |  | Server action |  |
| `cron_name` | Char |  |  | yes |  | Name | compute `_compute_cron_name` |
| `user_id` | Many2one | `res.users` | yes | yes | default: (computed) | Scheduler User |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `interval_number` | Integer |  |  | yes | default: `1` |  |  |
| `interval_type` | Selection |  |  | yes | `minutes` Minutes, `hours` Hours, `days` Days, `weeks` Weeks, `months` Months; default: `'months'` | Interval Unit |  |
| `numbercall` | Integer |  |  | yes | default: `1` | Number of Calls |  |
| `doall` | Boolean |  |  | yes |  | Repeat Missed |  |
| `nextcall` | Datetime |  | yes | yes | default: (computed) | Next Execution Date |  |
| `lastcall` | Datetime |  |  | yes |  | Last Execution Date |  |
| `priority` | Integer |  |  | yes | default: `5` |  |  |

## `ir.cron.trigger`

Table `ir_cron_trigger`.
Description: Triggered actions.
Display name field: `cron_id`.
Source: `ir_cron.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `cron_id` | Many2one | `ir.cron` |  | yes |  |  |  |
| `call_at` | Datetime |  |  | yes |  |  |  |

## `ir.default`

Table `ir_default`.
Description: Default Values.
Display name field: `field_id`.
Source: `ir_default.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `field_id` | Many2one | `ir.model.fields` | yes | yes |  | Field |  |
| `user_id` | Many2one | `res.users` |  | yes |  | User |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company |  |
| `condition` | Char |  |  | yes |  | Condition |  |
| `json_value` | Char |  | yes | yes |  | Default Value (JSON format) |  |

## `ir.demo`

Transient model (wizard), table `ir_demo`, rows purged.
Description: Demo.
Source: `ir_demo.py`.

## `ir.demo_failure`

Transient model (wizard), table `ir_demo_failure`, rows purged.
Description: Demo failure.
Source: `ir_demo_failure.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `module_id` | Many2one | `ir.module.module` | yes | yes |  | Module |  |
| `error` | Char |  |  | yes |  | Error |  |
| `wizard_id` | Many2one | `ir.demo_failure.wizard` |  | yes |  |  |  |

## `ir.demo_failure.wizard`

Transient model (wizard), table `ir_demo_failure_wizard`, rows purged.
Description: Demo Failure wizard.
Source: `ir_demo_failure.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `failure_ids` | One2many | `ir.demo_failure` (inverse `wizard_id`) |  | no (inverse) |  | Demo Installation Failures |  |
| `failures_count` | Integer |  |  | no |  |  | compute `_compute_failures_count` |

## `ir.exports`

Table `ir_exports`.
Description: Exports.
Order: `name`.
Source: `ir_exports.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  | Export Name |  |
| `resource` | Char |  |  | yes |  |  |  |
| `export_fields` | One2many | `ir.exports.line` (inverse `export_id`) |  | no (inverse) |  | Export ID |  |

## `ir.exports.line`

Table `ir_exports_line`.
Description: Exports Line.
Order: `id`.
Source: `ir_exports.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  | Field Name |  |
| `export_id` | Many2one | `ir.exports` |  | yes |  | Export |  |

## `ir.fields.converter`

Abstract model (mixin), no table of its own.
Description: Fields Converter.
Source: `ir_fields.py`.

## `ir.filters`

Table `ir_filters`.
Description: Filters.
Order: `model_id, name, id desc`.
Source: `ir_filters.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Filter Name |  |
| `user_id` | Many2one | `res.users` |  | yes |  | User |  |
| `domain` | Text |  | yes | yes | default: `'[]'` |  |  |
| `context` | Text |  | yes | yes | default: `'{}'` |  |  |
| `sort` | Text |  | yes | yes | default: `'[]'` |  |  |
| `model_id` | Selection |  | yes | yes | (dynamic: '_list_all_models') | Model |  |
| `is_default` | Boolean |  |  | yes |  | Default Filter |  |
| `action_id` | Many2one | `ir.actions.actions` |  | yes |  | Action |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |

SQL constraints:

- `name_model_uid_unique`: `unique (model_id, user_id, action_id, name)`

## `ir.http`

Abstract model (mixin), no table of its own.
Description: HTTP Routing.
Source: `ir_http.py`.

## `ir.logging`

Table `ir_logging`.
Description: Logging.
Order: `id DESC`.
Source: `ir_logging.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `create_uid` | Integer |  |  | yes |  | Created by |  |
| `create_date` | Datetime |  |  | yes |  | Created on |  |
| `write_uid` | Integer |  |  | yes |  | Last Updated by |  |
| `write_date` | Datetime |  |  | yes |  | Last Updated on |  |
| `name` | Char |  | yes | yes |  |  |  |
| `type` | Selection |  | yes | yes | `client` Client, `server` Server |  |  |
| `dbname` | Char |  |  | yes |  | Database Name |  |
| `level` | Char |  |  | yes |  |  |  |
| `message` | Text |  | yes | yes |  |  |  |
| `path` | Char |  | yes | yes |  |  |  |
| `func` | Char |  | yes | yes |  | Function |  |
| `line` | Char |  | yes | yes |  |  |  |

## `ir.mail_server`

Table `ir_mail_server`.
Description: Mail Server.
Order: `sequence, id`.
Source: `ir_mail_server.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `from_filter` | Char |  |  | yes |  | FROM Filtering |  |
| `smtp_host` | Char |  |  | yes |  | SMTP Server |  |
| `smtp_port` | Integer |  |  | yes | default: `25` | SMTP Port |  |
| `smtp_authentication` | Selection |  | yes | yes | `login` Username, `certificate` SSL Certificate, `cli` Command Line Interface; default: `'login'` | Authenticate with |  |
| `smtp_authentication_info` | Text |  |  | no |  | Authentication Info | compute `_compute_smtp_authentication_info` |
| `smtp_user` | Char |  |  | yes |  | Username |  |
| `smtp_pass` | Char |  |  | yes |  | Password |  |
| `smtp_encryption` | Selection |  | yes | yes | `none` None, `starttls` TLS (STARTTLS), `ssl` SSL/TLS; default: `'none'` | Connection Encryption |  |
| `smtp_ssl_certificate` | Binary |  |  | yes |  | SSL Certificate |  |
| `smtp_ssl_private_key` | Binary |  |  | yes |  | SSL Private Key |  |
| `smtp_debug` | Boolean |  |  | yes |  | Debugging |  |
| `sequence` | Integer |  |  | yes | default: `10` | Priority |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |

## `ir.model`

Table `ir_model`.
Description: Models.
Order: `model`.
Source: `ir_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Model Description |  |
| `model` | Char |  | yes | yes | default: `'x_'` |  |  |
| `order` | Char |  | yes | yes | default: `'id'` | Order |  |
| `info` | Text |  |  | yes |  | Information |  |
| `field_id` | One2many | `ir.model.fields` (inverse `model_id`) | yes | no (inverse) | default: (computed) | Fields |  |
| `inherited_model_ids` | Many2many | `ir.model` |  | no |  | Inherited models | compute `_inherited_models` |
| `state` | Selection |  |  | yes | `manual` Custom Object, `base` Base Object; default: `'manual'` | Type |  |
| `access_ids` | One2many | `ir.model.access` (inverse `model_id`) |  | no (inverse) |  | Access |  |
| `rule_ids` | One2many | `ir.rule` (inverse `model_id`) |  | no (inverse) |  | Record Rules |  |
| `transient` | Boolean |  |  | yes |  | Transient Model |  |
| `modules` | Char |  |  | no |  | In Apps | compute `_in_modules` |
| `view_ids` | One2many | `ir.ui.view` |  | no (inverse) |  | Views | compute `_view_ids` |
| `count` | Integer |  |  | no |  | Count (Incl. Archived) | compute `_compute_count` |

SQL constraints:

- `obj_name_uniq`: `unique (model)`

## `ir.model.access`

Table `ir_model_access`.
Description: Model Access.
Order: `model_id,group_id,name,id`.
Source: `ir_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `model_id` | Many2one | `ir.model` | yes | yes |  | Model |  |
| `group_id` | Many2one | `res.groups` |  | yes |  | Group |  |
| `perm_read` | Boolean |  |  | yes |  | Read Access |  |
| `perm_write` | Boolean |  |  | yes |  | Write Access |  |
| `perm_create` | Boolean |  |  | yes |  | Create Access |  |
| `perm_unlink` | Boolean |  |  | yes |  | Delete Access |  |

## `ir.model.constraint`

Table `ir_model_constraint`.
Description: Model Constraint.
Source: `ir_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Constraint |  |
| `definition` | Char |  |  | yes |  |  |  |
| `message` | Char |  |  | yes |  |  |  |
| `model` | Many2one | `ir.model` | yes | yes |  |  |  |
| `module` | Many2one | `ir.module.module` | yes | yes |  |  |  |
| `type` | Char |  | yes | yes |  | Constraint Type |  |
| `write_date` | Datetime |  |  | yes |  |  |  |
| `create_date` | Datetime |  |  | yes |  |  |  |

SQL constraints:

- `module_name_uniq`: `unique(name, module)`

## `ir.model.data`

Table `ir_model_data`.
Description: Model Data.
Order: `module, model, name`.
Source: `ir_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | External Identifier |  |
| `complete_name` | Char |  |  | no |  | Complete ID | compute `_compute_complete_name` |
| `model` | Char |  | yes | yes |  | Model Name |  |
| `module` | Char |  | yes | yes | default: `''` |  |  |
| `res_id` | Many2oneReference | (redefines inherited field) |  | yes |  | Record ID |  |
| `noupdate` | Boolean |  |  | yes | default: `False` | Non Updatable |  |
| `reference` | Char |  |  | no |  | Reference | compute `_compute_reference` |

SQL constraints:

- `name_nospaces`: `CHECK(name NOT LIKE '% %')`

## `ir.model.fields`

Table `ir_model_fields`.
Description: Fields.
Order: `name`.
Display name field: `field_description`.
Source: `ir_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: `'x_'` | Field Name |  |
| `complete_name` | Char |  |  | yes |  |  |  |
| `model` | Char |  | yes | yes |  | Model Name |  |
| `relation` | Char |  |  | yes |  | Related Model |  |
| `relation_field` | Char |  |  | yes |  |  |  |
| `relation_field_id` | Many2one | `ir.model.fields` |  | yes |  | Relation field | compute `_compute_relation_field_id` |
| `model_id` | Many2one | `ir.model` | yes | yes |  | Model |  |
| `field_description` | Char |  | yes | yes | default: `''` | Field Label |  |
| `help` | Text |  |  | yes |  | Field Help |  |
| `ttype` | Selection |  | yes | yes | (dynamic: FIELD_TYPES) | Field Type |  |
| `selection` | Char |  |  | no |  | Selection Options (Deprecated) | compute `_compute_selection` |
| `selection_ids` | One2many | `ir.model.fields.selection` (inverse `field_id`) |  | no (inverse) |  | Selection Options |  |
| `copied` | Boolean |  |  | yes |  | Copied | compute `_compute_copied` |
| `related` | Char |  |  | yes |  | Related Field |  |
| `related_field_id` | Many2one | `ir.model.fields` |  | yes |  | Related field | compute `_compute_related_field_id` |
| `required` | Boolean |  |  | yes |  |  |  |
| `readonly` | Boolean |  |  | yes |  |  |  |
| `index` | Boolean |  |  | yes |  | Indexed |  |
| `translate` | Boolean |  |  | yes |  | Translatable |  |
| `size` | Integer |  |  | yes |  |  |  |
| `state` | Selection |  | yes | yes | `manual` Custom Field, `base` Base Field; default: `'manual'` | Type |  |
| `on_delete` | Selection |  |  | yes | `cascade` Cascade, `set null` Set NULL, `restrict` Restrict; default: `'set null'` | On Delete |  |
| `domain` | Char |  |  | yes | default: `'[]'` |  |  |
| `groups` | Many2many | `res.groups` (table `ir_model_fields_group_rel`) |  | yes |  |  |  |
| `group_expand` | Boolean |  |  | yes |  | Expand Groups |  |
| `selectable` | Boolean |  |  | yes | default: `True` |  |  |
| `modules` | Char |  |  | no |  | In Apps | compute `_in_modules` |
| `relation_table` | Char |  |  | yes |  |  |  |
| `column1` | Char |  |  | yes |  | Column 1 |  |
| `column2` | Char |  |  | yes |  | Column 2 |  |
| `compute` | Text |  |  | yes |  |  |  |
| `depends` | Char |  |  | yes |  | Dependencies |  |
| `store` | Boolean |  |  | yes | default: `True` | Stored |  |
| `currency_field` | Char |  |  | yes |  | Currency field |  |
| `sanitize` | Boolean |  |  | yes | default: `True` | Sanitize HTML |  |
| `sanitize_overridable` | Boolean |  |  | yes | default: `False` | Sanitize HTML overridable |  |
| `sanitize_tags` | Boolean |  |  | yes | default: `True` | Sanitize HTML Tags |  |
| `sanitize_attributes` | Boolean |  |  | yes | default: `True` | Sanitize HTML Attributes |  |
| `sanitize_style` | Boolean |  |  | yes | default: `False` | Sanitize HTML Style |  |
| `sanitize_form` | Boolean |  |  | yes | default: `True` | Sanitize HTML Form |  |
| `strip_style` | Boolean |  |  | yes | default: `False` | Strip Style Attribute |  |
| `strip_classes` | Boolean |  |  | yes | default: `False` | Strip Class Attribute |  |

SQL constraints:

- `name_unique`: `UNIQUE(model, name)`
- `size_gt_zero`: `CHECK (size>=0)`
- `name_manual_field`: `CHECK (state != 'manual' OR name LIKE 'x\_%')`

## `ir.model.fields.selection`

Table `ir_model_fields_selection`.
Description: Fields Selection.
Order: `sequence, id`.
Source: `ir_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `field_id` | Many2one | `ir.model.fields` | yes | yes |  |  |  |
| `value` | Char |  | yes | yes |  |  |  |
| `name` | Char |  | yes | yes |  |  |  |
| `sequence` | Integer |  |  | yes | default: `1000` |  |  |

SQL constraints:

- `selection_field_uniq`: `unique(field_id, value)`

## `ir.model.inherit`

Table `ir_model_inherit`.
Description: Model Inheritance Tree.
Source: `ir_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `model_id` | Many2one | `ir.model` | yes | yes |  |  |  |
| `parent_id` | Many2one | `ir.model` | yes | yes |  |  |  |
| `parent_field_id` | Many2one | `ir.model.fields` |  | yes |  |  |  |

SQL constraints:

- `uniq`: `UNIQUE(model_id, parent_id)`

## `ir.model.relation`

Table `ir_model_relation`.
Description: Relation Model.
Source: `ir_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Relation Name |  |
| `model` | Many2one | `ir.model` | yes | yes |  |  |  |
| `module` | Many2one | `ir.module.module` | yes | yes |  |  |  |
| `write_date` | Datetime |  |  | yes |  |  |  |
| `create_date` | Datetime |  |  | yes |  |  |  |

## `ir.module.category`

Table `ir_module_category`.
Description: Application.
Order: `name`.
Source: `ir_module.py`, `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `parent_id` | Many2one | `ir.module.category` |  | yes |  | Parent Application |  |
| `child_ids` | One2many | `ir.module.category` (inverse `parent_id`) |  | no (inverse) |  | Child Applications |  |
| `module_ids` | One2many | `ir.module.module` (inverse `category_id`) |  | no (inverse) |  | Modules |  |
| `description` | Text |  |  | yes |  | Description |  |
| `sequence` | Integer |  |  | yes |  | Sequence |  |
| `visible` | Boolean |  |  | yes | default: `True` | Visible |  |
| `exclusive` | Boolean |  |  | yes |  | Exclusive |  |
| `xml_id` | Char |  |  | no |  | External ID | compute `_compute_xml_id` |

## `ir.module.module`

Table `ir_module_module`.
Description: Module.
Order: `application desc,sequence,name`.
Display name field: `shortdesc`.
Source: `ir_module.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Technical Name |  |
| `category_id` | Many2one | `ir.module.category` |  | yes |  | Category |  |
| `shortdesc` | Char |  |  | yes |  | Module Name |  |
| `summary` | Char |  |  | yes |  | Summary |  |
| `description` | Text |  |  | yes |  | Description |  |
| `description_html` | Html |  |  | no |  | Description HTML | compute `_get_desc` |
| `author` | Char |  |  | yes |  | Author |  |
| `maintainer` | Char |  |  | yes |  | Maintainer |  |
| `contributors` | Text |  |  | yes |  | Contributors |  |
| `website` | Char |  |  | yes |  | Website |  |
| `installed_version` | Char |  |  | no |  | Latest Version | compute `_get_latest_version` |
| `latest_version` | Char |  |  | yes |  | Installed Version |  |
| `published_version` | Char |  |  | yes |  | Published Version |  |
| `url` | Char |  |  | yes |  | URL |  |
| `sequence` | Integer |  |  | yes | default: `100` | Sequence |  |
| `dependencies_id` | One2many | `ir.module.module.dependency` (inverse `module_id`) |  | no (inverse) |  | Dependencies |  |
| `exclusion_ids` | One2many | `ir.module.module.exclusion` (inverse `module_id`) |  | no (inverse) |  | Exclusions |  |
| `auto_install` | Boolean |  |  | yes |  | Automatic Installation |  |
| `state` | Selection |  |  | yes | `uninstallable` Uninstallable, `uninstalled` Not Installed, `installed` Installed, `to upgrade` To be upgraded, `to remove` To be removed, `to install` To be installed; default: `'uninstallable'` | Status |  |
| `demo` | Boolean |  |  | yes | default: `False` | Demo Data |  |
| `license` | Selection |  |  | yes | `GPL-2` GPL Version 2, `GPL-2 or any later version` GPL-2 or later version, `GPL-3` GPL Version 3, `GPL-3 or any later version` GPL-3 or later version, `AGPL-3` Affero GPL-3, `LGPL-3` LGPL Version 3, `Other OSI approved licence` Other OSI Approved License, `OEEL-1` Odoo Enterprise Edition License v1.0, `OPL-1` Odoo Proprietary License v1.0, `Other proprietary` Other Proprietary; default: `'LGPL-3'` | License |  |
| `menus_by_module` | Text |  |  | yes |  | Menus | compute `_get_views` |
| `reports_by_module` | Text |  |  | yes |  | Reports | compute `_get_views` |
| `views_by_module` | Text |  |  | yes |  | Views | compute `_get_views` |
| `application` | Boolean |  |  | yes |  | Application |  |
| `icon` | Char |  |  | yes |  | Icon URL |  |
| `icon_image` | Binary |  |  | no |  | Icon | compute `_get_icon_image` |
| `icon_flag` | Char |  |  | no |  | Flag | compute `_get_icon_image` |
| `to_buy` | Boolean |  |  | yes | default: `False` | Odoo Enterprise Module |  |
| `has_iap` | Boolean |  |  | no |  |  | compute `_compute_has_iap` |

SQL constraints:

- `name_uniq`: `UNIQUE (name)`

## `ir.module.module.dependency`

Table `ir_module_module_dependency`.
Description: Module dependency.
Source: `ir_module.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  |  |  |
| `module_id` | Many2one | `ir.module.module` |  | yes |  | Module |  |
| `depend_id` | Many2one | `ir.module.module` |  | no |  | Dependency | compute `_compute_depend` |
| `state` | Selection |  |  | no | `uninstallable` Uninstallable, `uninstalled` Not Installed, `installed` Installed, `to upgrade` To be upgraded, `to remove` To be removed, `to install` To be installed, `unknown` Unknown | Status | compute `_compute_state` |
| `auto_install_required` | Boolean |  |  | yes | default: `True` |  |  |

## `ir.module.module.exclusion`

Table `ir_module_module_exclusion`.
Description: Module exclusion.
Source: `ir_module.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  |  |  |
| `module_id` | Many2one | `ir.module.module` |  | yes |  | Module |  |
| `exclusion_id` | Many2one | `ir.module.module` |  | no |  | Exclusion Module | compute `_compute_exclusion` |
| `state` | Selection |  |  | no | `uninstallable` Uninstallable, `uninstalled` Not Installed, `installed` Installed, `to upgrade` To be upgraded, `to remove` To be removed, `to install` To be installed, `unknown` Unknown | Status | compute `_compute_state` |

## `ir.profile`

Table `ir_profile`.
Description: Profiling results.
Order: `session desc, id desc`.
Source: `ir_profile.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `create_date` | Datetime |  |  | yes |  | Creation Date |  |
| `session` | Char |  |  | yes |  | Session |  |
| `name` | Char |  |  | yes |  | Description |  |
| `duration` | Float |  |  | yes |  | Duration |  |
| `init_stack_trace` | Text |  |  | yes |  | Initial stack trace |  |
| `sql` | Text |  |  | yes |  | Sql |  |
| `sql_count` | Integer |  |  | yes |  | Queries Count |  |
| `traces_async` | Text |  |  | yes |  | Traces Async |  |
| `traces_sync` | Text |  |  | yes |  | Traces Sync |  |
| `qweb` | Text |  |  | yes |  | Qweb |  |
| `entry_count` | Integer |  |  | yes |  | Entry count |  |
| `speedscope` | Binary |  |  | no |  | Speedscope | compute `_compute_speedscope` |
| `speedscope_url` | Text |  |  | no |  | Open | compute `_compute_speedscope_url` |

## `ir.property`

Table `ir_property`.
Description: Company Property.
Source: `ir_property.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  |  |  |
| `res_id` | Char |  |  | yes |  | Resource |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company |  |
| `fields_id` | Many2one | `ir.model.fields` | yes | yes |  | Field |  |
| `value_float` | Float |  |  | yes |  |  |  |
| `value_integer` | Integer |  |  | yes |  |  |  |
| `value_text` | Text |  |  | yes |  |  |  |
| `value_binary` | Binary |  |  | yes |  |  |  |
| `value_reference` | Char |  |  | yes |  |  |  |
| `value_datetime` | Datetime |  |  | yes |  |  |  |
| `type` | Selection |  | yes | yes | `char` Char, `float` Float, `boolean` Boolean, `integer` Integer, `text` Text, `binary` Binary, `many2one` Many2One, `date` Date, `datetime` DateTime, `selection` Selection, `html` Html; default: `'many2one'` |  |  |

## `ir.qweb`

Abstract model (mixin), no table of its own.
Description: Qweb.
Source: `ir_qweb.py`.

## `ir.qweb.field`

Abstract model (mixin), no table of its own.
Description: Qweb Field.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.barcode`

Abstract model (mixin), no table of its own.
Description: Qweb Field Barcode.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.contact`

Abstract model (mixin), no table of its own.
Description: Qweb Field Contact.
Inherits: `ir.qweb.field.many2one`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.date`

Abstract model (mixin), no table of its own.
Description: Qweb Field Date.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.datetime`

Abstract model (mixin), no table of its own.
Description: Qweb Field Datetime.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.duration`

Abstract model (mixin), no table of its own.
Description: Qweb Field Duration.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.float`

Abstract model (mixin), no table of its own.
Description: Qweb Field Float.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.float_time`

Abstract model (mixin), no table of its own.
Description: Qweb Field Float Time.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.html`

Abstract model (mixin), no table of its own.
Description: Qweb Field HTML.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.image`

Abstract model (mixin), no table of its own.
Description: Qweb Field Image.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.image_url`

Abstract model (mixin), no table of its own.
Description: Qweb Field Image.
Inherits: `ir.qweb.field.image`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.integer`

Abstract model (mixin), no table of its own.
Description: Qweb Field Integer.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.many2many`

Abstract model (mixin), no table of its own.
Description: Qweb field many2many.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.many2one`

Abstract model (mixin), no table of its own.
Description: Qweb Field Many to One.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.monetary`

Abstract model (mixin), no table of its own.
Description: Qweb Field Monetary.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.one2many`

Abstract model (mixin), no table of its own.
Description: Qweb field one2many.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.qweb`

Abstract model (mixin), no table of its own.
Description: Qweb Field qweb.
Inherits: `ir.qweb.field.many2one`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.relative`

Abstract model (mixin), no table of its own.
Description: Qweb Field Relative.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.selection`

Abstract model (mixin), no table of its own.
Description: Qweb Field Selection.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.text`

Abstract model (mixin), no table of its own.
Description: Qweb Field Text.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.qweb.field.time`

Abstract model (mixin), no table of its own.
Description: QWeb Field Time.
Inherits: `ir.qweb.field`.
Source: `ir_qweb_fields.py`.

## `ir.rule`

Table `ir_rule`.
Description: Record Rule.
Order: `model_id DESC,id`.
Source: `ir_rule.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  |  |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `model_id` | Many2one | `ir.model` | yes | yes |  | Model |  |
| `groups` | Many2many | `res.groups` (table `rule_group_rel`) |  | yes |  |  |  |
| `domain_force` | Text |  |  | yes |  | Domain |  |
| `perm_read` | Boolean |  |  | yes | default: `True` | Read |  |
| `perm_write` | Boolean |  |  | yes | default: `True` | Write |  |
| `perm_create` | Boolean |  |  | yes | default: `True` | Create |  |
| `perm_unlink` | Boolean |  |  | yes | default: `True` | Delete |  |

SQL constraints:

- `no_access_rights`: `CHECK (perm_read!=False or perm_write!=False or perm_create!=False or perm_unlink!=False)`

## `ir.sequence`

Table `ir_sequence`.
Description: Sequence.
Order: `name`.
Source: `ir_sequence.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `code` | Char |  |  | yes |  | Sequence Code |  |
| `implementation` | Selection |  | yes | yes | `standard` Standard, `no_gap` No gap; default: `'standard'` | Implementation |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `prefix` | Char |  |  | yes |  |  |  |
| `suffix` | Char |  |  | yes |  |  |  |
| `number_next` | Integer |  | yes | yes | default: `1` | Next Number |  |
| `number_next_actual` | Integer |  |  | no |  | Actual Next Number | compute `_get_number_next_actual` |
| `number_increment` | Integer |  | yes | yes | default: `1` | Step |  |
| `padding` | Integer |  | yes | yes | default: `0` | Sequence Size |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `use_date_range` | Boolean |  |  | yes |  | Use subsequences per date_range |  |
| `date_range_ids` | One2many | `ir.sequence.date_range` (inverse `sequence_id`) |  | no (inverse) |  | Subsequences |  |

## `ir.sequence.date_range`

Table `ir_sequence_date_range`.
Description: Sequence Date Range.
Display name field: `sequence_id`.
Source: `ir_sequence.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `date_from` | Date |  | yes | yes |  | From |  |
| `date_to` | Date |  | yes | yes |  | To |  |
| `sequence_id` | Many2one | `ir.sequence` | yes | yes |  | Main Sequence |  |
| `number_next` | Integer |  | yes | yes | default: `1` | Next Number |  |
| `number_next_actual` | Integer |  |  | no |  | Actual Next Number | compute `_get_number_next_actual` |

SQL constraints:

- `unique_range_per_sequence`: `UNIQUE(sequence_id, date_from, date_to)`

## `ir.ui.menu`

Table `ir_ui_menu`.
Description: Menu.
Order: `sequence,id`.
Source: `ir_ui_menu.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Menu |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |
| `child_id` | One2many | `ir.ui.menu` (inverse `parent_id`) |  | no (inverse) |  | Child IDs |  |
| `parent_id` | Many2one | `ir.ui.menu` |  | yes |  | Parent Menu |  |
| `parent_path` | Char |  |  | yes |  |  |  |
| `groups_id` | Many2many | `res.groups` (table `ir_ui_menu_group_rel`) |  | yes |  | Groups |  |
| `complete_name` | Char |  |  | no |  | Full Path | compute `_compute_complete_name` |
| `web_icon` | Char |  |  | yes |  | Web Icon File |  |
| `action` | Reference |  |  | yes | `ir.actions.report` ir.actions.report, `ir.actions.act_window` ir.actions.act_window, `ir.actions.act_url` ir.actions.act_url, `ir.actions.server` ir.actions.server, `ir.actions.client` ir.actions.client |  |  |
| `web_icon_data` | Binary |  |  | yes |  | Web Icon Image |  |

## `ir.ui.view`

Table `ir_ui_view`.
Description: View.
Order: `priority,name,id`.
Source: `ir_ui_view.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | View Name |  |
| `model` | Char |  |  | yes |  |  |  |
| `key` | Char |  |  | yes |  |  |  |
| `priority` | Integer |  | yes | yes | default: `16` | Sequence |  |
| `type` | Selection |  |  | yes | `tree` Tree, `form` Form, `graph` Graph, `pivot` Pivot, `calendar` Calendar, `gantt` Gantt, `kanban` Kanban, `search` Search, `qweb` QWeb | View Type |  |
| `arch` | Text |  |  | no |  | View Architecture | compute `_compute_arch` |
| `arch_base` | Text |  |  | no |  | Base View Architecture | compute `_compute_arch_base` |
| `arch_db` | Text |  |  | yes |  | Arch Blob |  |
| `arch_fs` | Char |  |  | yes |  | Arch Filename |  |
| `arch_updated` | Boolean |  |  | yes |  | Modified Architecture |  |
| `arch_prev` | Text |  |  | yes |  | Previous View Architecture |  |
| `inherit_id` | Many2one | `ir.ui.view` |  | yes |  | Inherited View |  |
| `inherit_children_ids` | One2many | `ir.ui.view` (inverse `inherit_id`) |  | no (inverse) |  | Views which inherit from this one |  |
| `model_data_id` | Many2one | `ir.model.data` |  | no |  | Model Data | compute `_compute_model_data_id` |
| `xml_id` | Char |  |  | no |  | External ID | compute `_compute_xml_id` |
| `groups_id` | Many2many | `res.groups` (table `ir_ui_view_group_rel`) |  | yes |  | Groups |  |
| `mode` | Selection |  | yes | yes | `primary` Base view, `extension` Extension View; default: `'primary'` | View inheritance mode |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `model_id` | Many2one | `ir.model` |  | no |  | Model of the view | compute `_compute_model_id` |

SQL constraints:

- `inheritance_mode`: `CHECK (mode != 'extension' OR inherit_id IS NOT NULL)`
- `qweb_required_key`: `CHECK (type != 'qweb' OR key IS NOT NULL)`

## `ir.ui.view.custom`

Table `ir_ui_view_custom`.
Description: Custom View.
Order: `create_date desc`.
Display name field: `user_id`.
Source: `ir_ui_view.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `ref_id` | Many2one | `ir.ui.view` | yes | yes |  | Original View |  |
| `user_id` | Many2one | `res.users` | yes | yes |  | User |  |
| `arch` | Text |  | yes | yes |  | View Architecture |  |

## `pycompat.to_text(model_data['model'])`

Table `pycompat_to_text(model_data['model'])`.
Description: model_data['name'].
Order: `model_data['order']`.
Source: `ir_model.py`.

## `report.layout`

Table `report_layout`.
Description: Report Layout.
Order: `sequence`.
Source: `report_layout.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `view_id` | Many2one | `ir.ui.view` | yes | yes |  | Document Template |  |
| `image` | Char |  |  | yes |  | Preview image src |  |
| `pdf` | Char |  |  | yes |  | Preview pdf src |  |
| `sequence` | Integer |  |  | yes | default: `50` |  |  |
| `name` | Char |  |  | yes |  |  |  |

## `report.paperformat`

Table `report_paperformat`.
Description: Paper Format Config.
Source: `report_paperformat.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `default` | Boolean |  |  | yes |  | Default paper format? |  |
| `format` | Selection |  |  | yes | (dynamic: [(ps['key'], ps['description']) for ps in PAPER_SIZES]); default: `'A4'` | Paper size |  |
| `margin_top` | Float |  |  | yes | default: `40` | Top Margin (mm) |  |
| `margin_bottom` | Float |  |  | yes | default: `20` | Bottom Margin (mm) |  |
| `margin_left` | Float |  |  | yes | default: `7` | Left Margin (mm) |  |
| `margin_right` | Float |  |  | yes | default: `7` | Right Margin (mm) |  |
| `page_height` | Integer |  |  | yes | default: `False` | Page height (mm) |  |
| `page_width` | Integer |  |  | yes | default: `False` | Page width (mm) |  |
| `orientation` | Selection |  |  | yes | `Landscape` Landscape, `Portrait` Portrait; default: `'Landscape'` | Orientation |  |
| `header_line` | Boolean |  |  | yes | default: `False` | Display a header line |  |
| `header_spacing` | Integer |  |  | yes | default: `35` | Header spacing |  |
| `disable_shrinking` | Boolean |  |  | yes |  | Disable smart shrinking |  |
| `dpi` | Integer |  | yes | yes | default: `90` | Output DPI |  |
| `report_ids` | One2many | `ir.actions.report` (inverse `paperformat_id`) |  | no (inverse) |  | Associated reports |  |
| `print_page_width` | Float |  |  | no |  | Print page width (mm) | compute `_compute_print_page_size` |
| `print_page_height` | Float |  |  | no |  | Print page height (mm) | compute `_compute_print_page_size` |

## `res.bank`

Table `res_bank`.
Description: Bank.
Order: `name`.
Source: `res_bank.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `street` | Char |  |  | yes |  |  |  |
| `street2` | Char |  |  | yes |  |  |  |
| `zip` | Char |  |  | yes |  |  |  |
| `city` | Char |  |  | yes |  |  |  |
| `state` | Many2one | `res.country.state` |  | yes |  | Fed. State |  |
| `country` | Many2one | `res.country` |  | yes |  |  |  |
| `email` | Char |  |  | yes |  |  |  |
| `phone` | Char |  |  | yes |  |  |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `bic` | Char |  |  | yes |  | Bank Identifier Code |  |

## `res.company`

Table `res_company`.
Description: Companies.
Order: `sequence, name`.
Source: `res_company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Company Name | related `partner_id.name` |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |
| `parent_id` | Many2one | `res.company` |  | yes |  | Parent Company |  |
| `child_ids` | One2many | `res.company` (inverse `parent_id`) |  | no (inverse) |  | Branches |  |
| `all_child_ids` | One2many | `res.company` (inverse `parent_id`) |  | no (inverse) |  |  |  |
| `parent_path` | Char |  |  | yes |  |  |  |
| `parent_ids` | Many2many | `res.company` |  | no |  |  | compute `_compute_parent_ids` |
| `root_id` | Many2one | `res.company` |  | no |  |  | compute `_compute_parent_ids` |
| `partner_id` | Many2one | `res.partner` | yes | yes |  | Partner |  |
| `report_header` | Html |  |  | yes |  | Company Tagline |  |
| `report_footer` | Html |  |  | yes |  | Report Footer |  |
| `company_details` | Html |  |  | yes |  | Company Details |  |
| `is_company_details_empty` | Boolean |  |  | no |  |  | compute `_compute_empty_company_details` |
| `logo` | Binary |  |  | no | default: (computed) | Company Logo | related `partner_id.image_1920` |
| `logo_web` | Binary |  |  | yes |  |  | compute `_compute_logo_web` |
| `uses_default_logo` | Boolean |  |  | yes |  |  | compute `_compute_uses_default_logo` |
| `currency_id` | Many2one | `res.currency` | yes | yes | default: (computed) | Currency |  |
| `user_ids` | Many2many | `res.users` (table `res_company_users_rel`) |  | yes |  | Accepted Users |  |
| `street` | Char |  |  | no |  |  | compute `_compute_address` |
| `street2` | Char |  |  | no |  |  | compute `_compute_address` |
| `zip` | Char |  |  | no |  |  | compute `_compute_address` |
| `city` | Char |  |  | no |  |  | compute `_compute_address` |
| `state_id` | Many2one | `res.country.state` |  | no |  | Fed. State | compute `_compute_address` |
| `bank_ids` | One2many | (from related) |  | no (inverse) |  |  | related `partner_id.bank_ids` |
| `country_id` | Many2one | `res.country` |  | no |  | Country | compute `_compute_address` |
| `email` | Char |  |  | yes |  |  | related `partner_id.email` |
| `phone` | Char |  |  | yes |  |  | related `partner_id.phone` |
| `mobile` | Char |  |  | yes |  |  | related `partner_id.mobile` |
| `website` | Char |  |  | no |  |  | related `partner_id.website` |
| `vat` | Char |  |  | no |  | Tax ID | related `partner_id.vat` |
| `company_registry` | Char |  |  | no |  | Company ID | related `partner_id.company_registry` |
| `paperformat_id` | Many2one | `report.paperformat` |  | yes | default: (computed) | Paper format |  |
| `external_report_layout_id` | Many2one | `ir.ui.view` |  | yes |  | Document Template |  |
| `font` | Selection |  |  | yes | `Lato` Lato, `Roboto` Roboto, `Open_Sans` Open Sans, `Montserrat` Montserrat, `Oswald` Oswald, `Raleway` Raleway, `Tajawal` Tajawal; default: `'Lato'` |  |  |
| `primary_color` | Char |  |  | yes |  |  |  |
| `secondary_color` | Char |  |  | yes |  |  |  |
| `color` | Integer |  |  | no |  |  | compute `_compute_color` |
| `layout_background` | Selection |  | yes | yes | `Blank` Blank, `Geometric` Geometric, `Custom` Custom; default: `'Blank'` |  |  |
| `layout_background_image` | Binary |  |  | yes |  | Background Image |  |

SQL constraints:

- `name_uniq`: `unique (name)`

## `res.config`

Transient model (wizard), table `res_config`, rows purged.
Description: Config.
Source: `res_config.py`.

## `res.config.installer`

Transient model (wizard), table `res_config_installer`, rows purged.
Description: Config Installer.
Inherits: `res.config`.
Source: `res_config.py`.

## `res.config.settings`

Transient model (wizard), table `res_config_settings`, rows purged.
Description: Config Settings.
Source: `res_config.py`.

## `res.country`

Table `res_country`.
Description: Country.
Order: `name`.
Source: `res_country.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Country Name |  |
| `code` | Char |  | yes | yes |  | Country Code |  |
| `address_format` | Text |  |  | yes | default: `'%(street)s\n%(street2)s\n%(city)s %(state_code)s %(zip)s\n%(country_name)s'` | Layout in Reports |  |
| `address_view_id` | Many2one | `ir.ui.view` |  | yes |  | Input View |  |
| `currency_id` | Many2one | `res.currency` |  | yes |  | Currency |  |
| `image_url` | Char |  |  | no |  | Flag | compute `_compute_image_url` |
| `phone_code` | Integer |  |  | yes |  | Country Calling Code |  |
| `country_group_ids` | Many2many | `res.country.group` (table `res_country_res_country_group_rel`) |  | yes |  | Country Groups |  |
| `state_ids` | One2many | `res.country.state` (inverse `country_id`) |  | no (inverse) |  | States |  |
| `name_position` | Selection |  |  | yes | `before` Before Address, `after` After Address; default: `'before'` | Customer Name Position |  |
| `vat_label` | Char |  |  | yes |  | Vat Label |  |
| `state_required` | Boolean |  |  | yes | default: `False` |  |  |
| `zip_required` | Boolean |  |  | yes | default: `True` |  |  |

SQL constraints:

- `name_uniq`: `unique (name)`
- `code_uniq`: `unique (code)`

## `res.country.group`

Table `res_country_group`.
Description: Country Group.
Source: `res_country.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `country_ids` | Many2many | `res.country` (table `res_country_res_country_group_rel`) |  | yes |  | Countries |  |

## `res.country.state`

Table `res_country_state`.
Description: Country state.
Order: `code`.
Source: `res_country.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `country_id` | Many2one | `res.country` | yes | yes |  | Country |  |
| `name` | Char |  | yes | yes |  | State Name |  |
| `code` | Char |  | yes | yes |  | State Code |  |

SQL constraints:

- `name_code_uniq`: `unique(country_id, code)`

## `res.currency`

Table `res_currency`.
Description: Currency.
Order: `active desc, name`.
Source: `res_currency.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Currency |  |
| `full_name` | Char |  |  | yes |  | Name |  |
| `symbol` | Char |  | yes | yes |  |  |  |
| `rate` | Float |  |  | no |  | Current Rate | compute `_compute_current_rate` |
| `inverse_rate` | Float |  |  | no |  |  | compute `_compute_current_rate` |
| `rate_string` | Char |  |  | no |  |  | compute `_compute_current_rate` |
| `rate_ids` | One2many | `res.currency.rate` (inverse `currency_id`) |  | no (inverse) |  | Rates |  |
| `rounding` | Float |  |  | yes | default: `0.01` | Rounding Factor |  |
| `decimal_places` | Integer |  |  | yes |  |  | compute `_compute_decimal_places` |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `position` | Selection |  |  | yes | `after` After Amount, `before` Before Amount; default: `'after'` | Symbol Position |  |
| `date` | Date |  |  | no |  |  | compute `_compute_date` |
| `currency_unit_label` | Char |  |  | yes |  | Currency Unit |  |
| `currency_subunit_label` | Char |  |  | yes |  | Currency Subunit |  |
| `is_current_company_currency` | Boolean |  |  | no |  |  | compute `_compute_is_current_company_currency` |

SQL constraints:

- `unique_name`: `unique (name)`
- `rounding_gt_zero`: `CHECK (rounding>0)`

## `res.currency.rate`

Table `res_currency_rate`.
Description: Currency Rate.
Order: `name desc`.
Source: `res_currency.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Date |  | yes | yes | default: (computed) | Date |  |
| `rate` | Float |  |  | yes |  | Technical Rate |  |
| `company_rate` | Float |  |  | no |  |  | compute `_compute_company_rate` |
| `inverse_company_rate` | Float |  |  | no |  |  | compute `_compute_inverse_company_rate` |
| `currency_id` | Many2one | `res.currency` | yes | yes |  | Currency |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |

SQL constraints:

- `unique_name_per_day`: `unique (name,currency_id,company_id)`
- `currency_rate_check`: `CHECK (rate>0)`

## `res.groups`

Table `res_groups`.
Description: Access Groups.
Order: `name`.
Display name field: `full_name`.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `users` | Many2many | `res.users` (table `res_groups_users_rel`) |  | yes |  |  |  |
| `model_access` | One2many | `ir.model.access` (inverse `group_id`) |  | no (inverse) |  | Access Controls |  |
| `rule_groups` | Many2many | `ir.rule` (table `rule_group_rel`) |  | yes |  | Rules |  |
| `menu_access` | Many2many | `ir.ui.menu` (table `ir_ui_menu_group_rel`) |  | yes |  | Access Menu |  |
| `view_access` | Many2many | `ir.ui.view` (table `ir_ui_view_group_rel`) |  | yes |  | Views |  |
| `comment` | Text |  |  | yes |  |  |  |
| `category_id` | Many2one | `ir.module.category` |  | yes |  | Application |  |
| `color` | Integer |  |  | yes |  | Color Index |  |
| `full_name` | Char |  |  | no |  | Group Name | compute `_compute_full_name` |
| `share` | Boolean |  |  | yes |  | Share Group |  |
| `implied_ids` | Many2many | `res.groups` (table `res_groups_implied_rel`) |  | yes |  | Inherits |  |
| `trans_implied_ids` | Many2many | `res.groups` |  | no |  | Transitively inherits | compute `_compute_trans_implied` |

SQL constraints:

- `name_uniq`: `unique (category_id, name)`

## `res.lang`

Table `res_lang`.
Description: Languages.
Order: `active desc,name`.
Source: `res_lang.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `code` | Char |  | yes | yes |  | Locale Code |  |
| `iso_code` | Char |  |  | yes |  | ISO code |  |
| `url_code` | Char |  | yes | yes |  | URL Code |  |
| `active` | Boolean |  |  | yes |  |  |  |
| `direction` | Selection |  | yes | yes | `ltr` Left-to-Right, `rtl` Right-to-Left; default: `'ltr'` |  |  |
| `date_format` | Char |  | yes | yes | default: (computed) | Date Format |  |
| `time_format` | Char |  | yes | yes | default: (computed) | Time Format |  |
| `week_start` | Selection |  | yes | yes | `1` Monday, `2` Tuesday, `3` Wednesday, `4` Thursday, `5` Friday, `6` Saturday, `7` Sunday; default: `'7'` | First Day of Week |  |
| `grouping` | Char |  | yes | yes | default: `'[]'` | Separator Format |  |
| `decimal_point` | Char |  | yes | yes | default: `'.'` | Decimal Separator |  |
| `thousands_sep` | Char |  |  | yes | default: `','` | Thousands Separator |  |
| `flag_image` | Image |  |  | yes |  | Image |  |
| `flag_image_url` | Char |  |  | no |  |  | compute `_compute_field_flag_image_url` |

SQL constraints:

- `name_uniq`: `unique(name)`
- `code_uniq`: `unique(code)`
- `url_code_uniq`: `unique(url_code)`

## `res.partner`

Table `res_partner`.
Description: Contact.
Inherits: `format.address.mixin`, `avatar.mixin`.
Order: `complete_name ASC, id DESC`.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  |  |  |
| `complete_name` | Char |  |  | yes |  |  | compute `_compute_complete_name` |
| `date` | Date |  |  | yes |  |  |  |
| `title` | Many2one | `res.partner.title` |  | yes |  |  |  |
| `parent_id` | Many2one | `res.partner` |  | yes |  | Related Company |  |
| `parent_name` | Char |  |  | no |  | Parent name | related `parent_id.name` |
| `child_ids` | One2many | `res.partner` (inverse `parent_id`) |  | no (inverse) |  | Contact |  |
| `ref` | Char |  |  | yes |  | Reference |  |
| `lang` | Selection |  |  | yes | (dynamic: _lang_get) | Language |  |
| `active_lang_count` | Integer |  |  | no |  |  | compute `_compute_active_lang_count` |
| `tz` | Selection |  |  | yes | (dynamic: _tz_get); default: (computed) | Timezone |  |
| `tz_offset` | Char |  |  | no |  | Timezone offset | compute `_compute_tz_offset` |
| `user_id` | Many2one | `res.users` |  | yes |  | Salesperson | compute `_compute_user_id` |
| `vat` | Char |  |  | yes |  | Tax ID |  |
| `same_vat_partner_id` | Many2one | `res.partner` |  | no |  | Partner with same Tax ID | compute `_compute_same_vat_partner_id` |
| `same_company_registry_partner_id` | Many2one | `res.partner` |  | no |  | Partner with same Company Registry | compute `_compute_same_vat_partner_id` |
| `company_registry` | Char |  |  | yes |  | Company ID | compute `_compute_company_registry` |
| `bank_ids` | One2many | `res.partner.bank` (inverse `partner_id`) |  | no (inverse) |  | Banks |  |
| `website` | Char |  |  | yes |  | Website Link |  |
| `comment` | Html |  |  | yes |  | Notes |  |
| `category_id` | Many2many | `res.partner.category` |  | yes | default: (computed) | Tags |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `employee` | Boolean |  |  | yes |  |  |  |
| `function` | Char |  |  | yes |  | Job Position |  |
| `type` | Selection |  |  | yes | `contact` Contact, `invoice` Invoice Address, `delivery` Delivery Address, `other` Other Address; default: `'contact'` | Address Type |  |
| `street` | Char |  |  | yes |  |  |  |
| `street2` | Char |  |  | yes |  |  |  |
| `zip` | Char |  |  | yes |  |  |  |
| `city` | Char |  |  | yes |  |  |  |
| `state_id` | Many2one | `res.country.state` |  | yes |  | State |  |
| `country_id` | Many2one | `res.country` |  | yes |  | Country |  |
| `country_code` | Char |  |  | no |  | Country Code | related `country_id.code` |
| `partner_latitude` | Float |  |  | yes |  | Geo Latitude |  |
| `partner_longitude` | Float |  |  | yes |  | Geo Longitude |  |
| `email` | Char |  |  | yes |  |  |  |
| `email_formatted` | Char |  |  | no |  | Formatted Email | compute `_compute_email_formatted` |
| `phone` | Char |  |  | yes |  |  |  |
| `mobile` | Char |  |  | yes |  |  |  |
| `is_company` | Boolean |  |  | yes | default: `False` | Is a Company |  |
| `is_public` | Boolean |  |  | no |  |  | compute `_compute_is_public` |
| `industry_id` | Many2one | `res.partner.industry` |  | yes |  | Industry |  |
| `company_type` | Selection |  |  | no | `person` Individual, `company` Company | Company Type | compute `_compute_company_type` |
| `company_id` | Many2one | `res.company` |  | yes |  | Company |  |
| `color` | Integer |  |  | yes | default: `0` | Color Index |  |
| `user_ids` | One2many | `res.users` (inverse `partner_id`) |  | no (inverse) |  | Users |  |
| `partner_share` | Boolean |  |  | yes |  | Share Partner | compute `_compute_partner_share` |
| `contact_address` | Char |  |  | no |  | Complete Address | compute `_compute_contact_address` |
| `commercial_partner_id` | Many2one | `res.partner` |  | yes |  | Commercial Entity | compute `_compute_commercial_partner` |
| `commercial_company_name` | Char |  |  | yes |  | Company Name Entity | compute `_compute_commercial_company_name` |
| `company_name` | Char |  |  | yes |  | Company Name |  |
| `barcode` | Char |  |  | no (per company, ir.property) |  |  |  |
| `self` | Many2one | `_name` |  | no |  |  | compute `_compute_get_ids` |

SQL constraints:

- `check_name`: `CHECK( (type='contact' AND name IS NOT NULL) or (type!='contact') )`

## `res.partner.bank`

Table `res_partner_bank`.
Description: Bank Accounts.
Order: `sequence, id`.
Display name field: `acc_number`.
Source: `res_bank.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `acc_type` | Selection |  |  | no | (dynamic: lambda x: x.env['res.partner.bank'].get_supported_account_types()) | Type | compute `_compute_acc_type` |
| `acc_number` | Char |  | yes | yes |  | Account Number |  |
| `sanitized_acc_number` | Char |  |  | yes |  | Sanitized Account Number | compute `_compute_sanitized_acc_number` |
| `acc_holder_name` | Char |  |  | yes |  | Account Holder Name | compute `_compute_account_holder_name` |
| `partner_id` | Many2one | `res.partner` | yes | yes |  | Account Holder |  |
| `allow_out_payment` | Boolean |  |  | yes | default: `False` | Send Money |  |
| `bank_id` | Many2one | `res.bank` |  | yes |  | Bank |  |
| `bank_name` | Char |  |  | no |  |  | related `bank_id.name` |
| `bank_bic` | Char |  |  | no |  |  | related `bank_id.bic` |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |
| `currency_id` | Many2one | `res.currency` |  | yes |  | Currency |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | related `partner_id.company_id` |

SQL constraints:

- `unique_number`: `unique(sanitized_acc_number, partner_id)`

## `res.partner.category`

Table `res_partner_category`.
Description: Partner Tags.
Order: `name`.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Tag Name |  |
| `color` | Integer |  |  | yes | default: (computed) | Color |  |
| `parent_id` | Many2one | `res.partner.category` |  | yes |  | Parent Category |  |
| `child_ids` | One2many | `res.partner.category` (inverse `parent_id`) |  | no (inverse) |  | Child Tags |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `parent_path` | Char |  |  | yes |  |  |  |
| `partner_ids` | Many2many | `res.partner` |  | yes |  | Partners |  |

## `res.partner.industry`

Table `res_partner_industry`.
Description: Industry.
Order: `name`.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  | Name |  |
| `full_name` | Char |  |  | yes |  | Full Name |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |

## `res.partner.title`

Table `res_partner_title`.
Description: Partner Title.
Order: `name`.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Title |  |
| `shortcut` | Char |  |  | yes |  | Abbreviation |  |

## `res.users`

Table `res_users`.
Description: User.
Delegates (`_inherits`): `{'res.partner': 'partner_id'}`.
Order: `name, login`.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `partner_id` | Many2one | `res.partner` | yes | yes |  | Related Partner |  |
| `login` | Char |  | yes | yes |  |  |  |
| `password` | Char |  |  | no |  |  | compute `_compute_password` |
| `new_password` | Char |  |  | no |  | Set Password | compute `_compute_password` |
| `signature` | Html |  |  | yes |  | Email Signature | compute `_compute_signature` |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `active_partner` | Boolean |  |  | no |  | Partner is Active | related `partner_id.active` |
| `action_id` | Many2one | `ir.actions.actions` |  | yes |  | Home Action |  |
| `groups_id` | Many2many | `res.groups` (table `res_groups_users_rel`) |  | yes | default: (computed) | Groups |  |
| `log_ids` | One2many | `res.users.log` (inverse `create_uid`) |  | no (inverse) |  | User log entries |  |
| `login_date` | Datetime |  |  | no |  | Latest authentication | related `log_ids.create_date` |
| `share` | Boolean |  |  | yes |  | Share User | compute `_compute_share` |
| `companies_count` | Integer |  |  | no |  | Number of Companies | compute `_compute_companies_count` |
| `tz_offset` | Char |  |  | no |  | Timezone offset | compute `_compute_tz_offset` |
| `res_users_settings_ids` | One2many | `res.users.settings` (inverse `user_id`) |  | no (inverse) |  |  |  |
| `res_users_settings_id` | Many2one | `res.users.settings` |  | no |  | Settings | compute `_compute_res_users_settings_id` |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `company_ids` | Many2many | `res.company` (table `res_company_users_rel`) |  | yes | default: (computed) | Companies |  |
| `name` | Char |  |  | no |  |  | related `partner_id.name` |
| `email` | Char |  |  | no |  |  | related `partner_id.email` |
| `accesses_count` | Integer |  |  | no |  | # Access Rights | compute `_compute_accesses_count` |
| `rules_count` | Integer |  |  | no |  | # Record Rules | compute `_compute_accesses_count` |
| `groups_count` | Integer |  |  | no |  | # Groups | compute `_compute_accesses_count` |
| `user_group_warning` | Text |  |  | no |  | User Group Warning | compute `_compute_user_group_warning` |
| `api_key_ids` | One2many | `res.users.apikeys` (inverse `user_id`) |  | no (inverse) |  | API Keys |  |

SQL constraints:

- `login_key`: `UNIQUE (login)`

## `res.users.apikeys`

Table `res_users_apikeys`. Not auto-created (`_auto = False`, SQL view).
Description: Users API Keys.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Description |  |
| `user_id` | Many2one | `res.users` | yes | yes |  |  |  |
| `scope` | Char |  |  | yes |  | Scope |  |
| `create_date` | Datetime |  |  | yes |  | Creation Date |  |

## `res.users.apikeys.description`

Transient model (wizard), table `res_users_apikeys_description`, rows purged.
Description: API Key Description.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Description |  |

## `res.users.apikeys.show`

Abstract model (mixin), no table of its own.
Description: Show API Key.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `id` | Id |  |  | yes |  |  |  |
| `key` | Char |  |  | yes |  |  |  |

## `res.users.deletion`

Table `res_users_deletion`.
Description: Users Deletion Request.
Display name field: `user_id`.
Source: `res_users_deletion.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `user_id` | Many2one | `res.users` |  | yes |  | User |  |
| `user_id_int` | Integer |  |  | yes |  | User Id | compute `_compute_user_id_int` |
| `state` | Selection |  | yes | yes | `todo` To Do, `done` Done, `fail` Failed; default: `'todo'` | State |  |

## `res.users.identitycheck`

Transient model (wizard), table `res_users_identitycheck`, rows purged.
Description: Password Check Wizard.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `request` | Char |  |  | yes |  |  |  |
| `password` | Char |  |  | yes |  |  |  |

## `res.users.log`

Table `res_users_log`.
Description: Users Log.
Order: `id desc`.
Source: `res_users.py`.

## `res.users.settings`

Table `res_users_settings`.
Description: User Settings.
Display name field: `user_id`.
Source: `res_users_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `user_id` | Many2one | `res.users` | yes | yes |  | User |  |

SQL constraints:

- `unique_user_id`: `UNIQUE(user_id)`

## `reset.view.arch.wizard`

Transient model (wizard), table `reset_view_arch_wizard`, rows purged.
Description: Reset View Architecture Wizard.
Source: `ir_ui_view.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `view_id` | Many2one | `ir.ui.view` |  | yes |  | View |  |
| `view_name` | Char |  |  | no |  | View Name | related `view_id.name` |
| `has_diff` | Boolean |  |  | no |  |  | compute `_compute_arch_diff` |
| `arch_diff` | Html |  |  | no |  | Architecture Diff | compute `_compute_arch_diff` |
| `reset_mode` | Selection |  | yes | yes | `soft` Restore previous version (soft reset)., `hard` Reset to file version (hard reset)., `other_view` Reset to another view.; default: `'soft'` | Reset Mode |  |
| `compare_view_id` | Many2one | `ir.ui.view` |  | yes |  | Compare To View |  |
| `arch_to_compare` | Text |  |  | no |  | Arch To Compare To | compute `_compute_arch_diff` |

## `wizard.ir.model.menu.create`

Transient model (wizard), table `wizard_ir_model_menu_create`, rows purged.
Description: Create Menu Wizard.
Source: `ir_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `menu_id` | Many2one | `ir.ui.menu` | yes | yes |  | Parent Menu |  |
| `name` | Char |  | yes | yes |  | Menu Name |  |
