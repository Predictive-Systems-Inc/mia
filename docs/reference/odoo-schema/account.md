# Odoo 17.0 module `account`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 35. Models extended here: 23.

## `account.account`

Table `account_account`.
Description: Account.
Inherits: `mail.thread`.
Order: `code, company_id`.
Source: `account_account.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Account Name |  |
| `currency_id` | Many2one | `res.currency` |  | yes |  | Account Currency |  |
| `company_currency_id` | Many2one | (from related) |  | no |  |  | related `company_id.currency_id` |
| `code` | Char |  | yes | yes |  |  |  |
| `deprecated` | Boolean |  |  | yes | default: `False` |  |  |
| `used` | Boolean |  |  | no |  |  | compute `_compute_used` |
| `account_type` | Selection |  | yes | yes | `asset_receivable` Receivable, `asset_cash` Bank and Cash, `asset_current` Current Assets, `asset_non_current` Non-current Assets, `asset_prepayments` Prepayments, `asset_fixed` Fixed Assets, `liability_payable` Payable, `liability_credit_card` Credit Card, `liability_current` Current Liabilities, `liability_non_current` Non-current Liabilities, `equity` Equity, `equity_unaffected` Current Year Earnings, `income` Income, `income_other` Other Income, `expense` Expenses, `expense_depreciation` Depreciation, `expense_direct_cost` Cost of Revenue, `off_balance` Off-Balance Sheet | Type | compute `_compute_account_type` |
| `include_initial_balance` | Boolean |  |  | yes |  | Bring Accounts Balance Forward | compute `_compute_include_initial_balance` |
| `internal_group` | Selection |  |  | yes | `equity` Equity, `asset` Asset, `liability` Liability, `income` Income, `expense` Expense, `off_balance` Off Balance | Internal Group | compute `_compute_internal_group` |
| `reconcile` | Boolean |  |  | yes |  | Allow Reconciliation | compute `_compute_reconcile` |
| `tax_ids` | Many2many | `account.tax` (table `account_account_tax_default_rel`) |  | yes |  | Default Taxes |  |
| `note` | Text |  |  | yes |  | Internal Notes |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `tag_ids` | Many2many | `account.account.tag` (table `account_account_account_tag`) |  | yes |  | Tags |  |
| `group_id` | Many2one | `account.group` |  | yes |  |  | compute `_compute_account_group` |
| `root_id` | Many2one | `account.root` |  | yes |  |  | compute `_compute_account_root` |
| `allowed_journal_ids` | Many2many | `account.journal` |  | yes |  | Allowed Journals |  |
| `opening_debit` | Monetary |  |  | no |  | Opening Debit | compute `_compute_opening_debit_credit` |
| `opening_credit` | Monetary |  |  | no |  | Opening Credit | compute `_compute_opening_debit_credit` |
| `opening_balance` | Monetary |  |  | no |  | Opening Balance | compute `_compute_opening_debit_credit` |
| `current_balance` | Float |  |  | no |  |  | compute `_compute_current_balance` |
| `related_taxes_amount` | Integer |  |  | no |  |  | compute `_compute_related_taxes_amount` |
| `non_trade` | Boolean |  |  | yes | default: `False` |  |  |

## `account.account.tag`

Table `account_account_tag`.
Description: Account Tag.
Source: `account_account_tag.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Tag Name |  |
| `applicability` | Selection |  | yes | yes | `accounts` Accounts, `taxes` Taxes, `products` Products; default: `'accounts'` |  |  |
| `color` | Integer |  |  | yes |  | Color Index |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `tax_negate` | Boolean |  |  | yes |  | Negate Tax Balance |  |
| `country_id` | Many2one | `res.country` |  | yes |  | Country |  |

SQL constraints:

- `name_uniq`: `unique(name, applicability, country_id)`

## `account.analytic.account` (extension)

Adds fields to `account.analytic.account`, defined in another module. Every field below is added by this module.
Source: `account_analytic_account.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `invoice_count` | Integer |  |  | no |  | Invoice Count | compute `_compute_invoice_count` |
| `vendor_bill_count` | Integer |  |  | no |  | Vendor Bill Count | compute `_compute_vendor_bill_count` |
| `debit` | Monetary |  |  | yes |  |  |  |
| `credit` | Monetary |  |  | yes |  |  |  |

## `account.analytic.applicability` (extension)

Adds fields to `account.analytic.applicability`, defined in another module. Every field below is added by this module.
Description: Analytic Plan's Applicabilities.
Source: `account_analytic_plan.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `business_domain` | Selection |  |  | yes | added: `invoice` Invoice, `bill` Vendor Bill |  |  |
| `account_prefix` | Char |  |  | yes |  | Financial Accounts Prefix |  |
| `product_categ_id` | Many2one | `product.category` |  | yes |  | Product Category |  |
| `display_account_prefix` | Boolean |  |  | no |  |  | compute `_compute_display_account_prefix` |

## `account.analytic.distribution.model` (extension)

Adds fields to `account.analytic.distribution.model`, defined in another module. Every field below is added by this module.
Source: `account_analytic_distribution_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `account_prefix` | Char |  |  | yes |  | Accounts Prefix |  |
| `product_id` | Many2one | `product.product` |  | yes |  | Product |  |
| `product_categ_id` | Many2one | `product.category` |  | yes |  | Product Category |  |

## `account.analytic.line` (extension)

Adds fields to `account.analytic.line`, defined in another module. Every field below is added by this module.
Description: Analytic Line.
Source: `account_analytic_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `product_id` | Many2one | `product.product` |  | yes |  | Product |  |
| `general_account_id` | Many2one | `account.account` |  | yes |  | Financial Account | compute `_compute_general_account_id` |
| `journal_id` | Many2one | `account.journal` |  | yes |  | Financial Journal | related `move_line_id.journal_id` |
| `partner_id` | Many2one | (redefines inherited field) |  | yes |  |  | compute `_compute_partner_id` |
| `move_line_id` | Many2one | `account.move.line` |  | yes |  | Journal Item |  |
| `code` | Char |  |  | yes |  |  |  |
| `ref` | Char |  |  | yes |  | Ref. |  |
| `category` | Selection |  |  | yes | added: `invoice` Customer Invoice, `vendor_bill` Vendor Bill |  |  |

## `account.bank.statement`

Table `account_bank_statement`.
Description: Bank Statement.
Order: `first_line_index desc`.
Source: `account_bank_statement.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  | Reference | compute `_compute_name` |
| `reference` | Char |  |  | yes |  | External Reference |  |
| `date` | Date |  |  | yes |  |  | compute `_compute_date_index` |
| `first_line_index` | Char |  |  | yes |  |  | compute `_compute_date_index` |
| `balance_start` | Monetary |  |  | yes |  | Starting Balance | compute `_compute_balance_start` |
| `balance_end` | Monetary |  |  | yes |  | Computed Balance | compute `_compute_balance_end` |
| `balance_end_real` | Monetary |  |  | yes |  | Ending Balance | compute `_compute_balance_end_real` |
| `company_id` | Many2one | `res.company` |  | yes |  |  | related `journal_id.company_id` |
| `currency_id` | Many2one | `res.currency` |  | no |  |  | compute `_compute_currency_id` |
| `journal_id` | Many2one | `account.journal` |  | yes |  |  | compute `_compute_journal_id` |
| `line_ids` | One2many | `account.bank.statement.line` (inverse `statement_id`) | yes | no (inverse) |  | Statement lines |  |
| `is_complete` | Boolean |  |  | yes |  |  | compute `_compute_is_complete` |
| `is_valid` | Boolean |  |  | no |  |  | compute `_compute_is_valid` |
| `problem_description` | Text |  |  | no |  |  | compute `_compute_problem_description` |
| `attachment_ids` | Many2many | `ir.attachment` |  | yes |  | Attachments |  |

## `account.bank.statement.line`

Table `account_bank_statement_line`.
Description: Bank Statement Line.
Delegates (`_inherits`): `{'account.move': 'move_id'}`.
Order: `internal_index desc`.
Source: `account_bank_statement_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `move_id` | Many2one | `account.move` | yes | yes |  | Journal Entry |  |
| `statement_id` | Many2one | `account.bank.statement` |  | yes |  | Statement |  |
| `payment_ids` | Many2many | `account.payment` (table `account_payment_account_bank_statement_line_rel`) |  | yes |  | Auto-generated Payments |  |
| `sequence` | Integer |  |  | yes | default: `1` |  |  |
| `partner_id` | Many2one | `res.partner` |  | yes |  | Partner |  |
| `account_number` | Char |  |  | yes |  | Bank Account Number |  |
| `partner_name` | Char |  |  | yes |  |  |  |
| `transaction_type` | Char |  |  | yes |  |  |  |
| `payment_ref` | Char |  |  | yes |  | Label |  |
| `currency_id` | Many2one | `res.currency` |  | yes |  | Journal Currency | compute `_compute_currency_id` |
| `amount` | Monetary |  |  | yes |  |  |  |
| `running_balance` | Monetary |  |  | no |  |  | compute `_compute_running_balance` |
| `foreign_currency_id` | Many2one | `res.currency` |  | yes |  | Foreign Currency |  |
| `amount_currency` | Monetary |  |  | yes |  | Amount in Currency | compute `_compute_amount_currency` |
| `amount_residual` | Float |  |  | yes |  | Residual Amount | compute `_compute_is_reconciled` |
| `country_code` | Char |  |  | no |  |  | related `company_id.account_fiscal_country_id.code` |
| `internal_index` | Char |  |  | yes |  | Internal Reference | compute `_compute_internal_index` |
| `is_reconciled` | Boolean |  |  | yes |  | Is Reconciled | compute `_compute_is_reconciled` |
| `statement_complete` | Boolean |  |  | no |  |  | related `statement_id.is_complete` |
| `statement_valid` | Boolean |  |  | no |  |  | related `statement_id.is_valid` |
| `statement_balance_end_real` | Monetary |  |  | no |  |  | related `statement_id.balance_end_real` |
| `statement_name` | Char |  |  | no |  | Statement Name | related `statement_id.name` |
| `transaction_details` | Json |  |  | yes |  |  |  |

## `account.cash.rounding`

Table `account_cash_rounding`.
Description: Account Cash Rounding.
Source: `account_cash_rounding.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `rounding` | Float |  | yes | yes | default: `0.01` | Rounding Precision |  |
| `strategy` | Selection |  | yes | yes | `biggest_tax` Modify tax amount, `add_invoice_line` Add a rounding line; default: `'add_invoice_line'` | Rounding Strategy |  |
| `profit_account_id` | Many2one | `account.account` |  | no (per company, ir.property) |  | Profit Account |  |
| `loss_account_id` | Many2one | `account.account` |  | no (per company, ir.property) |  | Loss Account |  |
| `rounding_method` | Selection |  | yes | yes | `UP` Up, `DOWN` Down, `HALF-UP` Nearest; default: `'HALF-UP'` | Rounding Method |  |
| `company_id` | Many2one | `res.company` |  | no |  |  | related `profit_account_id.company_id` |

## `account.chart.template`

Abstract model (mixin), no table of its own.
Description: Account Chart Template.
Source: `chart_template.py`, `template_generic_coa.py`.

## `account.fiscal.position`

Table `account_fiscal_position`.
Description: Fiscal Position.
Order: `sequence`.
Source: `partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sequence` | Integer |  |  | yes |  |  |  |
| `name` | Char |  | yes | yes |  | Fiscal Position |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `account_ids` | One2many | `account.fiscal.position.account` (inverse `position_id`) |  | no (inverse) |  | Account Mapping |  |
| `tax_ids` | One2many | `account.fiscal.position.tax` (inverse `position_id`) |  | no (inverse) |  | Tax Mapping |  |
| `note` | Html |  |  | yes |  | Notes |  |
| `auto_apply` | Boolean |  |  | yes |  | Detect Automatically |  |
| `vat_required` | Boolean |  |  | yes |  | VAT required |  |
| `company_country_id` | Many2one | (from related) |  | no |  | Company Country | related `company_id.account_fiscal_country_id` |
| `fiscal_country_codes` | Char |  |  | no |  | Company Fiscal Country Code | related `company_country_id.code` |
| `country_id` | Many2one | `res.country` |  | yes |  | Country |  |
| `country_group_id` | Many2one | `res.country.group` |  | yes |  | Country Group |  |
| `state_ids` | Many2many | `res.country.state` |  | yes |  | Federal States |  |
| `zip_from` | Char |  |  | yes |  | Zip Range From |  |
| `zip_to` | Char |  |  | yes |  | Zip Range To |  |
| `states_count` | Integer |  |  | no |  |  | compute `_compute_states_count` |
| `foreign_vat` | Char |  |  | yes |  | Foreign Tax ID |  |
| `foreign_vat_header_mode` | Selection |  |  | no | `templates_found` Templates Found, `no_template` No Template |  | compute `_compute_foreign_vat_header_mode` |

## `account.fiscal.position.account`

Table `account_fiscal_position_account`.
Description: Accounts Mapping of Fiscal Position.
Display name field: `position_id`.
Source: `partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `position_id` | Many2one | `account.fiscal.position` | yes | yes |  | Fiscal Position |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | related `position_id.company_id` |
| `account_src_id` | Many2one | `account.account` | yes | yes |  | Account on Product |  |
| `account_dest_id` | Many2one | `account.account` | yes | yes |  | Account to Use Instead |  |

