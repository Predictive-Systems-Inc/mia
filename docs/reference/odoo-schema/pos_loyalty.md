# Odoo 17.0 module `pos_loyalty`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 0. Models extended here: 11.

## `barcode.rule` (extension)

Adds fields to `barcode.rule`, defined in another module. Every field below is added by this module.
Source: `barcode_rule.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `type` | Selection |  |  | yes | added: `coupon` Coupon |  |  |

## `loyalty.card` (extension)

Adds fields to `loyalty.card`, defined in another module. Every field below is added by this module.
Source: `loyalty_card.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `source_pos_order_id` | Many2one | `pos.order` |  | yes |  | PoS Order Reference |  |

## `loyalty.mail` (extension)

Adds fields to `loyalty.mail`, defined in another module. Every field below is added by this module.
Source: `loyalty_mail.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_report_print_id` | Many2one | `ir.actions.report` |  | yes |  | Print Report |  |

## `loyalty.program` (extension)

Adds fields to `loyalty.program`, defined in another module. Every field below is added by this module.
Source: `loyalty_program.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_config_ids` | Many2many | `pos.config` |  | yes |  | Point of Sales | compute `_compute_pos_config_ids` |
| `pos_order_count` | Integer |  |  | no |  | PoS Order Count | compute `_compute_pos_order_count` |
| `pos_ok` | Boolean |  |  | yes | default: `True` | Point of Sale |  |
| `pos_report_print_id` | Many2one | `ir.actions.report` |  | no |  | Print Report | compute `_compute_pos_report_print_id` |

## `loyalty.reward` (extension)

Adds fields to `loyalty.reward`, defined in another module. Every field below is added by this module.
Source: `loyalty_reward.py`.

## `loyalty.rule` (extension)

Adds fields to `loyalty.rule`, defined in another module. Every field below is added by this module.
Source: `loyalty_rule.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `valid_product_ids` | Many2many | `product.product` (table `Valid Products`) |  | no |  |  | compute `_compute_valid_product_ids` |
| `any_product` | Boolean |  |  | no |  |  | compute `_compute_valid_product_ids` |
| `promo_barcode` | Char |  |  | yes |  | Barcode | compute `_compute_promo_barcode` |

## `pos.config` (extension)

Adds fields to `pos.config`, defined in another module. Every field below is added by this module.
Source: `pos_config.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `gift_card_settings` | Selection |  |  | yes | `create_set` Generate PDF cards, `scan_use` Scan existing cards; default: `'create_set'` | Gift Cards settings |  |

## `pos.order` (extension)

Adds fields to `pos.order`, defined in another module. Every field below is added by this module.
Source: `pos_order.py`.

## `pos.order.line` (extension)

Adds fields to `pos.order.line`, defined in another module. Every field below is added by this module.
Source: `pos_order_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `is_reward_line` | Boolean |  |  | yes |  |  |  |
| `reward_id` | Many2one | `loyalty.reward` |  | yes |  | Reward |  |
| `coupon_id` | Many2one | `loyalty.card` |  | yes |  | Coupon |  |
| `reward_identifier_code` | Char |  |  | yes |  |  |  |
| `points_cost` | Float |  |  | yes |  |  |  |

## `pos.session` (extension)

Adds fields to `pos.session`, defined in another module. Every field below is added by this module.
Source: `pos_session.py`.

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pos_gift_card_settings` | Selection |  |  | no |  |  | related `pos_config_id.gift_card_settings` |
