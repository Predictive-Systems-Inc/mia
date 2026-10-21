# Odoo 17.0 module `sale`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 2. Models extended here: 18.

## `account.analytic.applicability` (extension)

Adds fields to `account.analytic.applicability`, defined in another module. Every field below is added by this module.
Description: Analytic Plan's Applicabilities.
Source: `analytic.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `business_domain` | Selection |  |  | yes | added: `sale_order` Sale Order |  |  |

## `account.analytic.line` (extension)

Adds fields to `account.analytic.line`, defined in another module. Every field below is added by this module.
Source: `analytic.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `allowed_so_line_ids` | Many2many | `sale.order.line` |  | no |  |  | compute `_compute_allowed_so_line_ids` |
| `so_line` | Many2one | `sale.order.line` |  | yes |  | Sales Order Item |  |

## `account.move` (extension)

Adds fields to `account.move`, defined in another module. Every field below is added by this module.
Inherits: `utm.mixin`.
Source: `account_move.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `team_id` | Many2one | `crm.team` |  | yes |  | Sales Team | compute `_compute_team_id` |
| `campaign_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `medium_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `source_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `sale_order_count` | Integer |  |  | no |  | Sale Order Count | compute `_compute_origin_so_count` |

## `account.move.line` (extension)

Adds fields to `account.move.line`, defined in another module. Every field below is added by this module.
Source: `account_move_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `is_downpayment` | Boolean |  |  | yes |  |  |  |
| `sale_line_ids` | Many2many | `sale.order.line` (table `sale_order_line_invoice_rel`) |  | yes |  | Sales Order Lines |  |

## `crm.team` (extension)

Adds fields to `crm.team`, defined in another module. Every field below is added by this module.
Source: `crm_team.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `invoiced` | Float |  |  | no |  | Invoiced This Month | compute `_compute_invoiced` |
| `invoiced_target` | Float |  |  | yes |  | Invoicing Target |  |
| `quotations_count` | Integer |  |  | no |  | Number of quotations to invoice | compute `_compute_quotations_to_invoice` |
| `quotations_amount` | Float |  |  | no |  | Amount of quotations to invoice | compute `_compute_quotations_to_invoice` |
| `sales_to_invoice_count` | Integer |  |  | no |  | Number of sales to invoice | compute `_compute_sales_to_invoice` |
| `sale_order_count` | Integer |  |  | no |  | # Sale Orders | compute `_compute_sale_order_count` |

## `ir.config_parameter` (extension)

Adds fields to `ir.config_parameter`, defined in another module. Every field below is added by this module.
Source: `ir_config_parameter.py`.

## `onboarding.onboarding` (extension)

Adds fields to `onboarding.onboarding`, defined in another module. Every field below is added by this module.
Source: `onboarding_onboarding.py`.

## `onboarding.onboarding.step` (extension)

Adds fields to `onboarding.onboarding.step`, defined in another module. Every field below is added by this module.
Source: `onboarding_onboarding_step.py`.

## `payment.provider` (extension)

Adds fields to `payment.provider`, defined in another module. Every field below is added by this module.
Source: `payment_provider.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `so_reference_type` | Selection |  |  | yes | `so_name` Based on Document Reference, `partner` Based on Customer ID; default: `'so_name'` | Communication |  |

## `payment.transaction` (extension)

Adds fields to `payment.transaction`, defined in another module. Every field below is added by this module.
Source: `payment_transaction.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sale_order_ids` | Many2many | `sale.order` (table `sale_order_transaction_rel`) |  | yes |  | Sales Orders |  |
| `sale_order_ids_nbr` | Integer |  |  | no |  | # of Sales Orders | compute `_compute_sale_order_ids_nbr` |

## `product.attribute.custom.value` (extension)

Adds fields to `product.attribute.custom.value`, defined in another module. Every field below is added by this module.
Source: `product_product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sale_order_line_id` | Many2one | `sale.order.line` |  | yes |  | Sales Order Line |  |

SQL constraints:

- `sol_custom_value_unique`: `unique(custom_product_template_attribute_value_id, sale_order_line_id)`

## `product.document` (extension)

Adds fields to `product.document`, defined in another module. Every field below is added by this module.
Source: `product_document.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `attached_on` | Selection |  |  | yes | `quotation` Quotation, `sale_order` Confirmed order | Visible at |  |