SQL constraints:

- `account_src_dest_uniq`: `unique (position_id,account_src_id,account_dest_id)`

## `account.fiscal.position.tax`

Table `account_fiscal_position_tax`.
Description: Tax Mapping of Fiscal Position.
Display name field: `position_id`.
Source: `partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `position_id` | Many2one | `account.fiscal.position` | yes | yes |  | Fiscal Position |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | related `position_id.company_id` |
| `tax_src_id` | Many2one | `account.tax` | yes | yes |  | Tax on Product |  |
| `tax_dest_id` | Many2one | `account.tax` |  | yes |  | Tax to Apply |  |
| `tax_dest_active` | Boolean |  |  | no |  |  | related `tax_dest_id.active` |

SQL constraints:

- `tax_src_dest_uniq`: `unique (position_id,tax_src_id,tax_dest_id)`

## `account.full.reconcile`

Table `account_full_reconcile`.
Description: Full Reconcile.
Source: `account_full_reconcile.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `partial_reconcile_ids` | One2many | `account.partial.reconcile` (inverse `full_reconcile_id`) |  | no (inverse) |  | Reconciliation Parts |  |
| `reconciled_line_ids` | One2many | `account.move.line` (inverse `full_reconcile_id`) |  | no (inverse) |  | Matched Journal Items |  |
| `exchange_move_id` | Many2one | `account.move` |  | yes |  |  |  |

## `account.group`

Table `account_group`.
Description: Account Group.
Order: `code_prefix_start`.
Source: `account_account.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `parent_id` | Many2one | `account.group` |  | yes |  |  |  |
| `parent_path` | Char |  |  | yes |  |  |  |
| `name` | Char |  | yes | yes |  |  |  |
| `code_prefix_start` | Char |  |  | yes |  |  | compute `_compute_code_prefix_start` |
| `code_prefix_end` | Char |  |  | yes |  |  | compute `_compute_code_prefix_end` |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) |  |  |

SQL constraints:

- `check_length_prefix`: `CHECK(char_length(COALESCE(code_prefix_start, '')) = char_length(COALESCE(code_prefix_end, '')))`

## `account.incoterms`

Table `account_incoterms`.
Description: Incoterms.
Source: `account_incoterms.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `code` | Char |  | yes | yes |  | Code |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |

## `account.journal`

Table `account_journal`.
Description: Journal.
Inherits: `portal.mixin`, `mail.alias.mixin.optional`, `mail.thread`, `mail.activity.mixin`.
Order: `sequence, type, code`.
Source: `account_journal.py`, `account_journal_dashboard.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Journal Name |  |
| `code` | Char |  | yes | yes |  | Short Code | compute `_compute_code` |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `type` | Selection |  | yes | yes | `sale` Sales, `purchase` Purchase, `cash` Cash, `bank` Bank, `general` Miscellaneous |  |  |
| `account_control_ids` | Many2many | `account.account` (table `journal_account_control_rel`) |  | yes |  | Allowed accounts |  |
| `default_account_type` | Char |  |  | no |  | Default Account Type | compute `_compute_default_account_type` |
| `default_account_id` | Many2one | `account.account` |  | yes |  | Default Account |  |
| `suspense_account_id` | Many2one | `account.account` |  | yes |  | Suspense Account | compute `_compute_suspense_account_id` |
| `restrict_mode_hash_table` | Boolean |  |  | yes |  | Lock Posted Entries with Hash |  |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |
| `invoice_reference_type` | Selection |  | yes | yes | `none` Open, `partner` Based on Customer, `invoice` Based on Invoice; default: `'invoice'` | Communication Type |  |
| `invoice_reference_model` | Selection |  | yes | yes | `odoo` Odoo, `euro` European; default: (computed) | Communication Standard |  |
| `currency_id` | Many2one | `res.currency` |  | yes |  | Currency |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `country_code` | Char |  |  | no |  |  | related `company_id.account_fiscal_country_id.code` |
| `refund_sequence` | Boolean |  |  | yes | default: `False` | Dedicated Credit Note Sequence |  |
| `payment_sequence` | Boolean |  |  | yes |  | Dedicated Payment Sequence | compute `_compute_payment_sequence` |
| `sequence_override_regex` | Text |  |  | yes |  |  |  |
| `inbound_payment_method_line_ids` | One2many | `account.payment.method.line` (inverse `journal_id`) |  | yes |  | Inbound Payment Methods | compute `_compute_inbound_payment_method_line_ids` |
| `outbound_payment_method_line_ids` | One2many | `account.payment.method.line` (inverse `journal_id`) |  | yes |  | Outbound Payment Methods | compute `_compute_outbound_payment_method_line_ids` |
| `profit_account_id` | Many2one | `account.account` |  | yes |  | Profit Account |  |
| `loss_account_id` | Many2one | `account.account` |  | yes |  | Loss Account |  |
| `company_partner_id` | Many2one | `res.partner` |  | no |  | Account Holder | related `company_id.partner_id` |
| `bank_account_id` | Many2one | `res.partner.bank` |  | yes |  | Bank Account |  |
| `bank_statements_source` | Selection |  |  | yes | (dynamic: _get_bank_statements_available_sources); default: `'undefined'` | Bank Feeds |  |
| `bank_acc_number` | Char |  |  | no |  |  | related `bank_account_id.acc_number` |
| `bank_id` | Many2one | `res.bank` |  | no |  |  | related `bank_account_id.bank_id` |
| `sale_activity_type_id` | Many2one | `mail.activity.type` |  | yes | default: `False` | Schedule Activity |  |
| `sale_activity_user_id` | Many2one | `res.users` |  | yes |  | Activity User |  |
| `sale_activity_note` | Text |  |  | yes |  | Activity Summary |  |
| `alias_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `journal_group_ids` | Many2many | `account.journal.group` |  | yes |  | Journal Groups |  |
| `secure_sequence_id` | Many2one | `ir.sequence` |  | yes |  |  |  |
| `available_payment_method_ids` | Many2many | `account.payment.method` |  | no |  |  | compute `_compute_available_payment_method_ids` |
| `selected_payment_method_codes` | Char |  |  | no |  |  | compute `_compute_selected_payment_method_codes` |
| `accounting_date` | Date |  |  | no |  |  | compute `_compute_accounting_date` |
| `display_alias_fields` | Boolean |  |  | no |  |  | compute `_compute_display_alias_fields` |
| `kanban_dashboard` | Text |  |  | no |  |  | compute `_kanban_dashboard` |
| `kanban_dashboard_graph` | Text |  |  | no |  |  | compute `_kanban_dashboard_graph` |
| `json_activity_data` | Text |  |  | no |  |  | compute `_get_json_activity_data` |
| `show_on_dashboard` | Boolean |  |  | yes | default: `True` | Show journal on dashboard |  |
| `color` | Integer |  |  | yes | default: `0` | Color Index |  |
| `current_statement_balance` | Monetary |  |  | no |  |  | compute `_compute_current_statement_balance` |
| `has_statement_lines` | Boolean |  |  | no |  |  | compute `_compute_current_statement_balance` |
| `entries_count` | Integer |  |  | no |  |  | compute `_compute_entries_count` |
| `has_sequence_holes` | Boolean |  |  | no |  |  | compute `_compute_has_sequence_holes` |
| `last_statement_id` | Many2one | `account.bank.statement` |  | no |  |  | compute `_compute_last_bank_statement` |

SQL constraints:

- `code_company_uniq`: `unique (company_id, code)`

## `account.journal.group`

