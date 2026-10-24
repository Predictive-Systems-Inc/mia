# Odoo 17.0 module `point_of_sale`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 13. Models extended here: 25.

## `account.bank.statement.line` (extension)

Adds fields to `account.bank.statement.line`, defined in another module. Every field below is added by this module.
Source: `account_bank_statement.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_session_id` | Many2one | `pos.session` |  | yes |  | Session |  |

## `account.cash.rounding` (extension)

Adds fields to `account.cash.rounding`, defined in another module. Every field below is added by this module.
Source: `account_cash_rounding.py`, `pos_order.py`.

## `account.chart.template` (extension)

Adds fields to `account.chart.template`, defined in another module. Every field below is added by this module.
Source: `chart_template.py`.

## `account.fiscal.position` (extension)

Adds fields to `account.fiscal.position`, defined in another module. Every field below is added by this module.
Source: `account_fiscal_position.py`.

## `account.journal` (extension)

Adds fields to `account.journal`, defined in another module. Every field below is added by this module.
Source: `account_journal.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_payment_method_ids` | One2many | `pos.payment.method` (inverse `journal_id`) |  | no (inverse) |  | Point of Sale Payment Methods |  |

## `account.move` (extension)

Adds fields to `account.move`, defined in another module. Every field below is added by this module.
Source: `account_move.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_order_ids` | One2many | `pos.order` (inverse `account_move`) |  | no (inverse) |  |  |  |
| `pos_payment_ids` | One2many | `pos.payment` (inverse `account_move_id`) |  | no (inverse) |  |  |  |
| `pos_refunded_invoice_ids` | Many2many | `account.move` (table `refunded_invoices`) |  | yes |  |  |  |

## `account.move.line` (extension)

Adds fields to `account.move.line`, defined in another module. Every field below is added by this module.
Source: `account_move.py`.

## `account.payment` (extension)

Adds fields to `account.payment`, defined in another module. Every field below is added by this module.
Source: `account_payment.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_payment_method_id` | Many2one | `pos.payment.method` |  | yes |  | POS Payment Method |  |
| `force_outstanding_account_id` | Many2one | `account.account` |  | yes |  | Forced Outstanding Account |  |
| `pos_session_id` | Many2one | `pos.session` |  | yes |  | POS Session |  |

## `account.tax` (extension)

Adds fields to `account.tax`, defined in another module. Every field below is added by this module.
Source: `account_tax.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_order_line_ids` | Many2many | `pos.order.line` (table `account_tax_pos_order_line_rel`) |  | yes |  |  |  |

## `barcode.rule` (extension)

Adds fields to `barcode.rule`, defined in another module. Every field below is added by this module.
Source: `barcode_rule.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `type` | Selection |  |  | yes | added: `weight` Weighted Product, `price` Priced Product, `discount` Discounted Product, `client` Client, `cashier` Cashier |  |  |

## `digest.digest` (extension)

Adds fields to `digest.digest`, defined in another module. Every field below is added by this module.
Source: `digest.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `kpi_pos_total` | Boolean |  |  | yes |  | POS Sales |  |
| `kpi_pos_total_value` | Monetary |  |  | no |  |  | compute `_compute_kpi_pos_total_value` |

## `pos.bill`

Table `pos_bill`.
Description: Coins/Bills.
Order: `value`.
Source: `pos_bill.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  | Name |  |
| `value` | Float |  | yes | yes |  | Coin/Bill Value |  |
| `pos_config_ids` | Many2many | `pos.config` |  | yes |  | Point of Sales |  |

## `pos.category`

Table `pos_category`.
Description: Point of Sale Category.
Order: `sequence, name`.
Source: `pos_category.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Category Name |  |
| `parent_id` | Many2one | `pos.category` |  | yes |  | Parent Category |  |
| `child_id` | One2many | `pos.category` (inverse `parent_id`) |  | no (inverse) |  | Children Categories |  |
| `sequence` | Integer |  |  | yes |  |  |  |
| `image_128` | Image |  |  | yes |  | Image |  |
| `has_image` | Boolean |  |  | no |  |  | compute `_compute_has_image` |

## `pos.combo`

Table `pos_combo`.
Description: Product combo choices.
Order: `sequence, id`.
Source: `pos_combo.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `combo_line_ids` | One2many | `pos.combo.line` (inverse `combo_id`) |  | no (inverse) |  | Products in Combo |  |
| `num_of_products` | Integer |  |  | no |  | No of Products | compute `_compute_num_of_products` |
| `sequence` | Integer |  |  | yes |  |  |  |
| `base_price` | Float |  |  | no |  | Product Price | compute `_compute_base_price` |

## `pos.combo.line`

Table `pos_combo_line`.
Description: Product Combo Items.
Source: `pos_combo_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `combo_price` | Float |  |  | yes | default: `0.0` | Price Extra |  |
| `lst_price` | Float |  |  | no |  | Original Price | related `product_id.lst_price` |
| `combo_id` | Many2one | `pos.combo` |  | yes |  |  |  |

## `pos.config`

