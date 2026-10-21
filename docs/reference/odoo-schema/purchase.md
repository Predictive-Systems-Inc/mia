# Odoo 17.0 module `purchase`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 2. Models extended here: 12.

## `account.analytic.account` (extension)

Adds fields to `account.analytic.account`, defined in another module. Every field below is added by this module.
Source: `analytic_account.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `purchase_order_count` | Integer |  |  | no |  | Purchase Order Count | compute `_compute_purchase_order_count` |

## `account.analytic.applicability` (extension)

Adds fields to `account.analytic.applicability`, defined in another module. Every field below is added by this module.
Description: Analytic Plan's Applicabilities.
Source: `analytic_applicability.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `business_domain` | Selection |  |  | yes | added: `purchase_order` Purchase Order |  |  |

## `account.move` (extension)

Adds fields to `account.move`, defined in another module. Every field below is added by this module.
Source: `account_invoice.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `purchase_vendor_bill_id` | Many2one | `purchase.bill.union` |  | no |  | Auto-complete |  |
| `purchase_id` | Many2one | `purchase.order` |  | no |  | Purchase Order |  |
| `purchase_order_count` | Integer |  |  | no |  | Purchase Order Count | compute `_compute_origin_po_count` |

## `account.move.line` (extension)

Adds fields to `account.move.line`, defined in another module. Every field below is added by this module.
Source: `account_invoice.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `purchase_line_id` | Many2one | `purchase.order.line` |  | yes |  | Purchase Order Line |  |
| `purchase_order_id` | Many2one | `purchase.order` |  | no |  | Purchase Order | related `purchase_line_id.order_id` |

## `account.tax` (extension)

Adds fields to `account.tax`, defined in another module. Every field below is added by this module.
Source: `account_tax.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `purchase_order_line_ids` | Many2many | `purchase.order.line` (table `account_tax_purchase_order_line_rel`) |  | yes |  |  |  |

## `product.packaging` (extension)

Adds fields to `product.packaging`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `purchase` | Boolean |  |  | yes | default: `True` | Purchase |  |

## `product.product` (extension)

Adds fields to `product.product`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `purchased_product_qty` | Float |  |  | no |  | Purchased | compute `_compute_purchased_product_qty` |

## `product.supplierinfo` (extension)

Adds fields to `product.supplierinfo`, defined in another module. Every field below is added by this module.
Source: `product.py`.

## `product.template` (extension)

Adds fields to `product.template`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `purchased_product_qty` | Float |  |  | no |  | Purchased | compute `_compute_purchased_product_qty` |
| `purchase_method` | Selection |  |  | yes | `purchase` On ordered quantities, `receive` On received quantities; default: `'receive'` | Control Policy | compute `_compute_purchase_method` |
| `purchase_line_warn` | Selection |  | yes | yes | `no-message` No Message, `warning` Warning, `block` Blocking Message; default: `'no-message'` | Purchase Order Line Warning |  |
| `purchase_line_warn_msg` | Text |  |  | yes |  | Message for Purchase Order Line |  |

## `purchase.order`

Table `purchase_order`.
Description: Purchase Order.
Inherits: `portal.mixin`, `product.catalog.mixin`, `mail.thread`, `mail.activity.mixin`.
Order: `priority desc, id desc`.
Source: `purchase_order.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: `'New'` | Order Reference |  |
| `priority` | Selection |  |  | yes | `0` Normal, `1` Urgent; default: `'0'` | Priority |  |
| `origin` | Char |  |  | yes |  | Source Document |  |
| `partner_ref` | Char |  |  | yes |  | Vendor Reference |  |
| `date_order` | Datetime |  | yes | yes | default: (computed) | Order Deadline |  |
| `date_approve` | Datetime |  |  | yes |  | Confirmation Date |  |
| `partner_id` | Many2one | `res.partner` | yes | yes |  | Vendor |  |
| `dest_address_id` | Many2one | `res.partner` |  | yes |  | Dropship Address |  |
| `currency_id` | Many2one | `res.currency` | yes | yes | default: (computed) | Currency |  |
| `state` | Selection |  |  | yes | `draft` RFQ, `sent` RFQ Sent, `to approve` To Approve, `purchase` Purchase Order, `done` Locked, `cancel` Cancelled; default: `'draft'` | Status |  |
| `order_line` | One2many | `purchase.order.line` (inverse `order_id`) |  | no (inverse) |  | Order Lines |  |
| `notes` | Html |  |  | yes |  | Terms and Conditions |  |
| `invoice_count` | Integer |  |  | yes | default: `0` | Bill Count | compute `_compute_invoice` |
| `invoice_ids` | Many2many | `account.move` |  | yes |  | Bills | compute `_compute_invoice` |
| `invoice_status` | Selection |  |  | yes | `no` Nothing to Bill, `to invoice` Waiting Bills, `invoiced` Fully Billed; default: `'no'` | Billing Status | compute `_get_invoiced` |
| `date_planned` | Datetime |  |  | yes |  | Expected Arrival | compute `_compute_date_planned` |
| `date_calendar_start` | Datetime |  |  | yes |  |  | compute `_compute_date_calendar_start` |
| `amount_untaxed` | Monetary |  |  | yes |  | Untaxed Amount | compute `_amount_all` |
| `tax_totals` | Binary |  |  | no |  |  | compute `_compute_tax_totals` |
| `amount_tax` | Monetary |  |  | yes |  | Taxes | compute `_amount_all` |
| `amount_total` | Monetary |  |  | yes |  | Total | compute `_amount_all` |
| `fiscal_position_id` | Many2one | `account.fiscal.position` |  | yes |  | Fiscal Position |  |
| `tax_country_id` | Many2one | `res.country` |  | no |  |  | compute `_compute_tax_country_id` |
| `tax_calculation_rounding_method` | Selection |  |  | no |  | Tax calculation rounding method | related `company_id.tax_calculation_rounding_method` |
| `payment_term_id` | Many2one | `account.payment.term` |  | yes |  | Payment Terms |  |
| `incoterm_id` | Many2one | `account.incoterms` |  | yes |  | Incoterm |  |
| `product_id` | Many2one | `product.product` |  | no |  | Product | related `order_line.product_id` |
| `user_id` | Many2one | `res.users` |  | yes | default: (computed) | Buyer |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `country_code` | Char |  |  | no |  | Country code | related `company_id.account_fiscal_country_id.code` |
| `currency_rate` | Float |  |  | yes |  | Currency Rate | compute `_compute_currency_rate` |
| `mail_reminder_confirmed` | Boolean |  |  | yes | default: `False` | Reminder Confirmed |  |
| `mail_reception_confirmed` | Boolean |  |  | yes | default: `False` | Reception Confirmed |  |
| `receipt_reminder_email` | Boolean |  |  | no |  | Receipt Reminder Email | compute `_compute_receipt_reminder_email` |
| `reminder_date_before_receipt` | Integer |  |  | no |  | Days Before Receipt | compute `_compute_receipt_reminder_email` |