Table `account_journal_group`.
Description: Account Journal Group.
Source: `account_journal.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Journal Group |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) |  |  |
| `excluded_journal_ids` | Many2many | `account.journal` |  | yes |  | Excluded Journals |  |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |

SQL constraints:

- `uniq_name`: `unique(company_id, name)`

## `account.move`

Table `account_move`.
Description: Journal Entry.
Inherits: `portal.mixin`, `mail.thread.main.attachment`, `mail.activity.mixin`, `sequence.mixin`.
Order: `date desc, name desc, invoice_date desc, id desc`.
Source: `account_bank_statement_line.py`, `account_move.py`, `account_payment.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `statement_line_ids` | One2many | `account.bank.statement.line` (inverse `move_id`) |  | no (inverse) |  | Statements |  |
| `name` | Char |  |  | yes |  | Number | compute `_compute_name` |
| `ref` | Char |  |  | yes |  | Reference |  |
| `date` | Date |  | yes | yes |  | Date | compute `_compute_date` |
| `state` | Selection |  | yes | yes | `draft` Draft, `posted` Posted, `cancel` Cancelled; default: `'draft'` | Status |  |
| `move_type` | Selection |  | yes | yes | `entry` Journal Entry, `out_invoice` Customer Invoice, `out_refund` Customer Credit Note, `in_invoice` Vendor Bill, `in_refund` Vendor Credit Note, `out_receipt` Sales Receipt, `in_receipt` Purchase Receipt; default: `'entry'` | Type |  |
| `is_storno` | Boolean |  |  | yes |  |  | compute `_compute_is_storno` |
| `journal_id` | Many2one | `account.journal` | yes | yes |  | Journal | compute `_compute_journal_id` |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | compute `_compute_company_id` |
| `line_ids` | One2many | `account.move.line` (inverse `move_id`) |  | no (inverse) |  | Journal Items |  |
| `payment_id` | Many2one | `account.payment` |  | yes |  | Payment |  |
| `statement_line_id` | Many2one | `account.bank.statement.line` |  | yes |  | Statement Line |  |
| `statement_id` | Many2one | (from related) |  | no |  |  | related `statement_line_id.statement_id` |
| `tax_cash_basis_rec_id` | Many2one | `account.partial.reconcile` |  | yes |  | Tax Cash Basis Entry of |  |
| `tax_cash_basis_origin_move_id` | Many2one | `account.move` |  | yes |  | Cash Basis Origin |  |
| `tax_cash_basis_created_move_ids` | One2many | `account.move` (inverse `tax_cash_basis_origin_move_id`) |  | no (inverse) |  | Cash Basis Entries |  |
| `always_tax_exigible` | Boolean |  |  | yes |  |  | compute `_compute_always_tax_exigible` |
| `auto_post` | Selection |  | yes | yes | `no` No, `at_date` At Date, `monthly` Monthly, `quarterly` Quarterly, `yearly` Yearly; default: `'no'` | Auto-post |  |
| `auto_post_until` | Date |  |  | yes |  | Auto-post until | compute `_compute_auto_post_until` |
| `auto_post_origin_id` | Many2one | `account.move` |  | yes |  | First recurring entry |  |
| `hide_post_button` | Boolean |  |  | no |  |  | compute `_compute_hide_post_button` |
| `to_check` | Boolean |  |  | yes |  | To Check |  |
| `posted_before` | Boolean |  |  | yes |  |  |  |
| `suitable_journal_ids` | Many2many | `account.journal` |  | no |  |  | compute `_compute_suitable_journal_ids` |
| `highest_name` | Char |  |  | no |  |  | compute `_compute_highest_name` |
| `made_sequence_hole` | Boolean |  |  | no |  |  | compute `_compute_made_sequence_hole` |
| `show_name_warning` | Boolean |  |  | no |  |  |  |
| `type_name` | Char |  |  | no |  | Type Name | compute `_compute_type_name` |
| `country_code` | Char |  |  | no |  |  | related `company_id.account_fiscal_country_id.code` |
| `attachment_ids` | One2many | `ir.attachment` (inverse `res_id`) |  | no (inverse) |  | Attachments |  |
| `restrict_mode_hash_table` | Boolean |  |  | no |  |  | related `journal_id.restrict_mode_hash_table` |
| `secure_sequence_number` | Integer |  |  | yes |  | Inalteralbility No Gap Sequence # |  |
| `inalterable_hash` | Char |  |  | yes |  | Inalterability Hash |  |
| `string_to_hash` | Char |  |  | no |  |  | compute `_compute_string_to_hash` |
| `invoice_line_ids` | One2many | `account.move.line` (inverse `move_id`) |  | no (inverse) |  | Invoice lines |  |
| `invoice_date` | Date |  |  | yes |  | Invoice/Bill Date |  |
| `invoice_date_due` | Date |  |  | yes |  | Due Date | compute `_compute_invoice_date_due` |
| `delivery_date` | Date |  |  | yes |  | Delivery Date | compute `_compute_delivery_date` |
| `show_delivery_date` | Boolean |  |  | no |  |  | compute `_compute_show_delivery_date` |
| `invoice_payment_term_id` | Many2one | `account.payment.term` |  | yes |  | Payment Terms | compute `_compute_invoice_payment_term_id` |
| `needed_terms` | Binary |  |  | no |  |  | compute `_compute_needed_terms` |
| `needed_terms_dirty` | Boolean |  |  | no |  |  | compute `_compute_needed_terms` |
| `tax_calculation_rounding_method` | Selection |  |  | no |  | Tax calculation rounding method | related `company_id.tax_calculation_rounding_method` |
| `partner_id` | Many2one | `res.partner` |  | yes |  | Partner |  |
| `commercial_partner_id` | Many2one | `res.partner` |  | yes |  | Commercial Entity | compute `_compute_commercial_partner_id` |
| `partner_shipping_id` | Many2one | `res.partner` |  | yes |  | Delivery Address | compute `_compute_partner_shipping_id` |
| `partner_bank_id` | Many2one | `res.partner.bank` |  | yes |  | Recipient Bank | compute `_compute_partner_bank_id` |
| `fiscal_position_id` | Many2one | `account.fiscal.position` |  | yes |  | Fiscal Position | compute `_compute_fiscal_position_id` |
| `payment_reference` | Char |  |  | yes |  | Payment Reference | compute `_compute_payment_reference` |
| `display_qr_code` | Boolean |  |  | no |  | Display QR-code | compute `_compute_display_qr_code` |
| `qr_code_method` | Selection |  |  | yes | (dynamic: lambda self: self.env['res.partner.bank'].get_available_qr_methods_in_sequence()) | Payment QR-code |  |
| `invoice_outstanding_credits_debits_widget` | Binary |  |  | no |  |  | compute `_compute_payments_widget_to_reconcile_info` |
| `invoice_has_outstanding` | Boolean |  |  | no |  |  | compute `_compute_payments_widget_to_reconcile_info` |
| `invoice_payments_widget` | Binary |  |  | no |  |  | compute `_compute_payments_widget_reconciled_info` |
| `company_currency_id` | Many2one | (from related) |  | no |  | Company Currency | related `company_id.currency_id` |
| `currency_id` | Many2one | `res.currency` | yes | yes |  | Currency | compute `_compute_currency_id` |
| `direction_sign` | Integer |  |  | no |  |  | compute `_compute_direction_sign` |
| `amount_untaxed` | Monetary |  |  | yes |  | Untaxed Amount | compute `_compute_amount` |
| `amount_tax` | Monetary |  |  | yes |  | Tax | compute `_compute_amount` |
| `amount_total` | Monetary |  |  | yes |  | Total | compute `_compute_amount` |
| `amount_residual` | Monetary |  |  | yes |  | Amount Due | compute `_compute_amount` |
| `amount_untaxed_signed` | Monetary |  |  | yes |  | Untaxed Amount Signed | compute `_compute_amount` |
| `amount_tax_signed` | Monetary |  |  | yes |  | Tax Signed | compute `_compute_amount` |
| `amount_total_signed` | Monetary |  |  | yes |  | Total Signed | compute `_compute_amount` |
| `amount_total_in_currency_signed` | Monetary |  |  | yes |  | Total in Currency Signed | compute `_compute_amount` |
| `amount_residual_signed` | Monetary |  |  | yes |  | Amount Due Signed | compute `_compute_amount` |
| `tax_totals` | Binary |  |  | no |  | Invoice Totals | compute `_compute_tax_totals` |
| `payment_state` | Selection |  |  | yes | `not_paid` Not Paid, `in_payment` In Payment, `paid` Paid, `partial` Partially Paid, `reversed` Reversed, `invoicing_legacy` Invoicing App Legacy | Payment Status | compute `_compute_payment_state` |
| `amount_total_words` | Char |  |  | no |  | Amount total in words | compute `_compute_amount_total_words` |
| `reversed_entry_id` | Many2one | `account.move` |  | yes |  | Reversal of |  |
| `reversal_move_id` | One2many | `account.move` (inverse `reversed_entry_id`) |  | no (inverse) |  |  |  |
| `invoice_vendor_bill_id` | Many2one | `account.move` |  | no |  | Vendor Bill |  |
| `invoice_source_email` | Char |  |  | yes |  | Source Email |  |
| `invoice_partner_display_name` | Char |  |  | yes |  |  | compute `_compute_invoice_partner_display_info` |
| `quick_edit_mode` | Boolean |  |  | no |  |  | compute `_compute_quick_edit_mode` |
| `quick_edit_total_amount` | Monetary |  |  | yes |  | Total (Tax inc.) |  |
| `quick_encoding_vals` | Json |  |  | no |  |  | compute `_compute_quick_encoding_vals` |
| `narration` | Html |  |  | yes |  | Terms and Conditions | compute `_compute_narration` |
| `is_move_sent` | Boolean |  |  | yes |  |  |  |
| `is_being_sent` | Boolean |  |  | no |  |  | compute `_compute_is_being_sent` |
| `invoice_user_id` | Many2one | `res.users` |  | yes |  | Salesperson | compute `_compute_invoice_default_sale_person` |
| `user_id` | Many2one | (from related) |  | no |  | User | related `invoice_user_id` |
| `invoice_origin` | Char |  |  | yes |  | Origin |  |
| `invoice_incoterm_id` | Many2one | `account.incoterms` |  | yes |  | Incoterm | compute `_compute_incoterm` |
| `incoterm_location` | Char |  |  | yes |  | Incoterm Location | compute `_compute_incoterm_location` |
| `invoice_cash_rounding_id` | Many2one | `account.cash.rounding` |  | yes |  | Cash Rounding Method |  |
| `send_and_print_values` | Json |  |  | yes |  |  |  |
| `invoice_pdf_report_id` | Many2one | `ir.attachment` |  | no |  | PDF Attachment | compute `lambda self: self._compute_linked_attachment_id('invoice_pdf_report_id', 'invoice_pdf_report_file')` |
| `invoice_pdf_report_file` | Binary |  |  | yes |  | PDF File |  |
| `invoice_filter_type_domain` | Char |  |  | no |  |  | compute `_compute_invoice_filter_type_domain` |
| `bank_partner_id` | Many2one | `res.partner` |  | no |  |  | compute `_compute_bank_partner_id` |
| `tax_lock_date_message` | Char |  |  | no |  |  | compute `_compute_tax_lock_date_message` |
| `display_inactive_currency_warning` | Boolean |  |  | no |  |  | compute `_compute_display_inactive_currency_warning` |
| `tax_country_id` | Many2one | `res.country` |  | no |  |  | compute `_compute_tax_country_id` |
| `tax_country_code` | Char |  |  | no |  |  | compute `_compute_tax_country_code` |
| `has_reconciled_entries` | Boolean |  |  | no |  |  | compute `_compute_has_reconciled_entries` |
| `show_reset_to_draft_button` | Boolean |  |  | no |  |  | compute `_compute_show_reset_to_draft_button` |
| `partner_credit_warning` | Text |  |  | no |  |  | compute `_compute_partner_credit_warning` |
| `partner_credit` | Monetary |  |  | no |  |  | compute `_compute_partner_credit` |
| `duplicated_ref_ids` | Many2many | `account.move` |  | no |  |  | compute `_compute_duplicated_ref_ids` |
| `need_cancel_request` | Boolean |  |  | no |  |  | compute `_compute_need_cancel_request` |
| `show_update_fpos` | Boolean |  |  | no |  | Has Fiscal Position Changed |  |
| `payment_term_details` | Binary |  |  | no |  |  | compute `_compute_payment_term_details` |
| `show_payment_term_details` | Boolean |  |  | no |  |  | compute `_compute_show_payment_term_details` |
| `show_discount_details` | Boolean |  |  | no |  |  | compute `_compute_show_payment_term_details` |
| `payment_ids` | One2many | `account.payment` (inverse `move_id`) |  | no (inverse) |  | Payments |  |

SQL constraints:

- `unique_name`: ``

## `account.move.line`

