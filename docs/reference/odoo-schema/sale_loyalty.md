# Odoo 17.0 module `sale_loyalty`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 1. Models extended here: 5.

## `loyalty.card` (extension)

Adds fields to `loyalty.card`, defined in another module. Every field below is added by this module.
Source: `loyalty_card.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `order_id` | Many2one | `sale.order` |  | yes |  | Order Reference |  |

## `loyalty.program` (extension)

Adds fields to `loyalty.program`, defined in another module. Every field below is added by this module.
Source: `loyalty_program.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `order_count` | Integer |  |  | no |  |  | compute `_compute_order_count` |
| `sale_ok` | Boolean |  |  | yes | default: `True` | Sales |  |

## `loyalty.reward` (extension)

Adds fields to `loyalty.reward`, defined in another module. Every field below is added by this module.
Source: `loyalty_reward.py`.

## `sale.order` (extension)

Adds fields to `sale.order`, defined in another module. Every field below is added by this module.
Source: `sale_order.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `applied_coupon_ids` | Many2many | `loyalty.card` |  | yes |  | Manually Applied Coupons |  |
| `code_enabled_rule_ids` | Many2many | `loyalty.rule` |  | yes |  | Manually Triggered Rules |  |
| `coupon_point_ids` | One2many | `sale.order.coupon.points` (inverse `order_id`) |  | no (inverse) |  |  |  |
| `reward_amount` | Float |  |  | no |  |  | compute `_compute_reward_total` |

## `sale.order.coupon.points`

Table `sale_order_coupon_points`.
Description: Sale Order Coupon Points - Keeps track of how a sale order impacts a coupon.
Source: `sale_order_coupon_points.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `order_id` | Many2one | `sale.order` | yes | yes |  |  |  |
| `coupon_id` | Many2one | `loyalty.card` | yes | yes |  |  |  |
| `points` | Float |  | yes | yes |  |  |  |

SQL constraints:

- `order_coupon_unique`: `UNIQUE (order_id, coupon_id)`

## `sale.order.line` (extension)

Adds fields to `sale.order.line`, defined in another module. Every field below is added by this module.
Source: `sale_order_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `is_reward_line` | Boolean |  |  | no |  | Is a program reward line | compute `_compute_is_reward_line` |
| `reward_id` | Many2one | `loyalty.reward` |  | yes |  |  |  |
| `coupon_id` | Many2one | `loyalty.card` |  | yes |  |  |  |
| `reward_identifier_code` | Char |  |  | yes |  |  |  |
| `points_cost` | Float |  |  | yes |  |  |  |