## `purchase.order.line`

Table `purchase_order_line`.
Description: Purchase Order Line.
Inherits: `analytic.mixin`.
Order: `order_id, sequence, id`.
Source: `purchase_order_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Text |  | yes | yes |  | Description | compute `_compute_price_unit_and_date_planned_and_name` |
| `sequence` | Integer |  |  | yes | default: `10` | Sequence |  |
| `product_qty` | Float |  | yes | yes |  | Quantity | compute `_compute_product_qty` |
| `product_uom_qty` | Float |  |  | yes |  | Total Quantity | compute `_compute_product_uom_qty` |
| `date_planned` | Datetime |  |  | yes |  | Expected Arrival | compute `_compute_price_unit_and_date_planned_and_name` |
| `discount` | Float |  |  | yes |  | Discount (%) | compute `_compute_price_unit_and_date_planned_and_name` |
| `taxes_id` | Many2many | `account.tax` (table `account_tax_purchase_order_line_rel`) |  | yes |  | Taxes |  |
| `product_uom` | Many2one | `uom.uom` |  | yes |  | Unit of Measure |  |
| `product_uom_category_id` | Many2one | (from related) |  | no |  |  | related `product_id.uom_id.category_id` |
| `product_id` | Many2one | `product.product` |  | yes |  | Product |  |
| `product_type` | Selection |  |  | no |  |  | related `product_id.detailed_type` |
| `price_unit` | Float |  | yes | yes |  | Unit Price | compute `_compute_price_unit_and_date_planned_and_name` |
| `price_unit_discounted` | Float |  |  | no |  | Unit Price (Discounted) | compute `_compute_price_unit_discounted` |
| `price_subtotal` | Monetary |  |  | yes |  | Subtotal | compute `_compute_amount` |
| `price_total` | Monetary |  |  | yes |  | Total | compute `_compute_amount` |
| `price_tax` | Float |  |  | yes |  | Tax | compute `_compute_amount` |
| `order_id` | Many2one | `purchase.order` | yes | yes |  | Order Reference |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | related `order_id.company_id` |
| `state` | Selection |  |  | yes |  |  | related `order_id.state` |
| `invoice_lines` | One2many | `account.move.line` (inverse `purchase_line_id`) |  | no (inverse) |  | Bill Lines |  |
| `qty_invoiced` | Float |  |  | yes |  | Billed Qty | compute `_compute_qty_invoiced` |
| `qty_received_method` | Selection |  |  | yes | `manual` Manual | Received Qty Method | compute `_compute_qty_received_method` |
| `qty_received` | Float |  |  | yes |  | Received Qty | compute `_compute_qty_received` |
| `qty_received_manual` | Float |  |  | yes |  | Manual Received Qty |  |
| `qty_to_invoice` | Float |  |  | yes |  | To Invoice Quantity | compute `_compute_qty_invoiced` |
| `partner_id` | Many2one | `res.partner` |  | yes |  | Partner | related `order_id.partner_id` |
| `currency_id` | Many2one | (from related) |  | yes |  | Currency | related `order_id.currency_id` |
| `date_order` | Datetime |  |  | no |  | Order Date | related `order_id.date_order` |
| `date_approve` | Datetime |  |  | no |  | Confirmation Date | related `order_id.date_approve` |
| `product_packaging_id` | Many2one | `product.packaging` |  | yes |  | Packaging | compute `_compute_product_packaging_id` |
| `product_packaging_qty` | Float |  |  | yes |  | Packaging Quantity | compute `_compute_product_packaging_qty` |
| `tax_calculation_rounding_method` | Selection |  |  | no |  | Tax calculation rounding method | related `company_id.tax_calculation_rounding_method` |
| `display_type` | Selection |  |  | yes | `line_section` Section, `line_note` Note; default: `False` |  |  |

SQL constraints:

- `accountable_required_fields`: `CHECK(display_type IS NOT NULL OR (product_id IS NOT NULL AND product_uom IS NOT NULL AND date_planned IS NOT NULL))`
- `non_accountable_null_fields`: `CHECK(display_type IS NULL OR (product_id IS NULL AND price_unit = 0 AND product_uom_qty = 0 AND product_uom IS NULL AND date_planned is NULL))`

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Source: `res_company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `po_lead` | Float |  | yes | yes | default: `0.0` | Purchase Lead Time |  |
| `po_lock` | Selection |  |  | yes | `edit` Allow to edit purchase orders, `lock` Confirmed purchase orders are not editable; default: `'edit'` | Purchase Order Modification |  |
| `po_double_validation` | Selection |  |  | yes | `one_step` Confirm purchase orders in one step, `two_step` Get 2 levels of approvals to confirm a purchase order; default: `'one_step'` | Levels of Approvals |  |
| `po_double_validation_amount` | Monetary |  |  | yes | default: `5000` | Double validation amount |  |

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `lock_confirmed_po` | Boolean |  |  | yes | default: (computed) | Lock Confirmed Orders |  |
| `po_lock` | Selection |  |  | no |  | Purchase Order Modification * | related `company_id.po_lock` |
| `po_order_approval` | Boolean |  |  | yes | default: (computed) | Purchase Order Approval |  |
| `po_double_validation` | Selection |  |  | no |  | Levels of Approvals * | related `company_id.po_double_validation` |
| `po_double_validation_amount` | Monetary |  |  | no |  | Minimum Amount | related `company_id.po_double_validation_amount` |
| `company_currency_id` | Many2one | `res.currency` |  | no |  | Company Currency | related `company_id.currency_id` |
| `default_purchase_method` | Selection |  |  | yes | `purchase` Ordered quantities, `receive` Received quantities; default: `'receive'` | Bill Control |  |
| `group_warning_purchase` | Boolean |  |  | yes |  | Purchase Warnings |  |
| `module_account_3way_match` | Boolean |  |  | yes |  | 3-way matching: purchases, receptions and bills |  |
| `module_purchase_requisition` | Boolean |  |  | yes |  | Purchase Agreements |  |
| `module_purchase_product_matrix` | Boolean |  |  | yes |  | Purchase Grid Entry |  |
| `po_lead` | Float |  |  | no |  |  | related `company_id.po_lead` |
| `use_po_lead` | Boolean |  |  | yes |  | Security Lead Time for Purchase |  |
| `group_send_reminder` | Boolean |  |  | yes | default: `True` | Receipt Reminder |  |

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `property_purchase_currency_id` | Many2one | `res.currency` |  | no (per company, ir.property) |  | Supplier Currency |  |
| `purchase_order_count` | Integer |  |  | no |  | Purchase Order Count | compute `_compute_purchase_order_count` |
| `purchase_warn` | Selection |  |  | yes | `no-message` No Message, `warning` Warning, `block` Blocking Message; default: `'no-message'` | Purchase Order Warning |  |
| `purchase_warn_msg` | Text |  |  | yes |  | Message for Purchase Order |  |
| `receipt_reminder_email` | Boolean |  |  | no (per company, ir.property) | default: `False` | Receipt Reminder |  |
| `reminder_date_before_receipt` | Integer |  |  | no (per company, ir.property) | default: `1` | Days Before Receipt |  |
| `buyer_id` | Many2one | `res.users` |  | yes |  | Buyer |  |
