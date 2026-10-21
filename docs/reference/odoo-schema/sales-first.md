# Sales first: the Odoo 17.0 models from quotation to payment

The subset of the schema a small retail shop touches when it sells: who buys, what is sold and at
what price, the quotation and order, the counter sale (point of sale), the invoice, the payment,
loyalty, and the delivery. Field names are exact. Full field tables are in the per-module files
(the module that adds a field is named in brackets when it is not the defining module).
Conventions are in README.md: Many2one is a foreign key, One2many is the inverse side and not a
column, Many2many is a join table, "computed" means not stored unless marked "stored".

Every table also has `id`, `create_uid`, `create_date`, `write_uid`, `write_date`.

## Two sales paths

1. Quotation path (sale): `sale.order` (state `draft` to `sent` to `sale`), then a delivery
   `stock.picking` (sale_stock), then an invoice `account.move` (`move_type` `out_invoice`), then an
   `account.payment` reconciled against the invoice's receivable line.
2. Counter path (point_of_sale): a cashier opens a `pos.session` on a `pos.config`, rings up
   `pos.order` rows paid by `pos.payment` rows; at closing the session posts one journal entry
   (`pos.session.move_id`) and the stock pickings. A `pos.order` gets its own invoice only when
   `to_invoice` is set (state `invoiced`).

## Who: `res.partner` (base, table `res_partner`)

- Identity: `name`, `complete_name`, `is_company`, `parent_id` (company of a contact),
  `commercial_partner_id`, `type` (`contact`, `invoice`, `delivery`, `other`), `ref`, `barcode`,
  `vat`, `company_registry`, `active`, `company_id`, `user_id` (salesperson), `category_id` (tags).
- Contact: `email`, `phone`, `mobile`, `street`, `street2`, `zip`, `city`, `state_id`,
  `country_id`, `lang`, `tz`.
- Sales terms [account]: `property_payment_term_id`, `property_account_position_id`,
  `property_account_receivable_id` (required), `credit_limit`, `trust` (`good`, `normal`, `bad`).
  The `property_*` fields and `trust` are per company in `ir_property`, not columns.
- Ranks [account]: `customer_rank`, `supplier_rank`. Warnings [sale]: `sale_warn`
  (`no-message`, `warning`, `block`), `sale_warn_msg`. Team [crm]: `team_id`.

`res.users` (base) is the login; every user has a `partner_id`. Salesperson and cashier fields
point at `res.users`. `res.company` holds `currency_id` and the company partner.

## What: products

### `product.template` (product, table `product_template`)

- `name` (required), `default_code`, `detailed_type` (required: `consu`, `service`; [stock] adds
  `product`, [point_of_sale] adds `combo`), `type` (stored, computed from `detailed_type`),
  `categ_id` (required, `product.category`), `uom_id` and `uom_po_id` (required, `uom.uom`),
  `list_price` (sales price, Float, default `1.0`), `sale_ok`, `purchase_ok`, `active`,
  `company_id`, `product_tag_ids`, `attribute_line_ids` (variants).
- Taxes [account]: `taxes_id` (Many2many `account.tax`, table `product_taxes_rel`, customer taxes),
  `supplier_taxes_id`.
- Selling [sale]: `invoice_policy` (`order`, `delivery`), `sale_line_warn`.
- Counter [point_of_sale]: `available_in_pos`, `to_weight`, `pos_categ_ids`.
- Stock [stock]: `tracking` (required: `serial`, `lot`, `none`), `sale_delay`, `route_ids`.

### `product.product` (product, table `product_product`), the variant that is actually sold

- Delegates to the template (`_inherits`): `product_tmpl_id` (required).
- Own fields: `default_code`, `barcode`, `active`, `product_template_attribute_value_ids`,
  `combination_indices`, `standard_price` (cost, per company in `ir_property`), `weight`, `volume`.
- SQL constraint `barcode_uniq`: `unique(barcode)`.

### `product.pricelist` and `product.pricelist.item` (product)

- `product.pricelist`: `name` (required), `currency_id` (required), `company_id`, `active`,
  `sequence`, `discount_policy` (required: `with_discount`, `without_discount`),
  `country_group_ids`, `item_ids`.