Table `account_move_line`.
Description: Journal Item.
Inherits: `analytic.mixin`.
Order: `date desc, move_name desc, id`.
Source: `account_move_line.py`, `account_move_line_tax_details.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `move_id` | Many2one | `account.move` | yes | yes |  | Journal Entry |  |
| `journal_id` | Many2one | (from related) |  | yes |  |  | related `move_id.journal_id` |
| `company_id` | Many2one | (from related) |  | yes |  |  | related `move_id.company_id` |
| `company_currency_id` | Many2one | (from related) |  | yes |  | Company Currency | related `move_id.company_currency_id` |
| `move_name` | Char |  |  | yes |  | Number | related `move_id.name` |
| `parent_state` | Selection |  |  | yes |  |  | related `move_id.state` |
| `date` | Date |  |  | yes |  |  | related `move_id.date` |
| `invoice_date` | Date |  |  | yes |  |  | related `move_id.invoice_date` |
| `ref` | Char |  |  | yes |  |  | related `move_id.ref` |
| `is_storno` | Boolean |  |  | no |  | Company Storno Accounting | related `move_id.is_storno` |
| `sequence` | Integer |  |  | yes |  |  | compute `_compute_sequence` |
| `move_type` | Selection |  |  | no |  |  | related `move_id.move_type` |
| `account_id` | Many2one | `account.account` |  | yes |  | Account | compute `_compute_account_id` |
| `name` | Char |  |  | yes |  | Label | compute `_compute_name` |
| `debit` | Monetary |  |  | yes |  | Debit | compute `_compute_debit_credit` |
| `credit` | Monetary |  |  | yes |  | Credit | compute `_compute_debit_credit` |
| `balance` | Monetary |  |  | yes |  | Balance | compute `_compute_balance` |
| `cumulated_balance` | Monetary |  |  | no |  | Cumulated Balance | compute `_compute_cumulated_balance` |
| `currency_rate` | Float |  |  | no |  |  | compute `_compute_currency_rate` |
| `amount_currency` | Monetary |  |  | yes |  | Amount in Currency | compute `_compute_amount_currency` |
| `currency_id` | Many2one | `res.currency` | yes | yes |  | Currency | compute `_compute_currency_id` |
| `is_same_currency` | Boolean |  |  | no |  |  | compute `_compute_same_currency` |
| `partner_id` | Many2one | `res.partner` |  | yes |  | Partner | compute `_compute_partner_id` |
| `reconcile_model_id` | Many2one | `account.reconcile.model` |  | yes |  | Reconciliation Model |  |
| `payment_id` | Many2one | `account.payment` |  | yes |  | Originator Payment | related `move_id.payment_id` |
| `statement_line_id` | Many2one | `account.bank.statement.line` |  | yes |  | Originator Statement Line | related `move_id.statement_line_id` |
| `statement_id` | Many2one | (from related) |  | yes |  |  | related `statement_line_id.statement_id` |
| `tax_ids` | Many2many | `account.tax` (table `account_move_line_account_tax_rel`) |  | yes |  | Taxes | compute `_compute_tax_ids` |
| `group_tax_id` | Many2one | `account.tax` |  | yes |  | Originator Group of Taxes |  |
| `tax_line_id` | Many2one | `account.tax` |  | yes |  | Originator Tax | related `tax_repartition_line_id.tax_id` |
| `tax_group_id` | Many2one | (from related) |  | yes |  | Originator tax group | related `tax_line_id.tax_group_id` |
| `tax_base_amount` | Monetary |  |  | yes |  | Base Amount |  |
| `tax_repartition_line_id` | Many2one | `account.tax.repartition.line` |  | yes |  | Originator Tax Distribution Line |  |
| `tax_tag_ids` | Many2many | `account.account.tag` |  | yes |  | Tags |  |
| `tax_tag_invert` | Boolean |  |  | yes |  | Invert Tags | compute `_compute_tax_tag_invert` |
| `amount_residual` | Monetary |  |  | yes |  | Residual Amount | compute `_compute_amount_residual` |
| `amount_residual_currency` | Monetary |  |  | yes |  | Residual Amount in Currency | compute `_compute_amount_residual` |
| `reconciled` | Boolean |  |  | yes |  |  | compute `_compute_amount_residual` |
| `full_reconcile_id` | Many2one | `account.full.reconcile` |  | yes |  | Matching |  |
| `matched_debit_ids` | One2many | `account.partial.reconcile` (inverse `credit_move_id`) |  | no (inverse) |  | Matched Debits |  |
| `matched_credit_ids` | One2many | `account.partial.reconcile` (inverse `debit_move_id`) |  | no (inverse) |  | Matched Credits |  |
| `matching_number` | Char |  |  | yes |  | Matching # |  |
| `is_account_reconcile` | Boolean |  |  | no |  | Account Reconcile | related `account_id.reconcile` |
| `account_type` | Selection |  |  | no |  | Internal Type | related `account_id.account_type` |
| `account_internal_group` | Selection |  |  | no |  |  | related `account_id.internal_group` |
| `account_root_id` | Many2one | (from related) |  | yes |  | Account Root | related `account_id.root_id` |
| `display_type` | Selection |  | yes | yes | `product` Product, `cogs` Cost of Goods Sold, `tax` Tax, `discount` Discount, `rounding` Rounding, `payment_term` Payment Term, `line_section` Section, `line_note` Note, `epd` Early Payment Discount |  | compute `_compute_display_type` |
| `product_id` | Many2one | `product.product` |  | yes |  | Product |  |
| `product_uom_id` | Many2one | `uom.uom` |  | yes |  | Unit of Measure | compute `_compute_product_uom_id` |
| `product_uom_category_id` | Many2one | `uom.category` |  | no |  |  | related `product_id.uom_id.category_id` |
| `quantity` | Float |  |  | yes |  | Quantity | compute `_compute_quantity` |
| `date_maturity` | Date |  |  | yes |  | Due Date |  |
| `price_unit` | Float |  |  | yes |  | Unit Price | compute `_compute_price_unit` |
| `price_subtotal` | Monetary |  |  | yes |  | Subtotal | compute `_compute_totals` |
| `price_total` | Monetary |  |  | yes |  | Total | compute `_compute_totals` |
| `discount` | Float |  |  | yes | default: `0.0` | Discount (%) |  |
| `tax_calculation_rounding_method` | Selection |  |  | no |  | Tax calculation rounding method | related `company_id.tax_calculation_rounding_method` |
| `term_key` | Binary |  |  | no |  |  | compute `_compute_term_key` |
| `tax_key` | Binary |  |  | no |  |  | compute `_compute_tax_key` |
| `compute_all_tax` | Binary |  |  | no |  |  | compute `_compute_all_tax` |
| `compute_all_tax_dirty` | Boolean |  |  | no |  |  | compute `_compute_all_tax` |
| `epd_key` | Binary |  |  | no |  |  | compute `_compute_epd_key` |
| `epd_needed` | Binary |  |  | no |  |  | compute `_compute_epd_needed` |
| `epd_dirty` | Boolean |  |  | no |  |  | compute `_compute_epd_needed` |
| `discount_allocation_key` | Binary |  |  | no |  |  | compute `_compute_discount_allocation_key` |
| `discount_allocation_needed` | Binary |  |  | no |  |  | compute `_compute_discount_allocation_needed` |
| `discount_allocation_dirty` | Boolean |  |  | no |  |  | compute `_compute_discount_allocation_needed` |
| `analytic_line_ids` | One2many | `account.analytic.line` (inverse `move_line_id`) |  | no (inverse) |  | Analytic lines |  |
| `analytic_distribution` | Json |  |  | yes |  |  |  |
| `discount_date` | Date |  |  | yes |  | Discount Date |  |
| `discount_amount_currency` | Monetary |  |  | yes |  | Discount amount in Currency |  |
| `discount_balance` | Monetary |  |  | yes |  | Discount Balance |  |
| `payment_date` | Date |  |  | no |  | Payment Date | compute `_compute_payment_date` |
| `blocked` | Boolean |  |  | yes | default: `False` | No Follow-up |  |
| `is_refund` | Boolean |  |  | no |  |  | compute `_compute_is_refund` |

SQL constraints:

- `check_credit_debit`: `CHECK(display_type IN ('line_section', 'line_note') OR credit * debit=0)`
- `check_amount_currency_balance_sign`: `CHECK(                 display_type IN ('line_section', 'line_note')                 OR (                     (balance <= 0 AND amount_currency <= 0)                     OR                     (balance >= 0 AND amount_currency >= 0)                 )             )`
- `check_accountable_required_fields`: `CHECK(display_type IN ('line_section', 'line_note') OR account_id IS NOT NULL)`
- `check_non_accountable_fields_null`: `CHECK(display_type NOT IN ('line_section', 'line_note') OR (amount_currency = 0 AND debit = 0 AND credit = 0 AND account_id IS NULL))`

## `account.partial.reconcile`

Table `account_partial_reconcile`.
Description: Partial Reconcile.
Source: `account_partial_reconcile.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `debit_move_id` | Many2one | `account.move.line` | yes | yes |  |  |  |
| `credit_move_id` | Many2one | `account.move.line` | yes | yes |  |  |  |
| `full_reconcile_id` | Many2one | `account.full.reconcile` |  | yes |  | Full Reconcile |  |
| `exchange_move_id` | Many2one | `account.move` |  | yes |  |  |  |
| `company_currency_id` | Many2one | `res.currency` |  | no |  | Company Currency | related `company_id.currency_id` |
| `debit_currency_id` | Many2one | `res.currency` |  | yes |  | Currency of the debit journal item. | related `debit_move_id.currency_id` |
| `credit_currency_id` | Many2one | `res.currency` |  | yes |  | Currency of the credit journal item. | related `credit_move_id.currency_id` |
| `amount` | Monetary |  |  | yes |  |  |  |
| `debit_amount_currency` | Monetary |  |  | yes |  |  |  |
| `credit_amount_currency` | Monetary |  |  | yes |  |  |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | compute `_compute_company_id` |
| `max_date` | Date |  |  | yes |  | Max Date of Matched Lines | compute `_compute_max_date` |

## `account.payment`

Table `account_payment`.
Description: Payments.
Inherits: `mail.thread.main.attachment`, `mail.activity.mixin`.
Delegates (`_inherits`): `{'account.move': 'move_id'}`.
Order: `date desc, name desc`.
Source: `account_payment.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `move_id` | Many2one | `account.move` | yes | yes |  | Journal Entry |  |
| `is_reconciled` | Boolean |  |  | yes |  | Is Reconciled | compute `_compute_reconciliation_status` |
| `is_matched` | Boolean |  |  | yes |  | Is Matched With a Bank Statement | compute `_compute_reconciliation_status` |
| `available_partner_bank_ids` | Many2many | `res.partner.bank` |  | no |  |  | compute `_compute_available_partner_bank_ids` |
| `partner_bank_id` | Many2one | `res.partner.bank` |  | yes |  | Recipient Bank Account | compute `_compute_partner_bank_id` |
| `is_internal_transfer` | Boolean |  |  | yes |  | Internal Transfer | compute `_compute_is_internal_transfer` |
| `qr_code` | Html |  |  | no |  | QR Code URL | compute `_compute_qr_code` |
| `paired_internal_transfer_payment_id` | Many2one | `account.payment` |  | yes |  |  |  |
| `payment_method_line_id` | Many2one | `account.payment.method.line` |  | yes |  | Payment Method | compute `_compute_payment_method_line_id` |
| `available_payment_method_line_ids` | Many2many | `account.payment.method.line` |  | no |  |  | compute `_compute_payment_method_line_fields` |
| `payment_method_id` | Many2one | (from related) |  | yes |  | Method | related `payment_method_line_id.payment_method_id` |
| `available_journal_ids` | Many2many | `account.journal` |  | no |  |  | compute `_compute_available_journal_ids` |
| `amount` | Monetary |  |  | yes |  |  |  |
| `payment_type` | Selection |  | yes | yes | `outbound` Send, `inbound` Receive; default: `'inbound'` | Payment Type |  |
| `partner_type` | Selection |  | yes | yes | `customer` Customer, `supplier` Vendor; default: `'customer'` |  |  |
| `payment_reference` | Char |  |  | yes |  | Payment Reference |  |
| `currency_id` | Many2one | `res.currency` |  | yes |  | Currency | compute `_compute_currency_id` |
| `partner_id` | Many2one | `res.partner` |  | yes |  | Customer/Vendor | compute `_compute_partner_id` |
| `outstanding_account_id` | Many2one | `account.account` |  | yes |  | Outstanding Account | compute `_compute_outstanding_account_id` |
| `destination_account_id` | Many2one | `account.account` |  | yes |  | Destination Account | compute `_compute_destination_account_id` |
| `destination_journal_id` | Many2one | `account.journal` |  | yes |  | Destination Journal |  |
| `reconciled_invoice_ids` | Many2many | `account.move` |  | no |  | Reconciled Invoices | compute `_compute_stat_buttons_from_reconciliation` |
| `reconciled_invoices_count` | Integer |  |  | no |  | # Reconciled Invoices | compute `_compute_stat_buttons_from_reconciliation` |
| `reconciled_invoices_type` | Selection |  |  | no | `credit_note` Credit Note, `invoice` Invoice |  | compute `_compute_stat_buttons_from_reconciliation` |
| `reconciled_bill_ids` | Many2many | `account.move` |  | no |  | Reconciled Bills | compute `_compute_stat_buttons_from_reconciliation` |
| `reconciled_bills_count` | Integer |  |  | no |  | # Reconciled Bills | compute `_compute_stat_buttons_from_reconciliation` |
| `reconciled_statement_line_ids` | Many2many | `account.bank.statement.line` |  | no |  | Reconciled Statement Lines | compute `_compute_stat_buttons_from_reconciliation` |
| `reconciled_statement_lines_count` | Integer |  |  | no |  | # Reconciled Statement Lines | compute `_compute_stat_buttons_from_reconciliation` |
| `payment_method_code` | Char |  |  | no |  |  | related `payment_method_line_id.code` |
| `show_partner_bank_account` | Boolean |  |  | no |  |  | compute `_compute_show_require_partner_bank` |
| `require_partner_bank_account` | Boolean |  |  | no |  |  | compute `_compute_show_require_partner_bank` |
| `country_code` | Char |  |  | no |  |  | related `company_id.account_fiscal_country_id.code` |
| `amount_signed` | Monetary |  |  | no |  |  | compute `_compute_amount_signed` |
| `amount_company_currency_signed` | Monetary |  |  | yes |  |  | compute `_compute_amount_company_currency_signed` |

SQL constraints:

- `check_amount_not_negative`: `CHECK(amount >= 0.0)`

## `account.payment.method`

Table `account_payment_method`.
Description: Payment Methods.
Source: `account_payment_method.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `code` | Char |  | yes | yes |  |  |  |
| `payment_type` | Selection |  | yes | yes | `inbound` Inbound, `outbound` Outbound |  |  |

SQL constraints:

- `name_code_unique`: `unique (code, payment_type)`

## `account.payment.method.line`