Table `pos_config`.
Description: Point of Sale Configuration.
Source: `pos_config.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Point of Sale |  |
| `printer_ids` | Many2many | `pos.printer` (table `pos_config_printer_rel`) |  | yes |  | Order Printers |  |
| `is_order_printer` | Boolean |  |  | yes |  | Order Printer |  |
| `is_installed_account_accountant` | Boolean |  |  | no |  | Is the Full Accounting Installed | compute `_compute_is_installed_account_accountant` |
| `picking_type_id` | Many2one | `stock.picking.type` | yes | yes | default: (computed) | Operation Type |  |
| `journal_id` | Many2one | `account.journal` |  | yes | default: (computed) | Point of Sale Journal |  |
| `invoice_journal_id` | Many2one | `account.journal` |  | yes | default: (computed) | Invoice Journal |  |
| `currency_id` | Many2one | `res.currency` |  | no |  | Currency | compute `_compute_currency` |
| `iface_cashdrawer` | Boolean |  |  | yes |  | Cashdrawer |  |
| `iface_electronic_scale` | Boolean |  |  | yes |  | Electronic Scale |  |
| `iface_customer_facing_display` | Boolean |  |  | no |  |  | compute `_compute_customer_facing_display` |
| `iface_customer_facing_display_via_proxy` | Boolean |  |  | yes |  | Customer Facing Display |  |
| `iface_customer_facing_display_local` | Boolean |  |  | yes |  | Local Customer Facing Display |  |
| `iface_customer_facing_display_background_image_1920` | Image |  |  | yes |  | Background Image | compute `_compute_iface_customer_facing_display_background_image_1920` |
| `iface_print_via_proxy` | Boolean |  |  | yes |  | Print via Proxy |  |
| `iface_scan_via_proxy` | Boolean |  |  | yes |  | Scan via Proxy |  |
| `iface_big_scrollbars` | Boolean |  |  | yes |  | Large Scrollbars |  |
| `iface_print_auto` | Boolean |  |  | yes | default: `False` | Automatic Receipt Printing |  |
| `iface_print_skip_screen` | Boolean |  |  | yes | default: `True` | Skip Preview Screen |  |
| `iface_tax_included` | Selection |  | yes | yes | `subtotal` Tax-Excluded Price, `total` Tax-Included Price; default: `'total'` | Tax Display |  |
| `iface_start_categ_id` | Many2one | `pos.category` |  | yes |  | Initial Category |  |
| `iface_available_categ_ids` | Many2many | `pos.category` |  | yes |  | Available PoS Product Categories |  |
| `restrict_price_control` | Boolean |  |  | yes |  | Restrict Price Modifications to Managers |  |
| `is_margins_costs_accessible_to_every_user` | Boolean |  |  | yes | default: `False` | Margins & Costs |  |
| `cash_control` | Boolean |  |  | no |  | Advanced Cash Control | compute `_compute_cash_control` |
| `set_maximum_difference` | Boolean |  |  | yes |  | Set Maximum Difference |  |
| `receipt_header` | Text |  |  | yes |  | Receipt Header |  |
| `receipt_footer` | Text |  |  | yes |  | Receipt Footer |  |
| `proxy_ip` | Char |  |  | yes |  | IP Address |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `uuid` | Char |  |  | yes | default: (computed) |  |  |
| `sequence_id` | Many2one | `ir.sequence` |  | yes |  | Order IDs Sequence |  |
| `sequence_line_id` | Many2one | `ir.sequence` |  | yes |  | Order Line IDs Sequence |  |
| `session_ids` | One2many | `pos.session` (inverse `config_id`) |  | no (inverse) |  | Sessions |  |
| `current_session_id` | Many2one | `pos.session` |  | no |  | Current Session | compute `_compute_current_session` |
| `current_session_state` | Char |  |  | no |  |  | compute `_compute_current_session` |
| `number_of_rescue_session` | Integer |  |  | no |  | Number of Rescue Session | compute `_compute_current_session` |
| `last_session_closing_cash` | Float |  |  | no |  |  | compute `_compute_last_session` |
| `last_session_closing_date` | Date |  |  | no |  |  | compute `_compute_last_session` |
| `pos_session_username` | Char |  |  | no |  |  | compute `_compute_current_session_user` |
| `pos_session_state` | Char |  |  | no |  |  | compute `_compute_current_session_user` |
| `pos_session_duration` | Char |  |  | no |  |  | compute `_compute_current_session_user` |
| `pricelist_id` | Many2one | `product.pricelist` |  | yes |  | Default Pricelist |  |
| `available_pricelist_ids` | Many2many | `product.pricelist` |  | yes |  | Available Pricelists |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `group_pos_manager_id` | Many2one | `res.groups` |  | yes | default: (computed) | Point of Sale Manager Group |  |
| `group_pos_user_id` | Many2one | `res.groups` |  | yes | default: (computed) | Point of Sale User Group |  |
| `iface_tipproduct` | Boolean |  |  | yes |  | Product tips |  |
| `tip_product_id` | Many2one | `product.product` |  | yes | default: (computed) | Tip Product |  |
| `fiscal_position_ids` | Many2many | `account.fiscal.position` |  | yes |  | Fiscal Positions |  |
| `default_fiscal_position_id` | Many2one | `account.fiscal.position` |  | yes |  | Default Fiscal Position |  |
| `default_bill_ids` | Many2many | `pos.bill` |  | yes |  | Coins/Bills |  |
| `use_pricelist` | Boolean |  |  | yes |  | Use a pricelist. |  |
| `tax_regime_selection` | Boolean |  |  | yes |  | Tax Regime Selection value |  |
| `start_category` | Boolean |  |  | yes | default: `False` | Start Category |  |
| `limit_categories` | Boolean |  |  | yes |  | Restrict Categories |  |
| `module_pos_restaurant` | Boolean |  |  | yes |  | Is a Bar/Restaurant |  |
| `module_pos_discount` | Boolean |  |  | yes |  | Global Discounts |  |
| `module_pos_mercury` | Boolean |  |  | yes |  | Integrated Card Payments |  |
| `is_posbox` | Boolean |  |  | yes |  | PosBox |  |
| `is_header_or_footer` | Boolean |  |  | yes |  | Custom Header & Footer |  |
| `module_pos_hr` | Boolean |  |  | yes |  |  |  |
| `amount_authorized_diff` | Float |  |  | yes |  | Amount Authorized Difference |  |
| `payment_method_ids` | Many2many | `pos.payment.method` |  | yes | default: (computed) | Payment Methods |  |
| `company_has_template` | Boolean |  |  | no |  | Company has chart of accounts | compute `_compute_company_has_template` |
| `current_user_id` | Many2one | `res.users` |  | no |  | Current Session Responsible | compute `_compute_current_session_user` |
| `other_devices` | Boolean |  |  | yes |  | Other Devices |  |
| `rounding_method` | Many2one | `account.cash.rounding` |  | yes |  | Cash rounding |  |
| `cash_rounding` | Boolean |  |  | yes |  | Cash Rounding |  |
| `only_round_cash_method` | Boolean |  |  | yes |  | Only apply rounding on cash |  |
| `has_active_session` | Boolean |  |  | no |  |  | compute `_compute_current_session` |
| `manual_discount` | Boolean |  |  | yes | default: `True` | Line Discounts |  |
| `ship_later` | Boolean |  |  | yes |  | Ship Later |  |
| `warehouse_id` | Many2one | `stock.warehouse` |  | yes | default: (computed) |  |  |
| `route_id` | Many2one | `stock.route` |  | yes |  | Spefic route for products delivered later. |  |
| `picking_policy` | Selection |  | yes | yes | `direct` As soon as possible, `one` When all products are ready; default: `'direct'` | Shipping Policy |  |
| `auto_validate_terminal_payment` | Boolean |  |  | yes | default: `True` |  |  |
| `trusted_config_ids` | Many2many | `pos.config` (table `pos_config_trust_relation`) |  | yes |  | Trusted Point of Sale Configurations |  |

## `pos.order`

Table `pos_order`.
Description: Point of Sale Orders.
Inherits: `portal.mixin`.
Order: `date_order desc, name desc, id desc`.
Source: `pos_order.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: `'/'` | Order Ref |  |
| `last_order_preparation_change` | Char |  |  | yes |  | Last preparation change |  |
| `date_order` | Datetime |  |  | yes | default: (computed) | Date |  |
| `user_id` | Many2one | `res.users` |  | yes | default: (computed) | Responsible |  |
| `amount_tax` | Float |  | yes | yes |  | Taxes |  |
| `amount_total` | Float |  | yes | yes |  | Total |  |
| `amount_paid` | Float |  | yes | yes |  | Paid |  |
| `amount_return` | Float |  | yes | yes |  | Returned |  |
| `margin` | Monetary |  |  | no |  | Margin | compute `_compute_margin` |
| `margin_percent` | Float |  |  | no |  | Margin (%) | compute `_compute_margin` |
| `is_total_cost_computed` | Boolean |  |  | no |  |  | compute `_compute_is_total_cost_computed` |
| `lines` | One2many | `pos.order.line` (inverse `order_id`) |  | no (inverse) |  | Order Lines |  |
| `company_id` | Many2one | `res.company` | yes | yes |  | Company |  |
| `country_code` | Char |  |  | no |  |  | related `company_id.account_fiscal_country_id.code` |
| `pricelist_id` | Many2one | `product.pricelist` |  | yes |  | Pricelist |  |
| `partner_id` | Many2one | `res.partner` |  | yes |  | Customer |  |
| `sequence_number` | Integer |  |  | yes | default: `1` | Sequence Number |  |
| `session_id` | Many2one | `pos.session` | yes | yes |  | Session |  |
| `config_id` | Many2one | `pos.config` |  | yes |  | Point of Sale | related `session_id.config_id` |
| `currency_id` | Many2one | `res.currency` |  | no |  | Currency | related `config_id.currency_id` |
| `currency_rate` | Float |  |  | yes |  | Currency Rate | compute `_compute_currency_rate` |
| `state` | Selection |  |  | yes | `draft` New, `cancel` Cancelled, `paid` Paid, `done` Posted, `invoiced` Invoiced; default: `'draft'` | Status |  |
| `account_move` | Many2one | `account.move` |  | yes |  | Invoice |  |
| `picking_ids` | One2many | `stock.picking` (inverse `pos_order_id`) |  | no (inverse) |  |  |  |
| `picking_count` | Integer |  |  | no |  |  | compute `_compute_picking_count` |
| `failed_pickings` | Boolean |  |  | no |  |  | compute `_compute_picking_count` |
| `picking_type_id` | Many2one | `stock.picking.type` |  | no |  | Operation Type | related `session_id.config_id.picking_type_id` |
| `procurement_group_id` | Many2one | `procurement.group` |  | yes |  | Procurement Group |  |
| `note` | Text |  |  | yes |  | Internal Notes |  |
| `nb_print` | Integer |  |  | yes | default: `0` | Number of Print |  |
| `pos_reference` | Char |  |  | yes |  | Receipt Number |  |
| `sale_journal` | Many2one | `account.journal` |  | yes |  | Sales Journal | related `session_id.config_id.journal_id` |
| `fiscal_position_id` | Many2one | `account.fiscal.position` |  | yes |  | Fiscal Position |  |
| `payment_ids` | One2many | `pos.payment` (inverse `pos_order_id`) |  | no (inverse) |  | Payments |  |
| `session_move_id` | Many2one | `account.move` |  | no |  | Session Journal Entry | related `session_id.move_id` |
| `to_invoice` | Boolean |  |  | yes |  | To invoice |  |
| `shipping_date` | Date |  |  | yes |  | Shipping Date |  |
| `is_invoiced` | Boolean |  |  | no |  | Is Invoiced | compute `_compute_is_invoiced` |
| `is_tipped` | Boolean |  |  | yes |  | Is this already tipped? |  |
| `tip_amount` | Float |  |  | yes |  | Tip Amount |  |
| `refund_orders_count` | Integer |  |  | no |  | Number of Refund Orders | compute `_compute_refund_related_fields` |
| `is_refunded` | Boolean |  |  | no |  |  | compute `_compute_refund_related_fields` |
| `refunded_order_ids` | Many2many | `pos.order` |  | no |  |  | compute `_compute_refund_related_fields` |
| `has_refundable_lines` | Boolean |  |  | no |  | Has Refundable Lines | compute `_compute_has_refundable_lines` |
| `refunded_orders_count` | Integer |  |  | no |  |  | compute `_compute_refund_related_fields` |
| `ticket_code` | Char |  |  | yes |  |  |  |
| `tracking_number` | Char |  |  | no |  | Order Number | compute `_compute_tracking_number` |