- `product.pricelist.item` (a rule): `pricelist_id` (required), `applied_on` (required: `3_global`,
  `2_product_category`, `1_product`, `0_product_variant`), `categ_id`, `product_tmpl_id`,
  `product_id`, `min_quantity`, `date_start`, `date_end`, `compute_price` (required: `fixed`,
  `percentage`, `formula`), `fixed_price`, `percent_price`, `base` (required: `list_price`,
  `standard_price`, `pricelist`), `base_pricelist_id`, `price_discount`, `price_surcharge`,
  `price_round`, `price_min_margin`, `price_max_margin`. Rule order: `applied_on`,
  `min_quantity desc`, `categ_id desc`, `id desc`.

### `account.tax` (account)

`name` (required), `type_tax_use` (`sale`, `purchase`, `none`), `amount_type` (`group`, `fixed`,
`percent`, `division`), `amount` (required, Float), `price_include`, `include_base_amount`,
`tax_group_id` (required), `company_id` (required), `country_id` (required),
`tax_exigibility` (`on_invoice`, `on_payment`), `children_tax_ids`, `invoice_label`, `active`.

## Quotation and order (sale)

### `sale.order` (table `sale_order`, order `date_order desc, id desc`)

- Ids and dates: `name` (required, the reference), `client_order_ref`, `origin`, `reference`,
  `date_order` (required), `validity_date` (expiration, stored compute), `commitment_date`,
  `create_date`, `signed_on`; [sale_stock] `effective_date`.
- State: `state` (see state machines), `locked`, `invoice_status` (stored compute),
  [sale_stock] `delivery_status` (stored compute).
- Who: `partner_id` (required), `partner_invoice_id` and `partner_shipping_id` (required, stored
  compute), `user_id` (salesperson), `team_id`, `company_id` (required), `signed_by`.
- Terms: `pricelist_id`, `currency_id`, `currency_rate`, `payment_term_id`, `fiscal_position_id`,
  `journal_id`, `note`, `require_signature`, `require_payment`, `prepayment_percent`.
- Amounts (stored compute, Monetary): `amount_untaxed`, `amount_tax`, `amount_total`,
  `amount_to_invoice`. Not stored: `amount_invoiced`, `amount_paid`, `invoice_ids`,
  `invoice_count`, `tax_totals`.
- Lines and links: `order_line` (One2many `sale.order.line.order_id`), `transaction_ids` (online
  payments, table `sale_order_transaction_rel`), `tag_ids`; [sale_stock] `warehouse_id`
  (required), `picking_policy` (required: `direct`, `one`), `procurement_group_id`, `picking_ids`;
  [sale_loyalty] `applied_coupon_ids`, `code_enabled_rule_ids`, `coupon_point_ids`.
- SQL constraint `date_order_conditional_required`: a confirmed order (`state = 'sale'`) has a
  `date_order`.

### `sale.order.line` (table `sale_order_line`, order `order_id, sequence, id`)

- `order_id` (required), `sequence`, `display_type` (`line_section`, `line_note`, empty for a
  product line), `product_id`, `name` (required, description), `product_uom_qty` (required),
  `product_uom`, `price_unit` (required), `discount` (percent), `tax_id` (Many2many `account.tax`,
  stored compute), `customer_lead` (required).
- Amounts (stored compute): `price_subtotal`, `price_tax`, `price_total`, `price_reduce_taxexcl`,
  `price_reduce_taxinc`.
- Progress: `qty_delivered`, `qty_delivered_method` (`manual`, `analytic`; [sale_stock] adds
  `stock_move`), `qty_invoiced`, `qty_to_invoice`, `invoice_status`, `untaxed_amount_invoiced`,
  `untaxed_amount_to_invoice`.
- Copies of the order kept on the line (stored related): `company_id`, `currency_id`,
  `order_partner_id`, `salesman_id`, `state`.
- Links: `invoice_lines` (Many2many `account.move.line`, table `sale_order_line_invoice_rel`),
  `is_downpayment`; [sale_stock] `move_ids` (One2many `stock.move.sale_line_id`), `route_id`;
  [sale_loyalty] `reward_id`, `coupon_id`, `points_cost`, `reward_identifier_code`.

## Counter sale (point_of_sale)