## `product.packaging` (extension)

Adds fields to `product.packaging`, defined in another module. Every field below is added by this module.
Source: `product_product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sales` | Boolean |  |  | yes | default: `True` | Sales |  |

## `product.product` (extension)

Adds fields to `product.product`, defined in another module. Every field below is added by this module.
Source: `product_product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sales_count` | Float |  |  | no |  | Sold | compute `_compute_sales_count` |
| `product_catalog_product_is_in_sale_order` | Boolean |  |  | no |  |  | compute `_compute_product_is_in_sale_order` |

## `product.template` (extension)

Adds fields to `product.template`, defined in another module. Every field below is added by this module.
Source: `product_template.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `service_type` | Selection |  |  | yes | `manual` Manually set quantities on order | Track Service | compute `_compute_service_type` |
| `sale_line_warn` | Selection |  | yes | yes | `no-message` No Message, `warning` Warning, `block` Blocking Message; default: `'no-message'` | Sales Order Line |  |
| `sale_line_warn_msg` | Text |  |  | yes |  | Message for Sales Order Line |  |
| `expense_policy` | Selection |  |  | yes | `no` No, `cost` At cost, `sales_price` Sales price; default: `'no'` | Re-Invoice Expenses | compute `_compute_expense_policy` |
| `visible_expense_policy` | Boolean |  |  | no |  | Re-Invoice Policy visible | compute `_compute_visible_expense_policy` |
| `sales_count` | Float |  |  | no |  | Sold | compute `_compute_sales_count` |
| `invoice_policy` | Selection |  |  | yes | `order` Ordered quantities, `delivery` Delivered quantities | Invoicing Policy | compute `_compute_invoice_policy` |

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Source: `res_company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `portal_confirmation_sign` | Boolean |  |  | yes | default: `True` | Online Signature |  |
| `portal_confirmation_pay` | Boolean |  |  | yes |  | Online Payment |  |
| `prepayment_percent` | Float |  |  | yes | default: `1.0` | Prepayment percentage |  |
| `quotation_validity_days` | Integer |  |  | yes | default: `30` | Default Quotation Validity |  |
| `sale_discount_product_id` | Many2one | `product.product` |  | yes |  | Discount Product |  |
| `sale_down_payment_product_id` | Many2one | `product.product` |  | yes |  | Deposit Product |  |
| `sale_onboarding_payment_method` | Selection |  |  | yes | `digital_signature` Sign online, `paypal` PayPal, `stripe` Stripe, `other` Pay with another payment provider, `manual` Manual Payment | Sale onboarding selected payment method |  |

SQL constraints:

