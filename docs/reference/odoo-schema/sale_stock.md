# Odoo 17.0 module `sale_stock`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 0. Models extended here: 16.

## `account.move` (extension)

Adds fields to `account.move`, defined in another module. Every field below is added by this module.
Source: `account_move.py`.

## `account.move.line` (extension)

Adds fields to `account.move.line`, defined in another module. Every field below is added by this module.
Source: `account_move.py`.

## `procurement.group` (extension)

Adds fields to `procurement.group`, defined in another module. Every field below is added by this module.
Source: `stock.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sale_id` | Many2one | `sale.order` |  | yes |  | Sale Order |  |

## `product.template` (extension)

Adds fields to `product.template`, defined in another module. Every field below is added by this module.
Source: `product_template.py`.

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Source: `res_company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `security_lead` | Float |  | yes | yes | default: `0.0` | Sales Safety Days |  |

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `security_lead` | Float |  |  | no |  | Security Lead Time | related `company_id.security_lead` |
| `use_security_lead` | Boolean |  |  | yes |  | Security Lead Time for Sales |  |
| `default_picking_policy` | Selection |  | yes | yes | `direct` Ship products as soon as available, with back orders, `one` Ship all products at once; default: `'direct'` | Picking Policy |  |

## `res.users` (extension)

Adds fields to `res.users`, defined in another module. Every field below is added by this module.
Source: `res_users.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `property_warehouse_id` | Many2one | `stock.warehouse` |  | no (per company, ir.property) |  | Default Warehouse |  |

## `sale.order` (extension)

Adds fields to `sale.order`, defined in another module. Every field below is added by this module.
Source: `sale_order.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `incoterm` | Many2one | `account.incoterms` |  | yes |  | Incoterm |  |
| `incoterm_location` | Char |  |  | yes |  | Incoterm Location |  |
| `picking_policy` | Selection |  | yes | yes | `direct` As soon as possible, `one` When all products are ready; default: `'direct'` | Shipping Policy |  |
| `warehouse_id` | Many2one | `stock.warehouse` | yes | yes |  | Warehouse | compute `_compute_warehouse_id` |
| `picking_ids` | One2many | `stock.picking` (inverse `sale_id`) |  | no (inverse) |  | Transfers |  |
| `delivery_count` | Integer |  |  | no |  | Delivery Orders | compute `_compute_picking_ids` |
| `delivery_status` | Selection |  |  | yes | `pending` Not Delivered, `started` Started, `partial` Partially Delivered, `full` Fully Delivered | Delivery Status | compute `_compute_delivery_status` |
| `procurement_group_id` | Many2one | `procurement.group` |  | yes |  | Procurement Group |  |
| `effective_date` | Datetime |  |  | yes |  | Effective Date | compute `_compute_effective_date` |
| `expected_date` | Datetime |  |  | yes |  |  |  |
| `json_popover` | Char |  |  | no |  | JSON data for the popover widget | compute `_compute_json_popover` |
| `show_json_popover` | Boolean |  |  | no |  | Has late picking | compute `_compute_json_popover` |

## `sale.order.line` (extension)

Adds fields to `sale.order.line`, defined in another module. Every field below is added by this module.
Source: `sale_order_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `qty_delivered_method` | Selection |  |  | yes | added: `stock_move` Stock Moves |  |  |
| `route_id` | Many2one | `stock.route` |  | yes |  | Route |  |
| `move_ids` | One2many | `stock.move` (inverse `sale_line_id`) |  | no (inverse) |  | Stock Moves |  |
| `virtual_available_at_date` | Float |  |  | no |  |  | compute `_compute_qty_at_date` |
| `scheduled_date` | Datetime |  |  | no |  |  | compute `_compute_qty_at_date` |
| `forecast_expected_date` | Datetime |  |  | no |  |  | compute `_compute_qty_at_date` |
| `free_qty_today` | Float |  |  | no |  |  | compute `_compute_qty_at_date` |
| `qty_available_today` | Float |  |  | no |  |  | compute `_compute_qty_at_date` |
| `warehouse_id` | Many2one | (from related) |  | no |  |  | related `order_id.warehouse_id` |
| `qty_to_deliver` | Float |  |  | no |  |  | compute `_compute_qty_to_deliver` |
| `is_mto` | Boolean |  |  | no |  |  | compute `_compute_is_mto` |
| `display_qty_widget` | Boolean |  |  | no |  |  | compute `_compute_qty_to_deliver` |
| `customer_lead` | Float |  |  | yes |  |  | compute `_compute_customer_lead` |

## `stock.lot` (extension)

Adds fields to `stock.lot`, defined in another module. Every field below is added by this module.
Source: `stock.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sale_order_ids` | Many2many | `sale.order` |  | no |  | Sales Orders | compute `_compute_sale_order_ids` |
| `sale_order_count` | Integer |  |  | no |  | Sale order count | compute `_compute_sale_order_ids` |

## `stock.move` (extension)

Adds fields to `stock.move`, defined in another module. Every field below is added by this module.
Source: `stock.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sale_line_id` | Many2one | `sale.order.line` |  | yes |  | Sale Line |  |

## `stock.move.line` (extension)

Adds fields to `stock.move.line`, defined in another module. Every field below is added by this module.
Source: `stock.py`.

## `stock.picking` (extension)

Adds fields to `stock.picking`, defined in another module. Every field below is added by this module.
Source: `stock.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sale_id` | Many2one | `sale.order` |  | yes |  | Sales Order | compute `_compute_sale_id` |

## `stock.route` (extension)

Adds fields to `stock.route`, defined in another module. Every field below is added by this module.
Source: `stock.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `sale_selectable` | Boolean |  |  | yes |  | Selectable on Sales Order Line |  |

## `stock.rule` (extension)

Adds fields to `stock.rule`, defined in another module. Every field below is added by this module.
Source: `stock.py`.

## `stock.valuation.layer` (extension)

Adds fields to `stock.valuation.layer`, defined in another module. Every field below is added by this module.
Source: `stock_valuation_layer.py`.