### `pos.config` (a till)

`name` (required), `company_id` (required), `picking_type_id` (required), `journal_id`,
`invoice_journal_id`, `pricelist_id`, `available_pricelist_ids`, `use_pricelist`,
`payment_method_ids` (Many2many `pos.payment.method`), `iface_tax_included` (required: `subtotal`,
`total`), `cash_rounding`, `rounding_method`, `only_round_cash_method`, `manual_discount`,
`restrict_price_control`, `default_fiscal_position_id`, `warehouse_id`, `receipt_header`,
`receipt_footer`, `sequence_id`, `session_ids`, `active`; [pos_loyalty] `gift_card_settings`.

### `pos.session` (one cashier shift on a till, order `id desc`)

`name` (required), `config_id` (required), `user_id` (required, opened by), `state` (required),
`start_at`, `stop_at`, `cash_journal_id`, `cash_register_balance_start`,
`cash_register_balance_end_real`, `cash_real_transaction`, `opening_notes`, `closing_notes`,
`sequence_number`, `login_number`, `move_id` (the closing journal entry), `order_ids`,
`picking_ids`, `statement_line_ids` (cash in and out), `bank_payment_ids`,
`update_stock_at_closing`, `rescue`.

### `pos.order` (order `date_order desc, name desc, id desc`)

- Ids and dates: `name` (required), `pos_reference` (receipt number), `ticket_code`,
  `sequence_number`, `date_order`, `shipping_date`.
- State: `state`, `to_invoice`.
- Who: `user_id` (cashier), `partner_id`, `session_id` (required), `config_id` (stored related),
  `company_id` (required).
- Amounts (Float, required): `amount_tax`, `amount_total`, `amount_paid`, `amount_return`
  (change given); `tip_amount`, `is_tipped`.
- Links: `lines`, `payment_ids`, `pricelist_id`, `fiscal_position_id`, `account_move` (the
  invoice), `sale_journal`, `picking_ids`, `procurement_group_id`, `note`.

### `pos.order.line`

`order_id` (required), `product_id` (required), `full_product_name`, `name` (required), `qty`,
`price_unit`, `discount`, `tax_ids` (Many2many `account.tax`, table
`account_tax_pos_order_line_rel`), `price_subtotal` (required, without tax),
`price_subtotal_incl` (required, with tax), `total_cost`, `refunded_orderline_id`,
`refund_orderline_ids`, `pack_lot_ids`, `customer_note`, `combo_parent_id`, `uuid`;
[pos_loyalty] `is_reward_line`, `reward_id`, `coupon_id`, `points_cost`.

### `pos.payment` and `pos.payment.method`

- `pos.payment` (order `id desc`): `pos_order_id` (required), `amount` (required, Monetary),
  `payment_method_id` (required), `payment_date` (required), `session_id`, `company_id`,
  `is_change`, `card_type`, `cardholder_name`, `transaction_id`, `payment_status`, `ticket`,
  `account_move_id`.
- `pos.payment.method`: `name` (required), `type` (computed: `cash`, `bank`, `pay_later`),
  `is_cash_count`, `journal_id`, `receivable_account_id`, `outstanding_account_id`,
  `split_transactions`, `use_payment_terminal`, `config_ids`, `company_id`, `active`.

## Invoice and payment (account)

### `account.move` (journal entry and invoice, table `account_move`)

- Ids and dates: `name` (the number), `ref`, `payment_reference`, `invoice_origin`, `date`
  (required, accounting date), `invoice_date`, `invoice_date_due`, `delivery_date`.
- State: `state` (required), `move_type` (required), `payment_state` (stored compute),
  `posted_before`, `to_check`, `inalterable_hash`, `secure_sequence_number`.
- Who: `partner_id`, `commercial_partner_id`, `partner_shipping_id`, `invoice_user_id`
  (salesperson), `company_id`, [sale] `team_id`.
- Terms: `journal_id` (required), `currency_id` (required), `invoice_payment_term_id`,
  `fiscal_position_id`, `invoice_cash_rounding_id`, `narration`.
- Amounts (stored compute, Monetary): `amount_untaxed`, `amount_tax`, `amount_total`,
  `amount_residual` (still due), and the `_signed` versions in company currency.