Table `account_payment_method_line`.
Description: Payment Methods.
Order: `sequence, id`.
Source: `account_payment_method.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  |  | compute `_compute_name` |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |
| `payment_method_id` | Many2one | `account.payment.method` | yes | yes |  | Payment Method |  |
| `payment_account_id` | Many2one | `account.account` |  | yes |  |  |  |
| `journal_id` | Many2one | `account.journal` |  | yes |  |  |  |
| `code` | Char |  |  | no |  |  | related `payment_method_id.code` |
| `payment_type` | Selection |  |  | no |  |  | related `payment_method_id.payment_type` |
| `company_id` | Many2one | (from related) |  | no |  |  | related `journal_id.company_id` |
| `available_payment_method_ids` | Many2many | (from related) |  | no |  |  | related `journal_id.available_payment_method_ids` |

## `account.payment.term`

Table `account_payment_term`.
Description: Payment Terms.
Order: `sequence, id`.
Source: `account_payment_term.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Payment Terms |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `note` | Html |  |  | yes |  | Description on the Invoice |  |
| `line_ids` | One2many | `account.payment.term.line` (inverse `payment_id`) |  | no (inverse) | default: (computed) | Terms |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company |  |
| `fiscal_country_codes` | Char |  |  | no |  |  | compute `_compute_fiscal_country_codes` |
| `sequence` | Integer |  | yes | yes | default: `10` |  |  |
| `currency_id` | Many2one | `res.currency` |  | no |  |  | compute `_compute_currency_id` |
| `display_on_invoice` | Boolean |  |  | yes | default: `True` | Show installment dates |  |
| `example_amount` | Monetary |  |  | no | default: `1000` |  |  |
| `example_date` | Date |  |  | no | default: (computed) | Date example |  |
| `example_invalid` | Boolean |  |  | no |  |  | compute `_compute_example_invalid` |
| `example_preview` | Html |  |  | no |  |  | compute `_compute_example_preview` |
| `example_preview_discount` | Html |  |  | no |  |  | compute `_compute_example_preview` |
| `discount_percentage` | Float |  |  | yes | default: `2.0` | Discount % |  |
| `discount_days` | Integer |  |  | yes | default: `10` | Discount Days |  |
| `early_pay_discount_computation` | Selection |  |  | yes | `included` On early payment, `excluded` Never, `mixed` Always (upon invoice) | Cash Discount Tax Reduction | compute `_compute_discount_computation` |
| `early_discount` | Boolean |  |  | yes |  | Early Discount |  |

## `account.payment.term.line`

Table `account_payment_term_line`.
Description: Payment Terms Line.
Order: `id`.
Source: `account_payment_term.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `value` | Selection |  | yes | yes | `percent` Percent, `fixed` Fixed; default: `'percent'` |  |  |
| `value_amount` | Float |  |  | yes |  | Due | compute `_compute_value_amount` |
| `delay_type` | Selection |  | yes | yes | `days_after` Days after invoice date, `days_after_end_of_month` Days after end of month, `days_after_end_of_next_month` Days after end of next month; default: `'days_after'` |  |  |
| `nb_days` | Integer |  |  | yes |  | Days | compute `_compute_days` |
| `payment_id` | Many2one | `account.payment.term` | yes | yes |  | Payment Terms |  |

## `account.reconcile.model`

Table `account_reconcile_model`.
Description: Preset to create journal entries during a invoices and payments matching.
Inherits: `mail.thread`.
Order: `sequence, id`.
Source: `account_reconcile_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `name` | Char |  | yes | yes |  | Name |  |
| `sequence` | Integer |  | yes | yes | default: `10` |  |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `rule_type` | Selection |  | yes | yes | `writeoff_button` Button to generate counterpart entry, `writeoff_suggestion` Rule to suggest counterpart entry, `invoice_matching` Rule to match invoices/bills; default: `'writeoff_button'` | Type |  |
| `auto_reconcile` | Boolean |  |  | yes |  | Auto-validate |  |
| `to_check` | Boolean |  |  | yes | default: `False` | To Check |  |
| `matching_order` | Selection |  | yes | yes | `old_first` Oldest first, `new_first` Newest first; default: `'old_first'` |  |  |
| `match_text_location_label` | Boolean |  |  | yes | default: `True` |  |  |
| `match_text_location_note` | Boolean |  |  | yes | default: `False` |  |  |
| `match_text_location_reference` | Boolean |  |  | yes | default: `False` |  |  |
| `match_journal_ids` | Many2many | `account.journal` |  | yes |  | Journals Availability |  |
| `match_nature` | Selection |  | yes | yes | `amount_received` Received, `amount_paid` Paid, `both` Paid/Received; default: `'both'` | Amount Type |  |
| `match_amount` | Selection |  |  | yes | `lower` Is Lower Than, `greater` Is Greater Than, `between` Is Between | Amount Condition |  |
| `match_amount_min` | Float |  |  | yes |  | Amount Min Parameter |  |
| `match_amount_max` | Float |  |  | yes |  | Amount Max Parameter |  |
| `match_label` | Selection |  |  | yes | `contains` Contains, `not_contains` Not Contains, `match_regex` Match Regex | Label |  |
| `match_label_param` | Char |  |  | yes |  | Label Parameter |  |
| `match_note` | Selection |  |  | yes | `contains` Contains, `not_contains` Not Contains, `match_regex` Match Regex | Note |  |
| `match_note_param` | Char |  |  | yes |  | Note Parameter |  |
| `match_transaction_type` | Selection |  |  | yes | `contains` Contains, `not_contains` Not Contains, `match_regex` Match Regex | Transaction Type |  |
| `match_transaction_type_param` | Char |  |  | yes |  | Transaction Type Parameter |  |
| `match_same_currency` | Boolean |  |  | yes | default: `True` | Same Currency |  |
| `allow_payment_tolerance` | Boolean |  |  | yes | default: `True` | Payment Tolerance |  |
| `payment_tolerance_param` | Float |  |  | yes |  | Gap | compute `_compute_payment_tolerance_param` |
| `payment_tolerance_type` | Selection |  | yes | yes | `percentage` in percentage, `fixed_amount` in amount; default: `'percentage'` |  |  |
| `match_partner` | Boolean |  |  | yes |  | Partner is Set |  |
| `match_partner_ids` | Many2many | `res.partner` |  | yes |  | Matching partners |  |
| `match_partner_category_ids` | Many2many | `res.partner.category` |  | yes |  | Matching categories |  |
| `line_ids` | One2many | `account.reconcile.model.line` (inverse `model_id`) |  | no (inverse) |  |  |  |
| `partner_mapping_line_ids` | One2many | `account.reconcile.model.partner.mapping` (inverse `model_id`) |  | no (inverse) |  | Partner Mapping Lines |  |
| `past_months_limit` | Integer |  |  | yes | default: `18` | Search Months Limit |  |
| `decimal_separator` | Char |  |  | yes | default: (computed) |  |  |
| `show_decimal_separator` | Boolean |  |  | no |  |  | compute `_compute_show_decimal_separator` |
| `number_entries` | Integer |  |  | no |  | Number of entries related to this model | compute `_compute_number_entries` |

SQL constraints:

- `name_unique`: `unique(name, company_id)`

## `account.reconcile.model.line`

Table `account_reconcile_model_line`.
Description: Rules for the reconciliation model.
Inherits: `analytic.mixin`.
Order: `sequence, id`.
Source: `account_reconcile_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `model_id` | Many2one | `account.reconcile.model` |  | yes |  |  |  |
| `allow_payment_tolerance` | Boolean |  |  | no |  |  | related `model_id.allow_payment_tolerance` |
| `payment_tolerance_param` | Float |  |  | no |  |  | related `model_id.payment_tolerance_param` |
| `rule_type` | Selection |  |  | no |  |  | related `model_id.rule_type` |
| `company_id` | Many2one | (from related) |  | yes |  |  | related `model_id.company_id` |
| `sequence` | Integer |  | yes | yes | default: `10` |  |  |
| `account_id` | Many2one | `account.account` | yes | yes |  | Account |  |
| `journal_id` | Many2one | `account.journal` |  | yes |  | Journal |  |
| `label` | Char |  |  | yes |  | Journal Item Label |  |
| `amount_type` | Selection |  | yes | yes | `fixed` Fixed, `percentage` Percentage of balance, `percentage_st_line` Percentage of statement line, `regex` From label; default: `'percentage'` |  |  |
| `show_force_tax_included` | Boolean |  |  | no |  |  | compute `_compute_show_force_tax_included` |
| `force_tax_included` | Boolean |  |  | yes |  | Tax Included in Price |  |
| `amount` | Float |  |  | yes |  | Float Amount | compute `_compute_float_amount` |
| `amount_string` | Char |  | yes | yes | default: `'100'` | Amount |  |
| `tax_ids` | Many2many | `account.tax` (table `account_reconcile_model_line_account_tax_rel`) |  | yes |  | Taxes |  |

## `account.reconcile.model.partner.mapping`

Table `account_reconcile_model_partner_mapping`.
Description: Partner mapping for reconciliation models.
Source: `account_reconcile_model.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `model_id` | Many2one | `account.reconcile.model` | yes | yes |  |  |  |
| `company_id` | Many2one | (from related) |  | no |  |  | related `model_id.company_id` |
| `partner_id` | Many2one | `res.partner` | yes | yes |  | Partner |  |
| `payment_ref_regex` | Char |  |  | yes |  | Find Text in Label |  |
| `narration_regex` | Char |  |  | yes |  | Find Text in Notes |  |

## `account.report`

Table `account_report`.
Description: Accounting Report.
Order: `sequence, id`.
Source: `account_report.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `sequence` | Integer |  |  | yes |  | Sequence |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `line_ids` | One2many | `account.report.line` (inverse `report_id`) |  | no (inverse) |  | Lines |  |
| `column_ids` | One2many | `account.report.column` (inverse `report_id`) |  | no (inverse) |  | Columns |  |
| `root_report_id` | Many2one | `account.report` |  | yes |  | Root Report |  |
| `variant_report_ids` | One2many | `account.report` (inverse `root_report_id`) |  | no (inverse) |  | Variants |  |
| `section_report_ids` | Many2many | `account.report` (table `account_report_section_rel`) |  | yes |  | Sections |  |
| `section_main_report_ids` | Many2many | `account.report` (table `account_report_section_rel`) |  | yes |  | Section Of |  |
| `use_sections` | Boolean |  |  | yes |  | Composite Report | compute `_compute_use_sections` |
| `chart_template` | Selection |  |  | yes | (dynamic: lambda self: self.env['account.chart.template']._select_chart_template()) | Chart of Accounts |  |
| `country_id` | Many2one | `res.country` |  | yes |  | Country |  |
| `only_tax_exigible` | Boolean |  |  | yes |  | Only Tax Exigible Lines | compute `lambda x: x._compute_report_option_filter('only_tax_exigible')` |
| `availability_condition` | Selection |  |  | yes | `country` Country Matches, `coa` Chart of Accounts Matches, `always` Always | Availability | compute `_compute_default_availability_condition` |
| `load_more_limit` | Integer |  |  | yes |  | Load More Limit |  |
| `search_bar` | Boolean |  |  | yes |  | Search Bar |  |
| `prefix_groups_threshold` | Integer |  |  | yes |  | Prefix Groups Threshold |  |
| `default_opening_date_filter` | Selection |  |  | yes | `this_year` This Year, `this_quarter` This Quarter, `this_month` This Month, `today` Today, `last_month` Last Month, `last_quarter` Last Quarter, `last_year` Last Year, `this_tax_period` This Tax Period, `last_tax_period` Last Tax Period | Default Opening | compute `lambda x: x._compute_report_option_filter('default_opening_date_filter', 'last_month')` |
| `filter_multi_company` | Selection |  |  | yes | `disabled` Disabled, `selector` Use Company Selector, `tax_units` Use Tax Units | Multi-Company | compute `lambda x: x._compute_report_option_filter('filter_multi_company', 'disabled')` |
| `filter_date_range` | Boolean |  |  | yes |  | Date Range | compute `lambda x: x._compute_report_option_filter('filter_date_range', True)` |
| `filter_show_draft` | Boolean |  |  | yes |  | Draft Entries | compute `lambda x: x._compute_report_option_filter('filter_show_draft', True)` |
| `filter_unreconciled` | Boolean |  |  | yes |  | Unreconciled Entries | compute `lambda x: x._compute_report_option_filter('filter_unreconciled', False)` |
| `filter_unfold_all` | Boolean |  |  | yes |  | Unfold All | compute `lambda x: x._compute_report_option_filter('filter_unfold_all')` |
| `filter_hide_0_lines` | Selection |  |  | yes | `by_default` Enabled by Default, `optional` Optional, `never` Never | Hide lines at 0 | compute `lambda x: x._compute_report_option_filter('filter_hide_0_lines', 'optional')` |
| `filter_period_comparison` | Boolean |  |  | yes |  | Period Comparison | compute `lambda x: x._compute_report_option_filter('filter_period_comparison', True)` |
| `filter_growth_comparison` | Boolean |  |  | yes |  | Growth Comparison | compute `lambda x: x._compute_report_option_filter('filter_growth_comparison', True)` |
| `filter_journals` | Boolean |  |  | yes |  | Journals | compute `lambda x: x._compute_report_option_filter('filter_journals')` |
| `filter_analytic` | Boolean |  |  | yes |  | Analytic Filter | compute `lambda x: x._compute_report_option_filter('filter_analytic')` |
| `filter_hierarchy` | Selection |  |  | yes | `by_default` Enabled by Default, `optional` Optional, `never` Never | Account Groups | compute `lambda x: x._compute_report_option_filter('filter_hierarchy', 'optional')` |
| `filter_account_type` | Selection |  |  | yes | `both` Payable and receivable, `payable` Payable, `receivable` Receivable, `disabled` Disabled | Account Types | compute `lambda x: x._compute_report_option_filter('filter_account_type', 'disabled')` |
| `filter_partner` | Boolean |  |  | yes |  | Partners | compute `lambda x: x._compute_report_option_filter('filter_partner')` |
| `filter_fiscal_position` | Boolean |  |  | yes |  | Filter Multivat | compute `lambda x: x._compute_report_option_filter('filter_fiscal_position')` |
| `filter_aml_ir_filters` | Boolean |  |  | yes |  | Favorite Filters | compute `lambda x: x._compute_report_option_filter('filter_aml_ir_filters')` |

## `account.report.column`

Table `account_report_column`.
Description: Accounting Report Column.
Order: `sequence, id`.
Source: `account_report.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `expression_label` | Char |  | yes | yes |  | Expression Label |  |
| `sequence` | Integer |  |  | yes |  | Sequence |  |
| `report_id` | Many2one | `account.report` |  | yes |  | Report |  |
| `sortable` | Boolean |  |  | yes |  | Sortable |  |
| `figure_type` | Selection |  | yes | yes | `monetary` Monetary, `percentage` Percentage, `integer` Integer, `float` Float, `date` Date, `datetime` Datetime, `boolean` Boolean, `string` String; default: `'monetary'` | Figure Type |  |
| `blank_if_zero` | Boolean |  |  | yes |  | Blank if Zero |  |
| `custom_audit_action_id` | Many2one | `ir.actions.act_window` |  | yes |  | Custom Audit Action |  |