## `pos.order.line`

Table `pos_order_line`.
Description: Point of Sale Order Lines.
Display name field: `product_id`.
Source: `pos_order.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `company_id` | Many2one | `res.company` |  | yes |  | Company | related `order_id.company_id` |
| `name` | Char |  | yes | yes |  | Line No |  |
| `skip_change` | Boolean |  |  | yes |  | Skip line when sending ticket to kitchen printers. |  |
| `notice` | Char |  |  | yes |  | Discount Notice |  |
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `attribute_value_ids` | Many2many | `product.template.attribute.value` |  | yes |  | Selected Attributes |  |
| `custom_attribute_value_ids` | One2many | `product.attribute.custom.value` (inverse `pos_order_line_id`) |  | yes |  | Custom Values |  |
| `price_unit` | Float |  |  | yes |  | Unit Price |  |
| `qty` | Float |  |  | yes | default: `1` | Quantity |  |
| `price_subtotal` | Float |  | yes | yes |  | Subtotal w/o Tax |  |
| `price_subtotal_incl` | Float |  | yes | yes |  | Subtotal |  |
| `price_extra` | Float |  |  | yes |  | Price extra |  |
| `margin` | Monetary |  |  | no |  | Margin | compute `_compute_margin` |
| `margin_percent` | Float |  |  | no |  | Margin (%) | compute `_compute_margin` |
| `total_cost` | Float |  |  | yes |  | Total cost |  |
| `is_total_cost_computed` | Boolean |  |  | yes |  |  |  |
| `discount` | Float |  |  | yes | default: `0.0` | Discount (%) |  |
| `order_id` | Many2one | `pos.order` | yes | yes |  | Order Ref |  |
| `tax_ids` | Many2many | `account.tax` (table `account_tax_pos_order_line_rel`) |  | yes |  | Taxes |  |
| `tax_ids_after_fiscal_position` | Many2many | `account.tax` |  | no |  | Taxes to Apply | compute `_get_tax_ids_after_fiscal_position` |
| `pack_lot_ids` | One2many | `pos.pack.operation.lot` (inverse `pos_order_line_id`) |  | no (inverse) |  | Lot/serial Number |  |
| `product_uom_id` | Many2one | `uom.uom` |  | no |  | Product UoM | related `product_id.uom_id` |
| `currency_id` | Many2one | `res.currency` |  | no |  |  | related `order_id.currency_id` |
| `full_product_name` | Char |  |  | yes |  | Full Product Name |  |
| `customer_note` | Char |  |  | yes |  | Customer Note |  |
| `refund_orderline_ids` | One2many | `pos.order.line` (inverse `refunded_orderline_id`) |  | no (inverse) |  | Refund Order Lines |  |
| `refunded_orderline_id` | Many2one | `pos.order.line` |  | yes |  | Refunded Order Line |  |
| `refunded_qty` | Float |  |  | no |  | Refunded Quantity | compute `_compute_refund_qty` |
| `uuid` | Char |  |  | yes |  | Uuid |  |
| `combo_parent_id` | Many2one | `pos.order.line` |  | yes |  | Combo Parent |  |
| `combo_line_ids` | One2many | `pos.order.line` (inverse `combo_parent_id`) |  | no (inverse) |  | Combo Lines |  |

## `pos.pack.operation.lot`

Table `pos_pack_operation_lot`.
Description: Specify product lot/serial number in pos order line.
Display name field: `lot_name`.
Source: `pos_order.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_order_line_id` | Many2one | `pos.order.line` |  | yes |  |  |  |
| `order_id` | Many2one | `pos.order` |  | no |  |  | related `pos_order_line_id.order_id` |
| `lot_name` | Char |  |  | yes |  | Lot Name |  |
| `product_id` | Many2one | `product.product` |  | no |  |  | related `pos_order_line_id.product_id` |

## `pos.payment`

Table `pos_payment`.
Description: Point of Sale Payments.
Order: `id desc`.
Source: `pos_payment.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  | Label |  |
| `pos_order_id` | Many2one | `pos.order` | yes | yes |  | Order |  |
| `amount` | Monetary |  | yes | yes |  | Amount |  |
| `payment_method_id` | Many2one | `pos.payment.method` | yes | yes |  | Payment Method |  |
| `payment_date` | Datetime |  | yes | yes | default: (computed) | Date |  |
| `currency_id` | Many2one | `res.currency` |  | no |  | Currency | related `pos_order_id.currency_id` |
| `currency_rate` | Float |  |  | no |  | Conversion Rate | related `pos_order_id.currency_rate` |
| `partner_id` | Many2one | `res.partner` |  | no |  | Customer | related `pos_order_id.partner_id` |
| `session_id` | Many2one | `pos.session` |  | yes |  | Session | related `pos_order_id.session_id` |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | related `pos_order_id.company_id` |
| `card_type` | Char |  |  | yes |  | Type of card used |  |
| `cardholder_name` | Char |  |  | yes |  | Cardholder Name |  |
| `transaction_id` | Char |  |  | yes |  | Payment Transaction ID |  |
| `payment_status` | Char |  |  | yes |  | Payment Status |  |
| `ticket` | Char |  |  | yes |  | Payment Receipt Info |  |
| `is_change` | Boolean |  |  | yes | default: `False` | Is this payment change? |  |
| `account_move_id` | Many2one | `account.move` |  | yes |  |  |  |