- `check_quotation_validity_days`: `CHECK(quotation_validity_days >= 0)`

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sale_order_count` | Integer |  |  | no |  | Sale Order Count | compute `_compute_sale_order_count` |
| `sale_order_ids` | One2many | `sale.order` (inverse `partner_id`) |  | no (inverse) |  | Sales Order |  |
| `sale_warn` | Selection |  |  | yes | `no-message` No Message, `warning` Warning, `block` Blocking Message; default: `'no-message'` | Sales Warnings |  |
| `sale_warn_msg` | Text |  |  | yes |  | Message for Sales Order |  |

## `sale.order`

Table `sale_order`.
Description: Sales Order.
Inherits: `portal.mixin`, `product.catalog.mixin`, `mail.thread`, `mail.activity.mixin`, `utm.mixin`.
Order: `date_order desc, id desc`.
Source: `sale_order.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: (computed) | Order Reference |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) |  |  |
| `partner_id` | Many2one | `res.partner` | yes | yes |  | Customer |  |
| `state` | Selection |  |  | yes | `draft` Quotation, `sent` Quotation Sent, `sale` Sales Order, `cancel` Cancelled; default: `'draft'` | Status |  |
| `locked` | Boolean |  |  | yes | default: `False` |  |  |
| `client_order_ref` | Char |  |  | yes |  | Customer Reference |  |
| `create_date` | Datetime |  |  | yes |  | Creation Date |  |
| `commitment_date` | Datetime |  |  | yes |  | Delivery Date |  |
| `date_order` | Datetime |  | yes | yes | default: (computed) | Order Date |  |
| `origin` | Char |  |  | yes |  | Source Document |  |
| `reference` | Char |  |  | yes |  | Payment Ref. |  |
| `require_signature` | Boolean |  |  | yes |  | Online signature | compute `_compute_require_signature` |
| `require_payment` | Boolean |  |  | yes |  | Online payment | compute `_compute_require_payment` |
| `prepayment_percent` | Float |  |  | yes |  | Prepayment percentage | compute `_compute_prepayment_percent` |
| `signature` | Image |  |  | yes |  | Signature |  |
| `signed_by` | Char |  |  | yes |  | Signed By |  |
| `signed_on` | Datetime |  |  | yes |  | Signed On |  |
| `validity_date` | Date |  |  | yes |  | Expiration | compute `_compute_validity_date` |
| `journal_id` | Many2one | `account.journal` |  | yes |  | Invoicing Journal | compute `_compute_journal_id` |
| `note` | Html |  |  | yes |  | Terms and conditions | compute `_compute_note` |
| `partner_invoice_id` | Many2one | `res.partner` | yes | yes |  | Invoice Address | compute `_compute_partner_invoice_id` |
| `partner_shipping_id` | Many2one | `res.partner` | yes | yes |  | Delivery Address | compute `_compute_partner_shipping_id` |
| `fiscal_position_id` | Many2one | `account.fiscal.position` |  | yes |  | Fiscal Position | compute `_compute_fiscal_position_id` |
| `payment_term_id` | Many2one | `account.payment.term` |  | yes |  | Payment Terms | compute `_compute_payment_term_id` |
| `pricelist_id` | Many2one | `product.pricelist` |  | yes |  | Pricelist | compute `_compute_pricelist_id` |
| `currency_id` | Many2one | `res.currency` |  | yes |  |  | compute `_compute_currency_id` |
| `currency_rate` | Float |  |  | yes |  | Currency Rate | compute `_compute_currency_rate` |
| `user_id` | Many2one | `res.users` |  | yes |  | Salesperson | compute `_compute_user_id` |
| `team_id` | Many2one | `crm.team` |  | yes |  | Sales Team | compute `_compute_team_id` |
| `order_line` | One2many | `sale.order.line` (inverse `order_id`) |  | no (inverse) |  | Order Lines |  |
| `amount_untaxed` | Monetary |  |  | yes |  | Untaxed Amount | compute `_compute_amounts` |
| `amount_tax` | Monetary |  |  | yes |  | Taxes | compute `_compute_amounts` |
| `amount_total` | Monetary |  |  | yes |  | Total | compute `_compute_amounts` |
| `amount_to_invoice` | Monetary |  |  | yes |  | Amount to invoice | compute `_compute_amount_to_invoice` |
| `amount_invoiced` | Monetary |  |  | no |  | Already invoiced | compute `_compute_amount_invoiced` |
| `invoice_count` | Integer |  |  | no |  | Invoice Count | compute `_get_invoiced` |
| `invoice_ids` | Many2many | `account.move` |  | no |  | Invoices | compute `_get_invoiced` |
| `invoice_status` | Selection |  |  | yes | `upselling` Upselling Opportunity, `invoiced` Fully Invoiced, `to invoice` To Invoice, `no` Nothing to Invoice | Invoice Status | compute `_compute_invoice_status` |
| `transaction_ids` | Many2many | `payment.transaction` (table `sale_order_transaction_rel`) |  | yes |  | Transactions |  |
| `authorized_transaction_ids` | Many2many | `payment.transaction` |  | no |  | Authorized Transactions | compute `_compute_authorized_transaction_ids` |
| `amount_paid` | Float |  |  | no |  |  | compute `_compute_amount_paid` |
| `campaign_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `medium_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `source_id` | Many2one | (redefines inherited field) |  | yes |  |  |  |
| `analytic_account_id` | Many2one | `account.analytic.account` |  | yes |  | Analytic Account |  |
| `tag_ids` | Many2many | `crm.tag` (table `sale_order_tag_rel`) |  | yes |  | Tags |  |
| `amount_undiscounted` | Float |  |  | no |  | Amount Before Discount | compute `_compute_amount_undiscounted` |
| `country_code` | Char |  |  | no |  | Country code | related `company_id.account_fiscal_country_id.code` |
| `expected_date` | Datetime |  |  | no |  | Expected Date | compute `_compute_expected_date` |
| `is_expired` | Boolean |  |  | no |  | Is Expired | compute `_compute_is_expired` |
| `partner_credit_warning` | Text |  |  | no |  |  | compute `_compute_partner_credit_warning` |
| `tax_calculation_rounding_method` | Selection |  |  | no |  |  | related `company_id.tax_calculation_rounding_method` |
| `tax_country_id` | Many2one | `res.country` |  | no |  |  | compute `_compute_tax_country_id` |
| `tax_totals` | Binary |  |  | no |  |  | compute `_compute_tax_totals` |
| `terms_type` | Selection |  |  | no |  |  | related `company_id.terms_type` |
| `type_name` | Char |  |  | no |  | Type Name | compute `_compute_type_name` |
| `show_update_fpos` | Boolean |  |  | no |  | Has Fiscal Position Changed |  |
| `has_active_pricelist` | Boolean |  |  | no |  |  | compute `_compute_has_active_pricelist` |
| `show_update_pricelist` | Boolean |  |  | no |  | Has Pricelist Changed |  |