## `account.report.expression`

Table `account_report_expression`.
Description: Accounting Report Expression.
Display name field: `report_line_name`.
Source: `account_report.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `report_line_id` | Many2one | `account.report.line` | yes | yes |  | Report Line |  |
| `report_line_name` | Char |  |  | no |  | Report Line Name | related `report_line_id.name` |
| `label` | Char |  | yes | yes |  | Label |  |
| `engine` | Selection |  | yes | yes | `domain` Odoo Domain, `tax_tags` Tax Tags, `aggregation` Aggregate Other Formulas, `account_codes` Prefix of Account Codes, `external` External Value, `custom` Custom Python Function | Computation Engine |  |
| `formula` | Char |  | yes | yes |  | Formula |  |
| `subformula` | Char |  |  | yes |  | Subformula |  |
| `date_scope` | Selection |  | yes | yes | `from_beginning` From the very start, `from_fiscalyear` From the start of the fiscal year, `to_beginning_of_fiscalyear` At the beginning of the fiscal year, `to_beginning_of_period` At the beginning of the period, `normal` According to each type of account, `strict_range` Strictly on the given dates, `previous_tax_period` From previous tax period; default: `'strict_range'` | Date Scope |  |
| `figure_type` | Selection |  |  | yes | `monetary` Monetary, `percentage` Percentage, `integer` Integer, `float` Float, `date` Date, `datetime` Datetime, `boolean` Boolean, `string` String | Figure Type |  |
| `green_on_positive` | Boolean |  |  | yes | default: `True` | Is Growth Good when Positive |  |
| `blank_if_zero` | Boolean |  |  | yes |  | Blank if Zero |  |
| `auditable` | Boolean |  |  | yes |  | Auditable | compute `_compute_auditable` |
| `carryover_target` | Char |  |  | yes |  | Carry Over To |  |

SQL constraints:

- `domain_engine_subformula_required`: `CHECK(engine != 'domain' OR subformula IS NOT NULL)`
- `line_label_uniq`: `UNIQUE(report_line_id,label)`

## `account.report.external.value`

Table `account_report_external_value`.
Description: Accounting Report External Value.
Order: `date, id`.
Source: `account_report.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `value` | Float |  |  | yes |  | Numeric Value |  |
| `text_value` | Char |  |  | yes |  | Text Value |  |
| `date` | Date |  | yes | yes |  |  |  |
| `target_report_expression_id` | Many2one | `account.report.expression` | yes | yes |  | Target Expression |  |
| `target_report_line_id` | Many2one | (from related) |  | no |  | Target Line | related `target_report_expression_id.report_line_id` |
| `target_report_expression_label` | Char |  |  | no |  | Target Expression Label | related `target_report_expression_id.label` |
| `report_country_id` | Many2one | (from related) |  | no |  | Country | related `target_report_line_id.report_id.country_id` |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `foreign_vat_fiscal_position_id` | Many2one | `account.fiscal.position` |  | yes |  | Fiscal position |  |
| `carryover_origin_expression_label` | Char |  |  | yes |  | Origin Expression Label |  |
| `carryover_origin_report_line_id` | Many2one | `account.report.line` |  | yes |  | Origin Line |  |

## `account.report.line`

Table `account_report_line`.
Description: Accounting Report Line.
Order: `sequence, id`.
Source: `account_report.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `expression_ids` | One2many | `account.report.expression` (inverse `report_line_id`) |  | no (inverse) |  | Expressions |  |
| `report_id` | Many2one | `account.report` | yes | yes |  | Parent Report | compute `_compute_report_id` |
| `hierarchy_level` | Integer |  | yes | yes |  | Level | compute `_compute_hierarchy_level` |
| `parent_id` | Many2one | `account.report.line` |  | yes |  | Parent Line |  |
| `children_ids` | One2many | `account.report.line` (inverse `parent_id`) |  | no (inverse) |  | Child Lines |  |
| `groupby` | Char |  |  | yes |  | Group By |  |
| `user_groupby` | Char |  |  | yes |  | User Group By | compute `_compute_user_groupby` |
| `sequence` | Integer |  |  | yes |  | Sequence |  |
| `code` | Char |  |  | yes |  | Code |  |
| `foldable` | Boolean |  |  | yes |  | Foldable |  |
| `print_on_new_page` | Boolean |  |  | yes |  | Print On New Page |  |
| `action_id` | Many2one | `ir.actions.actions` |  | yes |  | Action |  |
| `hide_if_zero` | Boolean |  |  | yes |  | Hide if Zero |  |
| `domain_formula` | Char |  |  | no |  | Domain Formula Shortcut |  |
| `account_codes_formula` | Char |  |  | no |  | Account Codes Formula Shortcut |  |
| `aggregation_formula` | Char |  |  | no |  | Aggregation Formula Shortcut |  |
| `external_formula` | Char |  |  | no |  | External Formula Shortcut |  |
| `tax_tags_formula` | Char |  |  | no |  | Tax Tags Formula Shortcut |  |

SQL constraints:

- `code_uniq`: `unique (report_id, code)`

## `account.root`

Table `account_root`. Not auto-created (`_auto = False`, SQL view).
Description: Account codes first 2 digits.
Source: `account_account.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  |  |  |
| `parent_id` | Many2one | `account.root` |  | yes |  |  |  |
| `company_id` | Many2one | `res.company` |  | yes |  |  |  |

## `account.tax`

Table `account_tax`.
Description: Tax.
Inherits: `mail.thread`.
Order: `sequence,id`.
Source: `account_tax.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Tax Name |  |
| `name_searchable` | Char |  |  | no |  |  |  |
| `type_tax_use` | Selection |  | yes | yes | `sale` Sales, `purchase` Purchases, `none` None; default: `'sale'` | Tax Type |  |
| `tax_scope` | Selection |  |  | yes | `service` Services, `consu` Goods | Tax Scope |  |
| `amount_type` | Selection |  | yes | yes | `group` Group of Taxes, `fixed` Fixed, `percent` Percentage of Price, `division` Percentage of Price Tax Included; default: `'percent'` | Tax Computation |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `children_tax_ids` | Many2many | `account.tax` (table `account_tax_filiation_rel`) |  | yes |  | Children Taxes |  |
| `sequence` | Integer |  | yes | yes | default: `1` |  |  |
| `amount` | Float |  | yes | yes | default: `0.0` |  |  |
| `description` | Char |  |  | yes |  | Description |  |
| `invoice_label` | Char |  |  | yes |  | Label on Invoices |  |
| `price_include` | Boolean |  |  | yes | default: `False` | Included in Price |  |
| `include_base_amount` | Boolean |  |  | yes | default: `False` | Affect Base of Subsequent Taxes |  |
| `is_base_affected` | Boolean |  |  | yes | default: `True` | Base Affected by Previous Taxes |  |
| `analytic` | Boolean |  |  | yes |  | Include in Analytic Cost |  |
| `tax_group_id` | Many2one | `account.tax.group` | yes | yes |  | Tax Group | compute `_compute_tax_group_id` |
| `hide_tax_exigibility` | Boolean |  |  | no |  | Hide Use Cash Basis Option | related `company_id.tax_exigibility` |
| `tax_exigibility` | Selection |  |  | yes | `on_invoice` Based on Invoice, `on_payment` Based on Payment; default: `'on_invoice'` | Tax Exigibility |  |
| `cash_basis_transition_account_id` | Many2one | `account.account` |  | yes |  | Cash Basis Transition Account |  |
| `invoice_repartition_line_ids` | One2many | `account.tax.repartition.line` (inverse `tax_id`) |  | yes |  | Distribution for Invoices | compute `_compute_invoice_repartition_line_ids` |
| `refund_repartition_line_ids` | One2many | `account.tax.repartition.line` (inverse `tax_id`) |  | yes |  | Distribution for Refund Invoices | compute `_compute_refund_repartition_line_ids` |
| `repartition_line_ids` | One2many | `account.tax.repartition.line` (inverse `tax_id`) |  | no (inverse) |  | Distribution |  |
| `country_id` | Many2one | `res.country` | yes | yes |  | Country | compute `_compute_country_id` |
| `country_code` | Char |  |  | no |  |  | related `country_id.code` |
| `is_used` | Boolean |  |  | no |  | Tax used | compute `_compute_is_used` |
| `repartition_lines_str` | Char |  |  | no |  | Repartition Lines | compute `_compute_repartition_lines_str` |
| `account_move_line_ids` | Many2many | `account.move.line` (table `account_move_line_account_tax_rel`) |  | yes |  |  |  |
| `account_reconcile_model_line_ids` | Many2many | `account.reconcile.model.line` (table `account_reconcile_model_line_account_tax_rel`) |  | yes |  |  |  |

## `account.tax.group`

Table `account_tax_group`.
Description: Tax Group.
Order: `sequence asc, id`.
Source: `account_tax.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  |  |  |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) |  |  |
| `tax_payable_account_id` | Many2one | `account.account` |  | yes |  | Tax Payable Account |  |
| `tax_receivable_account_id` | Many2one | `account.account` |  | yes |  | Tax Receivable Account |  |
| `advance_tax_payment_account_id` | Many2one | `account.account` |  | yes |  | Tax Advance Account |  |
| `country_id` | Many2one | `res.country` |  | yes |  | Country | compute `_compute_country_id` |
| `country_code` | Char |  |  | no |  |  | related `country_id.code` |
| `preceding_subtotal` | Char |  |  | yes |  | Preceding Subtotal |  |

## `account.tax.repartition.line`