## `pos.payment.method`

Table `pos_payment_method`.
Description: Point of Sale Payment Methods.
Order: `sequence, id`.
Source: `pos_payment_method.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Method |  |
| `sequence` | Integer |  |  | yes |  |  |  |
| `outstanding_account_id` | Many2one | `account.account` |  | yes |  | Outstanding Account |  |
| `receivable_account_id` | Many2one | `account.account` |  | yes |  | Intermediary Account |  |
| `is_cash_count` | Boolean |  |  | yes |  | Cash | compute `_compute_is_cash_count` |
| `journal_id` | Many2one | `account.journal` |  | yes |  | Journal |  |
| `split_transactions` | Boolean |  |  | yes | default: `False` | Identify Customer |  |
| `open_session_ids` | Many2many | `pos.session` |  | no |  | Pos Sessions | compute `_compute_open_session_ids` |
| `config_ids` | Many2many | `pos.config` |  | yes |  | Point of Sale |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `use_payment_terminal` | Selection |  |  | yes | (dynamic: lambda self: self._get_payment_terminal_selection()) | Use a Payment Terminal |  |
| `hide_use_payment_terminal` | Boolean |  |  | no |  |  | compute `_compute_hide_use_payment_terminal` |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `type` | Selection |  |  | no | `cash` Cash, `bank` Bank, `pay_later` Customer Account |  | compute `_compute_type` |
| `image` | Image |  |  | yes |  | Image |  |

## `pos.printer`

Table `pos_printer`.
Description: Point of Sale Printer.
Source: `pos_printer.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: `'Printer'` | Printer Name |  |
| `printer_type` | Selection |  |  | yes | `iot`  Use a printer connected to the IoT Box; default: `'iot'` | Printer Type |  |
| `proxy_ip` | Char |  |  | yes |  | Proxy IP Address |  |
| `product_categories_ids` | Many2many | `pos.category` (table `printer_category_rel`) |  | yes |  | Printed Product Categories |  |