- Links: `line_ids` and `invoice_line_ids` (both One2many `account.move.line.move_id`),
  `payment_id`, `reversed_entry_id` (credit note of), `statement_line_id`;
  [point_of_sale] `pos_order_ids`, `pos_payment_ids`.

### `account.move.line` (journal item, order `date desc, move_name desc, id`)

- `move_id` (required), `display_type` (required: `product`, `cogs`, `tax`, `discount`,
  `rounding`, `payment_term`, `line_section`, `line_note`, `epd`), `sequence`, `name` (label),
  `account_id`, `partner_id`, `product_id`, `product_uom_id`, `quantity`, `price_unit`,
  `discount`, `tax_ids` (Many2many `account.tax`, table `account_move_line_account_tax_rel`),
  `tax_line_id` (the tax a tax line is for), `tax_base_amount`.
- Amounts: `price_subtotal`, `price_total`, `debit`, `credit`, `balance`, `amount_currency`,
  `currency_id` (required), `amount_residual`, `amount_residual_currency`.
- Matching: `reconciled`, `full_reconcile_id`, `matched_debit_ids`, `matched_credit_ids`,
  `matching_number`, `date_maturity`, `payment_id`.
- Stored copies of the move: `journal_id`, `company_id`, `move_name`, `parent_state`, `date`,
  `ref`. [sale] `sale_line_ids` (the other side of `sale.order.line.invoice_lines`).

### `account.payment` (table `account_payment`, order `date desc, name desc`)

- Delegates to `account.move` (`_inherits`): `move_id` (required). Its `name`, `date`, `state`,
  `journal_id`, `partner_id`, `currency_id` live on that move.
- Own fields: `payment_type` (required: `outbound`, `inbound`), `partner_type` (required:
  `customer`, `supplier`), `amount` (Monetary), `payment_reference`, `partner_id`, `currency_id`,
  `payment_method_line_id`, `payment_method_id` (stored related), `destination_account_id`,
  `outstanding_account_id`, `is_reconciled`, `is_matched`, `is_internal_transfer`;
  [point_of_sale] `pos_payment_method_id`, `pos_session_id`.

### `account.payment.method` and `account.payment.method.line`

- `account.payment.method`: `name` (required), `code` (required), `payment_type` (required:
  `inbound`, `outbound`). SQL constraint: `code` and `payment_type` unique together.
- `account.payment.method.line` (a method enabled on a journal): `payment_method_id` (required),
  `journal_id`, `name`, `sequence`, `payment_account_id`.

### How a payment settles an invoice