Table `account_tax_repartition_line`.
Description: Tax Repartition Line.
Order: `document_type, repartition_type, sequence, id`.
Source: `account_tax.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `factor_percent` | Float |  | yes | yes | default: `100` | % |  |
| `factor` | Float |  |  | no |  | Factor Ratio | compute `_compute_factor` |
| `repartition_type` | Selection |  | yes | yes | `base` Base, `tax` of tax; default: `'tax'` | Based On |  |
| `document_type` | Selection |  | yes | yes | `invoice` Invoice, `refund` Refund | Related to |  |
| `account_id` | Many2one | `account.account` |  | yes |  | Account |  |
| `tag_ids` | Many2many | `account.account.tag` |  | yes |  | Tax Grids |  |
| `tax_id` | Many2one | `account.tax` |  | yes |  |  |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | related `tax_id.company_id` |
| `sequence` | Integer |  |  | yes | default: `1` | Sequence |  |
| `use_in_tax_closing` | Boolean |  |  | yes |  | Tax Closing Entry | compute `_compute_use_in_tax_closing` |
| `tag_ids_domain` | Binary |  |  | no |  | tag domain | compute `_compute_tag_ids_domain` |

## `decimal.precision` (extension)

Adds fields to `decimal.precision`, defined in another module. Every field below is added by this module.
Source: `decimal_precision.py`.

## `digest.digest` (extension)

Adds fields to `digest.digest`, defined in another module. Every field below is added by this module.
Source: `digest.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `kpi_account_total_revenue` | Boolean |  |  | yes |  | Revenue |  |
| `kpi_account_total_revenue_value` | Monetary |  |  | no |  |  | compute `_compute_kpi_account_total_revenue_value` |

## `ir.actions.report` (extension)

Adds fields to `ir.actions.report`, defined in another module. Every field below is added by this module.
Source: `ir_actions_report.py`.

## `ir.attachment` (extension)

Adds fields to `ir.attachment`, defined in another module. Every field below is added by this module.
Source: `ir_attachment.py`.

## `ir.http` (extension)

Adds fields to `ir.http`, defined in another module. Every field below is added by this module.
Source: `ir_http.py`.

## `ir.module.module` (extension)

Adds fields to `ir.module.module`, defined in another module. Every field below is added by this module.
Source: `ir_module.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `account_templates` | Binary |  |  | no |  |  | compute `_compute_account_templates` |

## `kpi.provider` (extension)

Adds fields to `kpi.provider`, defined in another module. Every field below is added by this module.
Source: `kpi_provider.py`.

## `onboarding.onboarding` (extension)

Adds fields to `onboarding.onboarding`, defined in another module. Every field below is added by this module.
Source: `onboarding_onboarding.py`.

## `onboarding.onboarding.step` (extension)

Adds fields to `onboarding.onboarding.step`, defined in another module. Every field below is added by this module.
Source: `onboarding_onboarding_step.py`.

## `product.category` (extension)

Adds fields to `product.category`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `property_account_income_categ_id` | Many2one | `account.account` |  | no (per company, ir.property) |  | Income Account |  |
| `property_account_expense_categ_id` | Many2one | `account.account` |  | no (per company, ir.property) |  | Expense Account |  |

## `product.product` (extension)

Adds fields to `product.product`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `tax_string` | Char |  |  | no |  |  | compute `_compute_tax_string` |

## `product.template` (extension)

Adds fields to `product.template`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `taxes_id` | Many2many | `account.tax` (table `product_taxes_rel`) |  | yes | default: (computed) | Customer Taxes |  |
| `tax_string` | Char |  |  | no |  |  | compute `_compute_tax_string` |
| `supplier_taxes_id` | Many2many | `account.tax` (table `product_supplier_taxes_rel`) |  | yes | default: (computed) | Vendor Taxes |  |
| `property_account_income_id` | Many2one | `account.account` |  | no (per company, ir.property) |  | Income Account |  |
| `property_account_expense_id` | Many2one | `account.account` |  | no (per company, ir.property) |  | Expense Account |  |
| `account_tag_ids` | Many2many | `account.account.tag` |  | yes |  | Account Tags |  |
| `fiscal_country_codes` | Char |  |  | no |  |  | compute `_compute_fiscal_country_codes` |

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Inherits: `mail.thread`.
Source: `company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `fiscalyear_last_day` | Integer |  | yes | yes | default: `31` |  |  |
| `fiscalyear_last_month` | Selection |  | yes | yes | `1` January, `2` February, `3` March, `4` April, `5` May, `6` June, `7` July, `8` August, `9` September, `10` October, `11` November, `12` December; default: `'12'` |  |  |
| `period_lock_date` | Date |  |  | yes |  | Journals Entries Lock Date |  |
| `fiscalyear_lock_date` | Date |  |  | yes |  | All Users Lock Date |  |
| `tax_lock_date` | Date |  |  | yes |  | Tax Return Lock Date |  |
| `max_tax_lock_date` | Date |  |  | no |  |  | compute `_compute_max_tax_lock_date` |
| `transfer_account_id` | Many2one | `account.account` |  | yes |  | Inter-Banks Transfer Account |  |
| `expects_chart_of_accounts` | Boolean |  |  | yes | default: `True` | Expects a Chart of Accounts |  |
| `chart_template` | Selection |  |  | yes | (dynamic: '_chart_template_selection') |  |  |
| `bank_account_code_prefix` | Char |  |  | yes |  | Prefix of the bank accounts |  |
| `cash_account_code_prefix` | Char |  |  | yes |  | Prefix of the cash accounts |  |
| `default_cash_difference_income_account_id` | Many2one | `account.account` |  | yes |  | Cash Difference Income |  |
| `default_cash_difference_expense_account_id` | Many2one | `account.account` |  | yes |  | Cash Difference Expense |  |
| `account_journal_suspense_account_id` | Many2one | `account.account` |  | yes |  | Journal Suspense Account |  |
| `account_journal_payment_debit_account_id` | Many2one | `account.account` |  | yes |  | Journal Outstanding Receipts |  |
| `account_journal_payment_credit_account_id` | Many2one | `account.account` |  | yes |  | Journal Outstanding Payments |  |
| `account_journal_early_pay_discount_gain_account_id` | Many2one | `account.account` |  | yes |  | Cash Discount Write-Off Gain Account |  |
| `account_journal_early_pay_discount_loss_account_id` | Many2one | `account.account` |  | yes |  | Cash Discount Write-Off Loss Account |  |
| `transfer_account_code_prefix` | Char |  |  | yes |  | Prefix of the transfer accounts |  |
| `account_sale_tax_id` | Many2one | `account.tax` |  | yes |  | Default Sale Tax |  |
| `account_purchase_tax_id` | Many2one | `account.tax` |  | yes |  | Default Purchase Tax |  |
| `tax_calculation_rounding_method` | Selection |  |  | yes | `round_per_line` Round per Line, `round_globally` Round Globally; default: `'round_per_line'` | Tax Calculation Rounding Method |  |
| `currency_exchange_journal_id` | Many2one | `account.journal` |  | yes |  | Exchange Gain or Loss Journal |  |
| `income_currency_exchange_account_id` | Many2one | `account.account` |  | yes |  | Gain Exchange Rate Account |  |
| `expense_currency_exchange_account_id` | Many2one | `account.account` |  | yes |  | Loss Exchange Rate Account |  |
| `anglo_saxon_accounting` | Boolean |  |  | yes |  | Use anglo-saxon accounting |  |
| `bank_journal_ids` | One2many | `account.journal` (inverse `company_id`) |  | no (inverse) |  | Bank Journals |  |
| `incoterm_id` | Many2one | `account.incoterms` |  | yes |  | Default incoterm |  |
| `qr_code` | Boolean |  |  | yes |  | Display QR-code on invoices |  |
| `invoice_is_email` | Boolean |  |  | yes | default: `True` | Email by default |  |
| `invoice_is_download` | Boolean |  |  | yes | default: `True` | Download by default |  |
| `display_invoice_amount_total_words` | Boolean |  |  | yes |  | Total amount of invoice in letters |  |
| `account_use_credit_limit` | Boolean |  |  | yes |  | Sales Credit Limit |  |
| `account_opening_move_id` | Many2one | `account.move` |  | yes |  | Opening Journal Entry |  |
| `account_opening_journal_id` | Many2one | `account.journal` |  | no |  | Opening Journal | related `account_opening_move_id.journal_id` |
| `account_opening_date` | Date |  | yes | yes | default: (computed) | Opening Entry |  |
| `invoice_terms` | Html |  |  | yes |  | Default Terms and Conditions |  |
| `terms_type` | Selection |  |  | yes | `plain` Add a Note, `html` Add a link to a Web Page; default: `'plain'` | Terms & Conditions format |  |
| `invoice_terms_html` | Html |  |  | yes |  | Default Terms and Conditions as a Web page | compute `_compute_invoice_terms_html` |
| `account_default_pos_receivable_account_id` | Many2one | `account.account` |  | yes |  | Default PoS Receivable Account |  |
| `expense_accrual_account_id` | Many2one | `account.account` |  | yes |  |  |  |
| `revenue_accrual_account_id` | Many2one | `account.account` |  | yes |  |  |  |
| `automatic_entry_default_journal_id` | Many2one | `account.journal` |  | yes |  |  |  |
| `country_code` | Char |  |  | no |  |  | related `country_id.code` |
| `account_fiscal_country_id` | Many2one | `res.country` |  | yes |  | Fiscal Country | compute `compute_account_tax_fiscal_country` |
| `account_enabled_tax_country_ids` | Many2many | `res.country` |  | no |  | l10n-used countries | compute `_compute_account_enabled_tax_country_ids` |
| `tax_exigibility` | Boolean |  |  | yes |  | Use Cash Basis |  |
| `tax_cash_basis_journal_id` | Many2one | `account.journal` |  | yes |  | Cash Basis Journal |  |
| `account_cash_basis_base_account_id` | Many2one | `account.account` |  | yes |  | Base Tax Received Account |  |
| `account_storno` | Boolean |  |  | yes |  | Storno accounting |  |
| `fiscal_position_ids` | One2many | `account.fiscal.position` (inverse `company_id`) |  | no (inverse) |  |  |  |
| `multi_vat_foreign_country_ids` | Many2many | `res.country` |  | no |  | Foreign VAT countries | compute `_compute_multi_vat_foreign_country` |
| `quick_edit_mode` | Selection |  |  | yes | `out_invoices` Customer Invoices, `in_invoices` Vendor Bills, `out_and_in_invoices` Customer Invoices and Vendor Bills | Quick encoding |  |
| `account_discount_income_allocation_id` | Many2one | `account.account` |  | yes |  | Separate account for income discount |  |
| `account_discount_expense_allocation_id` | Many2one | `account.account` |  | yes |  | Separate account for expense discount |  |

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `has_accounting_entries` | Boolean |  |  | no |  |  | compute `_compute_has_chart_of_accounts` |
| `currency_id` | Many2one | `res.currency` | yes | no |  | Currency | related `company_id.currency_id` |
| `currency_exchange_journal_id` | Many2one | `account.journal` |  | no |  | Currency Exchange Journal | related `company_id.currency_exchange_journal_id` |
| `income_currency_exchange_account_id` | Many2one | `account.account` |  | no |  | Gain Exchange Rate Account | related `company_id.income_currency_exchange_account_id` |
| `expense_currency_exchange_account_id` | Many2one | `account.account` |  | no |  | Loss Exchange Rate Account | related `company_id.expense_currency_exchange_account_id` |
| `has_chart_of_accounts` | Boolean |  |  | no |  | Company has a chart of accounts | compute `_compute_has_chart_of_accounts` |
| `chart_template` | Selection |  |  | yes | (dynamic: lambda self: self.env.company._chart_template_selection()); default: (computed) |  |  |
| `sale_tax_id` | Many2one | `account.tax` |  | no |  | Default Sale Tax | related `company_id.account_sale_tax_id` |
| `purchase_tax_id` | Many2one | `account.tax` |  | no |  | Default Purchase Tax | related `company_id.account_purchase_tax_id` |
| `tax_calculation_rounding_method` | Selection |  |  | no |  | Tax calculation rounding method | related `company_id.tax_calculation_rounding_method` |
| `account_journal_suspense_account_id` | Many2one | `account.account` |  | no |  | Bank Suspense | related `company_id.account_journal_suspense_account_id` |
| `account_journal_payment_debit_account_id` | Many2one | `account.account` |  | no |  | Outstanding Receipts | related `company_id.account_journal_payment_debit_account_id` |
| `account_journal_payment_credit_account_id` | Many2one | `account.account` |  | no |  | Outstanding Payments | related `company_id.account_journal_payment_credit_account_id` |
| `transfer_account_id` | Many2one | `account.account` |  | no |  | Internal Transfer | related `company_id.transfer_account_id` |
| `module_account_accountant` | Boolean |  |  | yes |  | Accounting |  |
| `group_warning_account` | Boolean |  |  | yes |  | Warnings in Invoices |  |
| `group_cash_rounding` | Boolean |  |  | yes |  | Cash Rounding |  |
| `group_show_sale_receipts` | Boolean |  |  | yes |  | Sale Receipt |  |
| `group_show_purchase_receipts` | Boolean |  |  | yes |  | Purchase Receipt |  |
| `module_account_budget` | Boolean |  |  | yes |  | Budget Management |  |
| `module_account_payment` | Boolean |  |  | yes |  | Invoice Online Payment |  |
| `module_account_reports` | Boolean |  |  | yes |  | Dynamic Reports |  |
| `module_account_check_printing` | Boolean |  |  | yes |  | Allow check printing and deposits |  |
| `module_account_batch_payment` | Boolean |  |  | yes |  | Use batch payments |  |
| `module_account_sepa` | Boolean |  |  | yes |  | SEPA Credit Transfer (SCT) |  |
| `module_account_sepa_direct_debit` | Boolean |  |  | yes |  | Use SEPA Direct Debit |  |
| `module_account_bank_statement_import_qif` | Boolean |  |  | yes |  | Import .qif files |  |
| `module_account_bank_statement_import_ofx` | Boolean |  |  | yes |  | Import in .ofx format |  |
| `module_account_bank_statement_import_csv` | Boolean |  |  | yes |  | Import in .csv, .xls, and .xlsx format |  |
| `module_account_bank_statement_import_camt` | Boolean |  |  | yes |  | Import in CAMT.053 format |  |
| `module_currency_rate_live` | Boolean |  |  | yes |  | Automatic Currency Rates |  |
| `module_account_intrastat` | Boolean |  |  | yes |  | Intrastat |  |
| `module_product_margin` | Boolean |  |  | yes |  | Allow Product Margin |  |
| `module_l10n_eu_oss` | Boolean |  |  | yes |  | EU Intra-community Distance Selling |  |
| `module_account_taxcloud` | Boolean |  |  | yes |  | Account TaxCloud |  |
| `module_account_avatax` | Boolean |  |  | yes |  | Account Avatax |  |
| `module_account_invoice_extract` | Boolean |  |  | yes |  | Document Digitization |  |
| `module_snailmail_account` | Boolean |  |  | yes |  | Snailmail |  |
| `module_account_peppol` | Boolean |  |  | yes |  | PEPPOL Invoicing |  |
| `tax_exigibility` | Boolean |  |  | no |  | Cash Basis | related `company_id.tax_exigibility` |
| `tax_cash_basis_journal_id` | Many2one | `account.journal` |  | no |  | Tax Cash Basis Journal | related `company_id.tax_cash_basis_journal_id` |
| `account_cash_basis_base_account_id` | Many2one | `account.account` |  | no |  | Base Tax Received Account | related `company_id.account_cash_basis_base_account_id` |
| `account_fiscal_country_id` | Many2one | (from related) |  | no |  | Fiscal Country Code | related `company_id.account_fiscal_country_id` |
| `qr_code` | Boolean |  |  | no |  | Display SEPA QR-code | related `company_id.qr_code` |
| `invoice_is_download` | Boolean |  |  | no |  | Download | related `company_id.invoice_is_download` |
| `invoice_is_email` | Boolean |  |  | no |  | Send Email | related `company_id.invoice_is_email` |
| `incoterm_id` | Many2one | `account.incoterms` |  | no |  | Default incoterm | related `company_id.incoterm_id` |
| `invoice_terms` | Html |  |  | no |  | Terms & Conditions | related `company_id.invoice_terms` |
| `invoice_terms_html` | Html |  |  | no |  | Terms & Conditions as a Web page | related `company_id.invoice_terms_html` |
| `terms_type` | Selection |  |  | no |  |  | related `company_id.terms_type` |
| `display_invoice_amount_total_words` | Boolean |  |  | no |  | Total amount of invoice in letters | related `company_id.display_invoice_amount_total_words` |
| `preview_ready` | Boolean |  |  | no |  | Display preview button | compute `_compute_terms_preview` |
| `use_invoice_terms` | Boolean |  |  | yes |  | Default Terms & Conditions |  |
| `account_use_credit_limit` | Boolean |  |  | no |  | Sales Credit Limit | related `company_id.account_use_credit_limit` |
| `account_default_credit_limit` | Monetary |  |  | no |  | Default Credit Limit | compute `_compute_account_default_credit_limit` |
| `country_code` | Char |  |  | no |  |  | related `company_id.account_fiscal_country_id.code` |
| `account_storno` | Boolean |  |  | no |  | Storno accounting | related `company_id.account_storno` |
| `group_sale_delivery_address` | Boolean |  |  | yes |  | Customer Addresses |  |
| `quick_edit_mode` | Selection |  |  | no |  | Quick encoding | related `company_id.quick_edit_mode` |
| `account_journal_early_pay_discount_loss_account_id` | Many2one | `account.account` |  | no |  | Cash Discount Loss | related `company_id.account_journal_early_pay_discount_loss_account_id` |
| `account_journal_early_pay_discount_gain_account_id` | Many2one | `account.account` |  | no |  | Cash Discount Gain | related `company_id.account_journal_early_pay_discount_gain_account_id` |
| `account_discount_income_allocation_id` | Many2one | `account.account` |  | no |  | Vendor Bills Discounts Account | related `company_id.account_discount_income_allocation_id` |
| `account_discount_expense_allocation_id` | Many2one | `account.account` |  | no |  | Customer Invoices Discounts Account | related `company_id.account_discount_expense_allocation_id` |
| `is_account_peppol_eligible` | Boolean |  |  | no |  | PEPPOL eligible | compute `_compute_is_account_peppol_eligible` |