## `pos.session`

Table `pos_session`.
Description: Point of Sale Session.
Inherits: `mail.thread`, `mail.activity.mixin`.
Order: `id desc`.
Source: `pos_session.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `company_id` | Many2one | `res.company` |  | no |  | Company | related `config_id.company_id` |
| `config_id` | Many2one | `pos.config` | yes | yes |  | Point of Sale |  |
| `name` | Char |  | yes | yes | default: `'/'` | Session ID |  |
| `access_token` | Char |  |  | yes |  | Security Token |  |
| `user_id` | Many2one | `res.users` | yes | yes | default: (computed) | Opened By |  |
| `currency_id` | Many2one | `res.currency` |  | no |  | Currency | related `config_id.currency_id` |
| `start_at` | Datetime |  |  | yes |  | Opening Date |  |
| `stop_at` | Datetime |  |  | yes |  | Closing Date |  |
| `state` | Selection |  | yes | yes | `opening_control` Opening Control, `opened` In Progress, `closing_control` Closing Control, `closed` Closed & Posted; default: `'opening_control'` | Status |  |
| `sequence_number` | Integer |  |  | yes | default: `1` | Order Sequence Number |  |
| `login_number` | Integer |  |  | yes | default: `0` | Login Sequence Number |  |
| `opening_notes` | Text |  |  | yes |  | Opening Notes |  |
| `closing_notes` | Text |  |  | yes |  | Closing Notes |  |
| `cash_control` | Boolean |  |  | no |  | Has Cash Control | compute `_compute_cash_control` |
| `cash_journal_id` | Many2one | `account.journal` |  | yes |  | Cash Journal | compute `_compute_cash_journal` |
| `cash_register_balance_end_real` | Monetary |  |  | yes |  | Ending Balance |  |
| `cash_register_balance_start` | Monetary |  |  | yes |  | Starting Balance |  |
| `cash_register_total_entry_encoding` | Monetary |  |  | no |  | Total Cash Transaction | compute `_compute_cash_balance` |
| `cash_register_balance_end` | Monetary |  |  | no |  | Theoretical Closing Balance | compute `_compute_cash_balance` |
| `cash_register_difference` | Monetary |  |  | no |  | Before Closing Difference | compute `_compute_cash_balance` |
| `cash_real_transaction` | Monetary |  |  | yes |  | Transaction |  |
| `order_ids` | One2many | `pos.order` (inverse `session_id`) |  | no (inverse) |  | Orders |  |
| `order_count` | Integer |  |  | no |  |  | compute `_compute_order_count` |
| `statement_line_ids` | One2many | `account.bank.statement.line` (inverse `pos_session_id`) |  | no (inverse) |  | Cash Lines |  |
| `failed_pickings` | Boolean |  |  | no |  |  | compute `_compute_picking_count` |
| `picking_count` | Integer |  |  | no |  |  | compute `_compute_picking_count` |
| `picking_ids` | One2many | `stock.picking` (inverse `pos_session_id`) |  | no (inverse) |  |  |  |
| `rescue` | Boolean |  |  | yes |  | Recovery Session |  |
| `move_id` | Many2one | `account.move` |  | yes |  | Journal Entry |  |
| `payment_method_ids` | Many2many | `pos.payment.method` |  | no |  | Payment Methods | related `config_id.payment_method_ids` |
| `total_payments_amount` | Float |  |  | no |  | Total Payments Amount | compute `_compute_total_payments_amount` |
| `is_in_company_currency` | Boolean |  |  | no |  | Is Using Company Currency | compute `_compute_is_in_company_currency` |
| `update_stock_at_closing` | Boolean |  |  | yes |  | Stock should be updated at closing |  |
| `bank_payment_ids` | One2many | `account.payment` (inverse `pos_session_id`) |  | no (inverse) |  | Bank Payments |  |

SQL constraints:

- `uniq_name`: `unique(name)`

## `procurement.group` (extension)

Adds fields to `procurement.group`, defined in another module. Every field below is added by this module.
Source: `pos_session.py`, `stock_picking.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_order_id` | Many2one | `pos.order` |  | yes |  | POS Order |  |

## `product.attribute.custom.value` (extension)

Adds fields to `product.attribute.custom.value`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_order_line_id` | Many2one | `pos.order.line` |  | yes |  | PoS Order Line |  |