`account.partial.reconcile` matches two journal items: `debit_move_id` (the invoice's receivable
line) and `credit_move_id` (the payment's receivable line), with `amount` and `max_date`. When the
residual reaches zero the lines share an `account.full.reconcile`, and `account.move.payment_state`
becomes `paid` (or `in_payment` while the payment waits for bank matching).

## Loyalty (loyalty, sale_loyalty, pos_loyalty)

- `loyalty.program`: `name` (required), `program_type` (required), `trigger` (`auto`,
  `with_code`), `applies_on` (required: `current`, `future`, `both`), `date_from`, `date_to`,
  `limit_usage`, `max_usage`, `currency_id` (required), `company_id`, `pricelist_ids`, `active`,
  `rule_ids`, `reward_ids`, `coupon_ids`; [sale_loyalty] `sale_ok`; [pos_loyalty] `pos_ok`,
  `pos_config_ids`.
- `loyalty.rule` (earning): `program_id` (required), `mode` (`auto`, `with_code`), `code`,
  `product_ids`, `product_category_id`, `product_tag_id`, `minimum_qty`, `minimum_amount`,
  `minimum_amount_tax_mode` (`incl`, `excl`), `reward_point_amount`, `reward_point_mode`
  (from a method: `order`, `money`, `unit`), `reward_point_split`.
- `loyalty.reward` (spending): `program_id` (required), `reward_type` (required: `product`,
  `discount`), `discount`, `discount_mode` (from a method: `percent`, `per_point`, `per_order`),
  `discount_applicability` (`order`, `cheapest`, `specific`), `discount_max_amount`,
  `discount_product_ids`, `reward_product_id`, `reward_product_qty`, `required_points`,
  `discount_line_product_id`, `description`.
- `loyalty.card` (a card, coupon or gift card): `program_id`, `partner_id`, `code` (required,
  unique), `points`, `expiration_date`, `company_id`; [sale_loyalty] `order_id`;
  [pos_loyalty] `source_pos_order_id`.
- `sale.order.coupon.points` [sale_loyalty]: `order_id`, `coupon_id`, `points` (all required),
  unique per order and card. Odoo 17 has no points history table; points live on `loyalty.card`.

## Delivery (stock, sale_stock)

- `stock.picking` (a transfer, order `priority desc, scheduled_date asc, id desc`): `name`,
  `origin` (the sale order name), `state` (stored compute), `move_type` (required: `direct`,
  `one`), `picking_type_id` (required; its `code` is `incoming`, `outgoing` or `internal`),
  `location_id`, `location_dest_id` (both required), `partner_id`, `user_id`, `company_id`,
  `scheduled_date`, `date_deadline`, `date_done`, `backorder_id`, `return_id`, `group_id`,
  `move_ids`; [sale_stock] `sale_id`; [point_of_sale] `pos_order_id`, `pos_session_id`.
- `stock.move` (one product line of a transfer): `name` (required), `product_id` (required),
  `product_uom_qty` (required, demand), `quantity` (done), `product_uom` (required), `state`,
  `date` (required), `location_id`, `location_dest_id` (both required), `picking_id`,
  `partner_id`, `price_unit`, `origin`, `procure_method` (required: `make_to_stock`,
  `make_to_order`), `group_id`, `company_id` (required), `picked`; [sale_stock] `sale_line_id`.
  Stock on hand is `stock.quant` (`product_id`, `location_id`, `quantity`), changed by done moves.

## State machines (literal `state` selections)

- `sale.order.state`: `draft` Quotation, `sent` Quotation Sent, `sale` Sales Order, `cancel`
  Cancelled (default `draft`). Separate flags: `locked`; `invoice_status` `upselling`, `invoiced`,
  `to invoice`, `no`; `delivery_status` `pending`, `started`, `partial`, `full`.
- `pos.session.state`: `opening_control` Opening Control, `opened` In Progress,
  `closing_control` Closing Control, `closed` Closed & Posted (default `opening_control`).
- `pos.order.state`: `draft` New, `cancel` Cancelled, `paid` Paid, `done` Posted, `invoiced`
  Invoiced (default `draft`).
- `account.move.state`: `draft` Draft, `posted` Posted, `cancel` Cancelled (default `draft`).
  `account.move.move_type`: `entry`, `out_invoice`, `out_refund`, `in_invoice`, `in_refund`,
  `out_receipt`, `in_receipt` (default `entry`). `account.move.payment_state`: `not_paid`,
  `in_payment`, `paid`, `partial`, `reversed`, `invoicing_legacy`.
- `account.payment`: no own state; it uses its move's `state` through `_inherits`.
- `stock.picking.state`: `draft` Draft, `waiting` Waiting Another Operation, `confirmed`
  Waiting, `assigned` Ready, `done` Done, `cancel` Cancelled.
- `stock.move.state`: `draft` New, `waiting` Waiting Another Move, `confirmed` Waiting
  Availability, `partially_available` Partially Available, `assigned` Available, `done` Done,
  `cancel` Cancelled (default `draft`).
- `loyalty.program.program_type` (not a state, but it decides behaviour): `coupons`,
  `gift_card`, `loyalty`, `promotion`, `ewallet`, `promo_code`, `buy_x_get_y`,
  `next_order_coupons` (default `promotion`).

## Foreign keys

The main ones; every Many2one in the per-module files is a foreign key.

Partners, products and prices:

- res.partner.parent_id -> res.partner
- res.partner.commercial_partner_id -> res.partner
- res.partner.user_id -> res.users
- product.product.product_tmpl_id -> product.template
- product.template.categ_id -> product.category
- product.template.taxes_id -> account.tax (join table product_taxes_rel)
- product.pricelist.item.pricelist_id -> product.pricelist
- product.pricelist.item.product_tmpl_id -> product.template
- product.pricelist.item.product_id -> product.product
- product.pricelist.item.categ_id -> product.category
- product.pricelist.item.base_pricelist_id -> product.pricelist

Sale:

- sale.order.partner_id -> res.partner
- sale.order.partner_invoice_id -> res.partner
- sale.order.partner_shipping_id -> res.partner
- sale.order.user_id -> res.users
- sale.order.pricelist_id -> product.pricelist
- sale.order.payment_term_id -> account.payment.term
- sale.order.warehouse_id -> stock.warehouse
- sale.order.transaction_ids -> payment.transaction (join table sale_order_transaction_rel)
- sale.order.applied_coupon_ids -> loyalty.card
- sale.order.line.order_id -> sale.order
- sale.order.line.product_id -> product.product
- sale.order.line.product_uom -> uom.uom
- sale.order.line.tax_id -> account.tax (join table)
- sale.order.line.invoice_lines -> account.move.line (join table sale_order_line_invoice_rel)
- sale.order.line.reward_id -> loyalty.reward
- sale.order.line.coupon_id -> loyalty.card
- sale.order.coupon.points.order_id -> sale.order
- sale.order.coupon.points.coupon_id -> loyalty.card

Point of sale:

- pos.config.journal_id -> account.journal
- pos.config.pricelist_id -> product.pricelist
- pos.config.payment_method_ids -> pos.payment.method (join table)
- pos.session.config_id -> pos.config
- pos.session.user_id -> res.users
- pos.session.move_id -> account.move
- pos.order.session_id -> pos.session
- pos.order.config_id -> pos.config
- pos.order.partner_id -> res.partner
- pos.order.user_id -> res.users
- pos.order.pricelist_id -> product.pricelist
- pos.order.account_move -> account.move
- pos.order.line.order_id -> pos.order
- pos.order.line.product_id -> product.product
- pos.order.line.tax_ids -> account.tax (join table account_tax_pos_order_line_rel)
- pos.order.line.refunded_orderline_id -> pos.order.line
- pos.order.line.reward_id -> loyalty.reward
- pos.order.line.coupon_id -> loyalty.card
- pos.payment.pos_order_id -> pos.order
- pos.payment.payment_method_id -> pos.payment.method
- pos.payment.session_id -> pos.session
- pos.payment.account_move_id -> account.move
- pos.payment.method.journal_id -> account.journal

Invoice and payment:

- account.move.partner_id -> res.partner
- account.move.journal_id -> account.journal
- account.move.invoice_user_id -> res.users
- account.move.payment_id -> account.payment
- account.move.reversed_entry_id -> account.move
- account.move.line.move_id -> account.move
- account.move.line.account_id -> account.account
- account.move.line.partner_id -> res.partner
- account.move.line.product_id -> product.product
- account.move.line.tax_ids -> account.tax (join table account_move_line_account_tax_rel)
- account.move.line.tax_line_id -> account.tax
- account.move.line.payment_id -> account.payment
- account.move.line.full_reconcile_id -> account.full.reconcile
- account.partial.reconcile.debit_move_id -> account.move.line
- account.partial.reconcile.credit_move_id -> account.move.line
- account.payment.move_id -> account.move
- account.payment.partner_id -> res.partner
- account.payment.payment_method_line_id -> account.payment.method.line
- account.payment.pos_payment_method_id -> pos.payment.method
- account.payment.pos_session_id -> pos.session
- account.payment.method.line.payment_method_id -> account.payment.method
- account.payment.method.line.journal_id -> account.journal

Loyalty:

- loyalty.rule.program_id -> loyalty.program
- loyalty.reward.program_id -> loyalty.program
- loyalty.reward.reward_product_id -> product.product
- loyalty.card.program_id -> loyalty.program
- loyalty.card.partner_id -> res.partner
- loyalty.card.order_id -> sale.order
- loyalty.card.source_pos_order_id -> pos.order

Delivery:

- stock.picking.sale_id -> sale.order
- stock.picking.pos_order_id -> pos.order
- stock.picking.pos_session_id -> pos.session
- stock.picking.partner_id -> res.partner
- stock.move.picking_id -> stock.picking
- stock.move.sale_line_id -> sale.order.line
- stock.move.product_id -> product.product