SQL constraints:

- `date_order_conditional_required`: `CHECK((state = 'sale' AND date_order IS NOT NULL) OR state != 'sale')`

## `sale.order.line`

Table `sale_order_line`.
Description: Sales Order Line.
Inherits: `analytic.mixin`.
Order: `order_id, sequence, id`.
Source: `sale_order_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `order_id` | Many2one | `sale.order` | yes | yes |  | Order Reference |  |
| `sequence` | Integer |  |  | yes | default: `10` | Sequence |  |
| `company_id` | Many2one | (from related) |  | yes |  |  | related `order_id.company_id` |
| `currency_id` | Many2one | (from related) |  | yes |  |  | related `order_id.currency_id` |
| `order_partner_id` | Many2one | (from related) |  | yes |  | Customer | related `order_id.partner_id` |
| `salesman_id` | Many2one | (from related) |  | yes |  | Salesperson | related `order_id.user_id` |
| `state` | Selection |  |  | yes |  | Order Status | related `order_id.state` |
| `tax_country_id` | Many2one | (from related) |  | no |  |  | related `order_id.tax_country_id` |
| `display_type` | Selection |  |  | yes | `line_section` Section, `line_note` Note; default: `False` |  |  |
| `is_downpayment` | Boolean |  |  | yes |  | Is a down payment |  |
| `is_expense` | Boolean |  |  | yes |  | Is expense |  |
| `product_id` | Many2one | `product.product` |  | yes |  | Product |  |
| `product_template_id` | Many2one | `product.template` |  | no |  | Product Template | compute `_compute_product_template_id` |
| `product_uom_category_id` | Many2one | (from related) |  | no |  |  | related `product_id.uom_id.category_id` |
| `product_custom_attribute_value_ids` | One2many | `product.attribute.custom.value` (inverse `sale_order_line_id`) |  | yes |  | Custom Values | compute `_compute_custom_attribute_values` |
| `product_no_variant_attribute_value_ids` | Many2many | `product.template.attribute.value` |  | yes |  | Extra Values | compute `_compute_no_variant_attribute_values` |
| `name` | Text |  | yes | yes |  | Description | compute `_compute_name` |
| `product_uom_qty` | Float |  | yes | yes | default: `1.0` | Quantity | compute `_compute_product_uom_qty` |
| `product_uom` | Many2one | `uom.uom` |  | yes |  | Unit of Measure | compute `_compute_product_uom` |
| `tax_id` | Many2many | `account.tax` |  | yes |  | Taxes | compute `_compute_tax_id` |
| `pricelist_item_id` | Many2one | `product.pricelist.item` |  | no |  |  | compute `_compute_pricelist_item_id` |
| `price_unit` | Float |  | yes | yes |  | Unit Price | compute `_compute_price_unit` |
| `discount` | Float |  |  | yes |  | Discount (%) | compute `_compute_discount` |
| `price_subtotal` | Monetary |  |  | yes |  | Subtotal | compute `_compute_amount` |
| `price_tax` | Float |  |  | yes |  | Total Tax | compute `_compute_amount` |
| `price_total` | Monetary |  |  | yes |  | Total | compute `_compute_amount` |
| `price_reduce_taxexcl` | Monetary |  |  | yes |  | Price Reduce Tax excl | compute `_compute_price_reduce_taxexcl` |
| `price_reduce_taxinc` | Monetary |  |  | yes |  | Price Reduce Tax incl | compute `_compute_price_reduce_taxinc` |
| `product_packaging_id` | Many2one | `product.packaging` |  | yes |  | Packaging | compute `_compute_product_packaging_id` |
| `product_packaging_qty` | Float |  |  | yes |  | Packaging Quantity | compute `_compute_product_packaging_qty` |
| `customer_lead` | Float |  | yes | yes |  | Lead Time | compute `_compute_customer_lead` |
| `qty_delivered_method` | Selection |  |  | yes | `manual` Manual, `analytic` Analytic From Expenses | Method to update delivered qty | compute `_compute_qty_delivered_method` |
| `qty_delivered` | Float |  |  | yes | default: `0.0` | Delivery Quantity | compute `_compute_qty_delivered` |
| `qty_invoiced` | Float |  |  | yes |  | Invoiced Quantity | compute `_compute_qty_invoiced` |
| `qty_to_invoice` | Float |  |  | yes |  | Quantity To Invoice | compute `_compute_qty_to_invoice` |
| `analytic_line_ids` | One2many | `account.analytic.line` (inverse `so_line`) |  | no (inverse) |  | Analytic lines |  |
| `invoice_lines` | Many2many | `account.move.line` (table `sale_order_line_invoice_rel`) |  | yes |  | Invoice Lines |  |
| `invoice_status` | Selection |  |  | yes | `upselling` Upselling Opportunity, `invoiced` Fully Invoiced, `to invoice` To Invoice, `no` Nothing to Invoice | Invoice Status | compute `_compute_invoice_status` |
| `untaxed_amount_invoiced` | Monetary |  |  | yes |  | Untaxed Invoiced Amount | compute `_compute_untaxed_amount_invoiced` |
| `untaxed_amount_to_invoice` | Monetary |  |  | yes |  | Untaxed Amount To Invoice | compute `_compute_untaxed_amount_to_invoice` |
| `product_type` | Selection |  |  | no |  |  | related `product_id.detailed_type` |
| `product_updatable` | Boolean |  |  | no |  | Can Edit Product | compute `_compute_product_updatable` |
| `product_uom_readonly` | Boolean |  |  | no |  |  | compute `_compute_product_uom_readonly` |
| `tax_calculation_rounding_method` | Selection |  |  | no |  | Tax calculation rounding method | related `company_id.tax_calculation_rounding_method` |

SQL constraints:

- `accountable_required_fields`: `CHECK(display_type IS NOT NULL OR (product_id IS NOT NULL AND product_uom IS NOT NULL))`
- `non_accountable_null_fields`: `CHECK(display_type IS NULL OR (product_id IS NULL AND price_unit = 0 AND product_uom_qty = 0 AND product_uom IS NULL AND customer_lead = 0))`

## `utm.campaign` (extension)

Adds fields to `utm.campaign`, defined in another module. Every field below is added by this module.
Description: UTM Campaign.
Source: `utm_campaign.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `quotation_count` | Integer |  |  | no |  | Quotation Count | compute `_compute_quotation_count` |
| `invoiced_amount` | Integer |  |  | no |  | Revenues generated by the campaign | compute `_compute_sale_invoiced_amount` |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `currency_id` | Many2one | `res.currency` |  | no |  | Currency | related `company_id.currency_id` |