## `product.product` (extension)

Adds fields to `product.product`, defined in another module. Every field below is added by this module.
Source: `product.py`.

## `product.template` (extension)

Adds fields to `product.template`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `available_in_pos` | Boolean |  |  | yes | default: `False` | Available in POS |  |
| `to_weight` | Boolean |  |  | yes |  | To Weigh With Scale |  |
| `pos_categ_ids` | Many2many | `pos.category` |  | yes |  | Point of Sale Category |  |
| `combo_ids` | Many2many | `pos.combo` |  | yes |  | Combinations |  |
| `detailed_type` | Selection |  |  | yes | added: `combo` Combo |  |  |
| `type` | Selection |  |  | yes | added: `combo` Combo |  |  |

## `report.point_of_sale.report_saledetails`

Abstract model (mixin), no table of its own.
Description: Point of Sale Details.
Source: `report_sale_details.py`.

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Source: `res_company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `point_of_sale_update_stock_quantities` | Selection |  |  | yes | `closing` At the session closing (faster), `real` In real time (accurate but slower); default: `'closing'` | Update quantities in stock |  |
| `point_of_sale_use_ticket_qr_code` | Boolean |  |  | yes |  | Use QR code on ticket |  |
| `point_of_sale_ticket_unique_code` | Boolean |  |  | yes |  | Generate a code on ticket |  |

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_config_id` | Many2one | `pos.config` |  | yes | default: (computed) | Point of Sale |  |
| `sale_tax_id` | Many2one | `account.tax` |  | no |  | Default Sale Tax | related `company_id.account_sale_tax_id` |
| `module_pos_mercury` | Boolean |  |  | yes |  | Vantiv Payment Terminal |  |
| `module_pos_adyen` | Boolean |  |  | yes |  | Adyen Payment Terminal |  |
| `module_pos_stripe` | Boolean |  |  | yes |  | Stripe Payment Terminal |  |
| `module_pos_six` | Boolean |  |  | yes |  | Six Payment Terminal |  |
| `module_pos_paytm` | Boolean |  |  | yes |  | PayTM Payment Terminal |  |
| `module_pos_preparation_display` | Boolean |  |  | yes |  | Preparation Display |  |
| `update_stock_quantities` | Selection |  |  | no |  |  | related `company_id.point_of_sale_update_stock_quantities` |
| `account_default_pos_receivable_account_id` | Many2one | (from related) |  | no |  | Default Account Receivable (PoS) | related `company_id.account_default_pos_receivable_account_id` |
| `barcode_nomenclature_id` | Many2one | `barcode.nomenclature` |  | no |  |  | related `company_id.nomenclature_id` |
| `is_kiosk_mode` | Boolean |  |  | yes | default: `False` | Is Kiosk Mode |  |
| `pos_module_pos_discount` | Boolean |  |  | no |  |  | related `pos_config_id.module_pos_discount` |
| `pos_module_pos_hr` | Boolean |  |  | no |  |  | related `pos_config_id.module_pos_hr` |
| `pos_module_pos_restaurant` | Boolean |  |  | no |  |  | related `pos_config_id.module_pos_restaurant` |
| `pos_is_order_printer` | Boolean |  |  | yes |  |  | compute `_compute_pos_printer` |
| `pos_printer_ids` | Many2many | (from related) |  | no |  |  | related `pos_config_id.printer_ids` |
| `pos_allowed_pricelist_ids` | Many2many | `product.pricelist` |  | no |  |  | compute `_compute_pos_allowed_pricelist_ids` |
| `pos_amount_authorized_diff` | Float |  |  | no |  |  | related `pos_config_id.amount_authorized_diff` |
| `pos_available_pricelist_ids` | Many2many | `product.pricelist` |  | yes |  | Available Pricelists | compute `_compute_pos_pricelist_id` |
| `pos_cash_control` | Boolean |  |  | no |  |  | related `pos_config_id.cash_control` |
| `pos_cash_rounding` | Boolean |  |  | no |  | Cash Rounding (PoS) | related `pos_config_id.cash_rounding` |
| `pos_company_has_template` | Boolean |  |  | no |  |  | related `pos_config_id.company_has_template` |
| `pos_default_bill_ids` | Many2many | (from related) |  | no |  |  | related `pos_config_id.default_bill_ids` |
| `pos_default_fiscal_position_id` | Many2one | `account.fiscal.position` |  | yes |  | Default Fiscal Position | compute `_compute_pos_fiscal_positions` |
| `pos_fiscal_position_ids` | Many2many | `account.fiscal.position` |  | yes |  | Fiscal Positions | compute `_compute_pos_fiscal_positions` |
| `pos_has_active_session` | Boolean |  |  | no |  |  | related `pos_config_id.has_active_session` |
| `pos_iface_available_categ_ids` | Many2many | `pos.category` |  | yes |  | Available PoS Product Categories | compute `_compute_pos_iface_available_categ_ids` |
| `pos_iface_big_scrollbars` | Boolean |  |  | no |  |  | related `pos_config_id.iface_big_scrollbars` |
| `pos_iface_cashdrawer` | Boolean |  |  | yes |  | Cashdrawer | compute `_compute_pos_iface_cashdrawer` |
| `pos_iface_customer_facing_display_local` | Boolean |  |  | no |  |  | related `pos_config_id.iface_customer_facing_display_local` |
| `pos_iface_customer_facing_display_via_proxy` | Boolean |  |  | yes |  | Customer Facing Display | compute `_compute_pos_iface_customer_facing_display_via_proxy` |
| `pos_iface_customer_facing_display_background_image_1920` | Image |  |  | no |  |  | related `pos_config_id.iface_customer_facing_display_background_image_1920` |
| `pos_iface_electronic_scale` | Boolean |  |  | yes |  | Electronic Scale | compute `_compute_pos_iface_electronic_scale` |
| `pos_iface_print_auto` | Boolean |  |  | no |  |  | related `pos_config_id.iface_print_auto` |
| `pos_iface_print_skip_screen` | Boolean |  |  | no |  |  | related `pos_config_id.iface_print_skip_screen` |
| `pos_iface_print_via_proxy` | Boolean |  |  | yes |  | Print via Proxy | compute `_compute_pos_iface_print_via_proxy` |
| `pos_iface_scan_via_proxy` | Boolean |  |  | yes |  | Scan via Proxy | compute `_compute_pos_iface_scan_via_proxy` |
| `pos_iface_start_categ_id` | Many2one | `pos.category` |  | yes |  | Initial Category | compute `_compute_pos_iface_start_categ_id` |
| `pos_iface_tax_included` | Selection |  |  | no |  |  | related `pos_config_id.iface_tax_included` |
| `pos_iface_tipproduct` | Boolean |  |  | no |  |  | related `pos_config_id.iface_tipproduct` |
| `pos_invoice_journal_id` | Many2one | (from related) |  | no |  |  | related `pos_config_id.invoice_journal_id` |
| `pos_is_header_or_footer` | Boolean |  |  | no |  |  | related `pos_config_id.is_header_or_footer` |
| `pos_is_margins_costs_accessible_to_every_user` | Boolean |  |  | no |  |  | related `pos_config_id.is_margins_costs_accessible_to_every_user` |
| `pos_is_posbox` | Boolean |  |  | no |  |  | related `pos_config_id.is_posbox` |
| `pos_journal_id` | Many2one | (from related) |  | no |  |  | related `pos_config_id.journal_id` |
| `pos_limit_categories` | Boolean |  |  | no |  |  | related `pos_config_id.limit_categories` |
| `pos_manual_discount` | Boolean |  |  | no |  |  | related `pos_config_id.manual_discount` |
| `pos_only_round_cash_method` | Boolean |  |  | no |  |  | related `pos_config_id.only_round_cash_method` |
| `pos_other_devices` | Boolean |  |  | no |  |  | related `pos_config_id.other_devices` |
| `pos_payment_method_ids` | Many2many | (from related) |  | no |  |  | related `pos_config_id.payment_method_ids` |
| `pos_picking_policy` | Selection |  |  | no |  |  | related `pos_config_id.picking_policy` |
| `pos_picking_type_id` | Many2one | (from related) |  | no |  |  | related `pos_config_id.picking_type_id` |
| `pos_pricelist_id` | Many2one | `product.pricelist` |  | yes |  | Default Pricelist | compute `_compute_pos_pricelist_id` |
| `pos_proxy_ip` | Char |  |  | yes |  | IP Address | compute `_compute_pos_proxy_ip` |
| `pos_receipt_footer` | Text |  |  | yes |  | Receipt Footer | compute `_compute_pos_receipt_header_footer` |
| `pos_receipt_header` | Text |  |  | yes |  | Receipt Header | compute `_compute_pos_receipt_header_footer` |
| `pos_restrict_price_control` | Boolean |  |  | no |  |  | related `pos_config_id.restrict_price_control` |
| `pos_rounding_method` | Many2one | (from related) |  | no |  |  | related `pos_config_id.rounding_method` |
| `pos_route_id` | Many2one | (from related) |  | no |  |  | related `pos_config_id.route_id` |
| `pos_selectable_categ_ids` | Many2many | `pos.category` |  | no |  |  | compute `_compute_pos_selectable_categ_ids` |
| `pos_sequence_id` | Many2one | (from related) |  | no |  |  | related `pos_config_id.sequence_id` |
| `pos_set_maximum_difference` | Boolean |  |  | no |  |  | related `pos_config_id.set_maximum_difference` |
| `pos_ship_later` | Boolean |  |  | no |  |  | related `pos_config_id.ship_later` |
| `pos_start_category` | Boolean |  |  | no |  |  | related `pos_config_id.start_category` |
| `pos_tax_regime_selection` | Boolean |  |  | no |  |  | related `pos_config_id.tax_regime_selection` |
| `pos_tip_product_id` | Many2one | `product.product` |  | yes |  | Tip Product | compute `_compute_pos_tip_product_id` |
| `pos_use_pricelist` | Boolean |  |  | no |  |  | related `pos_config_id.use_pricelist` |
| `pos_warehouse_id` | Many2one | (from related) |  | no |  | Warehouse (PoS) | related `pos_config_id.warehouse_id` |
| `point_of_sale_use_ticket_qr_code` | Boolean |  |  | no |  |  | related `company_id.point_of_sale_use_ticket_qr_code` |
| `pos_auto_validate_terminal_payment` | Boolean |  |  | no |  | Automatically validates orders paid with a payment terminal. | related `pos_config_id.auto_validate_terminal_payment` |
| `pos_trusted_config_ids` | Many2many | (from related) |  | no |  |  | related `pos_config_id.trusted_config_ids` |
| `point_of_sale_ticket_unique_code` | Boolean |  |  | no |  |  | related `company_id.point_of_sale_ticket_unique_code` |

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_order_count` | Integer |  |  | no |  |  | compute `_compute_pos_order` |
| `pos_order_ids` | One2many | `pos.order` (inverse `partner_id`) |  | no (inverse) |  |  |  |

## `stock.move` (extension)

Adds fields to `stock.move`, defined in another module. Every field below is added by this module.
Source: `stock_picking.py`.

## `stock.picking` (extension)

Adds fields to `stock.picking`, defined in another module. Every field below is added by this module.
Source: `stock_picking.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_session_id` | Many2one | `pos.session` |  | yes |  |  |  |
| `pos_order_id` | Many2one | `pos.order` |  | yes |  |  |  |

## `stock.picking.type` (extension)

Adds fields to `stock.picking.type`, defined in another module. Every field below is added by this module.
Source: `stock_picking.py`.

## `stock.rule` (extension)

Adds fields to `stock.rule`, defined in another module. Every field below is added by this module.
Source: `stock_rule.py`.

## `stock.warehouse` (extension)

Adds fields to `stock.warehouse`, defined in another module. Every field below is added by this module.
Source: `stock_warehouse.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_type_id` | Many2one | `stock.picking.type` |  | yes |  | Point of Sale Operation Type |  |

## `uom.category` (extension)

Adds fields to `uom.category`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `is_pos_groupable` | Boolean |  |  | yes |  | Group Products in POS |  |

## `uom.uom` (extension)

Adds fields to `uom.uom`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `is_pos_groupable` | Boolean |  |  | no |  |  | related `category_id.is_pos_groupable` |