## `res.currency` (extension)

Adds fields to `res.currency`, defined in another module. Every field below is added by this module.
Source: `res_currency.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `display_rounding_warning` | Boolean |  |  | no |  | Display Rounding Warning | compute `_compute_display_rounding_warning` |
| `fiscal_country_codes` | Char |  |  | no |  |  | compute `_compute_fiscal_country_codes` |

## `res.groups` (extension)

Adds fields to `res.groups`, defined in another module. Every field below is added by this module.
Source: `res_users.py`.

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `fiscal_country_codes` | Char |  |  | no |  |  | compute `_compute_fiscal_country_codes` |
| `name` | Char |  |  | yes |  |  |  |
| `credit` | Monetary |  |  | no |  | Total Receivable | compute `_credit_debit_get` |
| `credit_to_invoice` | Monetary |  |  | no |  |  | compute `_compute_credit_to_invoice` |
| `credit_limit` | Float |  |  | no (per company, ir.property) |  | Credit Limit |  |
| `use_partner_credit_limit` | Boolean |  |  | no |  | Partner Limit | compute `_compute_use_partner_credit_limit` |
| `show_credit_limit` | Boolean |  |  | no | default: (computed) |  | compute `_compute_show_credit_limit` |
| `days_sales_outstanding` | Float |  |  | no |  | Days Sales Outstanding (DSO) | compute `_compute_days_sales_outstanding` |
| `debit` | Monetary |  |  | no |  | Total Payable | compute `_credit_debit_get` |
| `debit_limit` | Monetary |  |  | yes |  | Payable Limit |  |
| `total_invoiced` | Monetary |  |  | no |  | Total Invoiced | compute `_invoice_total` |
| `currency_id` | Many2one | `res.currency` |  | no |  | Currency | compute `_get_company_currency` |
| `journal_item_count` | Integer |  |  | no |  | Journal Items | compute `_compute_journal_item_count` |
| `property_account_payable_id` | Many2one | `account.account` | yes | no (per company, ir.property) |  | Account Payable |  |
| `property_account_receivable_id` | Many2one | `account.account` | yes | no (per company, ir.property) |  | Account Receivable |  |
| `property_account_position_id` | Many2one | `account.fiscal.position` |  | no (per company, ir.property) |  | Fiscal Position |  |
| `property_payment_term_id` | Many2one | `account.payment.term` |  | no (per company, ir.property) |  | Customer Payment Terms |  |
| `property_supplier_payment_term_id` | Many2one | `account.payment.term` |  | no (per company, ir.property) |  | Vendor Payment Terms |  |
| `ref_company_ids` | One2many | `res.company` (inverse `partner_id`) |  | no (inverse) |  | Companies that refers to partner |  |
| `supplier_invoice_count` | Integer |  |  | no |  | # Vendor Bills | compute `_compute_supplier_invoice_count` |
| `has_unreconciled_entries` | Boolean |  |  | no |  |  | compute `_compute_has_unreconciled_entries` |
| `last_time_entries_checked` | Datetime |  |  | yes |  | Latest Invoices & Payments Matching Date |  |
| `invoice_ids` | One2many | `account.move` (inverse `partner_id`) |  | no (inverse) |  | Invoices |  |
| `contract_ids` | One2many | `account.analytic.account` (inverse `partner_id`) |  | no (inverse) |  | Partner Contracts |  |
| `bank_account_count` | Integer |  |  | no |  | Bank | compute `_compute_bank_count` |
| `trust` | Selection |  |  | no (per company, ir.property) | `good` Good Debtor, `normal` Normal Debtor, `bad` Bad Debtor; default: `'normal'` | Degree of trust you have in this debtor |  |
| `invoice_warn` | Selection |  |  | yes | `no-message` No Message, `warning` Warning, `block` Blocking Message; default: `'no-message'` | Invoice |  |
| `invoice_warn_msg` | Text |  |  | yes |  | Message for Invoice |  |
| `supplier_rank` | Integer |  |  | yes | default: `0` |  |  |
| `customer_rank` | Integer |  |  | yes | default: `0` |  |  |
| `duplicated_bank_account_partners_count` | Integer |  |  | no |  |  | compute `_compute_duplicated_bank_account_partners_count` |
| `is_coa_installed` | Boolean |  |  | no | default: (computed) |  |  |

## `res.partner.bank` (extension)

Adds fields to `res.partner.bank`, defined in another module. Every field below is added by this module.
Inherits: `mail.thread`, `mail.activity.mixin`.
Source: `res_partner_bank.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `journal_id` | One2many | `account.journal` (inverse `bank_account_id`) |  | no (inverse) |  | Account Journal |  |
| `has_iban_warning` | Boolean |  |  | yes |  |  | compute `_compute_display_account_warning` |
| `partner_country_name` | Char |  |  | no |  |  | related `partner_id.country_id.name` |
| `has_money_transfer_warning` | Boolean |  |  | yes |  |  | compute `_compute_display_account_warning` |
| `money_transfer_service` | Char |  |  | no |  |  | compute `_compute_money_transfer_service_name` |
| `partner_supplier_rank` | Integer |  |  | no |  |  | related `partner_id.supplier_rank` |
| `partner_customer_rank` | Integer |  |  | no |  |  | related `partner_id.customer_rank` |
| `related_moves` | One2many | `account.move` (inverse `partner_bank_id`) |  | no (inverse) |  |  |  |
| `bank_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `active` | Boolean |  |  | yes |  |  |  |
| `acc_number` | Char |  |  | yes |  |  |  |
| `acc_holder_name` | Char |  |  | yes |  |  |  |
| `partner_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `user_has_group_validate_bank_account` | Boolean |  |  | no |  |  | compute `_compute_user_has_group_validate_bank_account` |
| `allow_out_payment` | Boolean |  |  | yes |  |  |  |
| `currency_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `lock_trust_fields` | Boolean |  |  | no |  |  | compute `_compute_lock_trust_fields` |

## `sequence.mixin`

Abstract model (mixin), no table of its own.
Description: Automatic sequence.
Source: `sequence_mixin.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sequence_prefix` | Char |  |  | yes |  |  | compute `_compute_split_sequence` |
| `sequence_number` | Integer |  |  | yes |  |  | compute `_compute_split_sequence` |

## `uom.uom` (extension)

Adds fields to `uom.uom`, defined in another module. Every field below is added by this module.
Source: `uom_uom.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `fiscal_country_codes` | Char |  |  | no |  |  | compute `_compute_fiscal_country_codes` |
