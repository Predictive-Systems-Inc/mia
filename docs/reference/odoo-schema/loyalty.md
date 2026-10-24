# Odoo 17.0 module `loyalty`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 5. Models extended here: 4.

## `loyalty.card`

Table `loyalty_card`.
Description: Loyalty Coupon.
Inherits: `mail.thread`.
Display name field: `code`.
Source: `loyalty_card.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `program_id` | Many2one | `loyalty.program` |  | yes | default: (computed) |  |  |
| `program_type` | Selection |  |  | no |  |  | related `program_id.program_type` |
| `company_id` | Many2one | (from related) |  | yes |  |  | related `program_id.company_id` |
| `currency_id` | Many2one | (from related) |  | no |  |  | related `program_id.currency_id` |
| `partner_id` | Many2one | `res.partner` |  | yes |  |  |  |
| `points` | Float |  |  | yes |  |  |  |
| `point_name` | Char |  |  | no |  |  | related `program_id.portal_point_name` |
| `points_display` | Char |  |  | no |  |  | compute `_compute_points_display` |
| `code` | Char |  | yes | yes | default: (computed) |  |  |
| `expiration_date` | Date |  |  | yes |  |  |  |
| `use_count` | Integer |  |  | no |  |  | compute `_compute_use_count` |

SQL constraints:

- `card_code_unique`: `UNIQUE(code)`

## `loyalty.mail`

Table `loyalty_mail`.
Description: Loyalty Communication.
Source: `loyalty_mail.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `program_id` | Many2one | `loyalty.program` | yes | yes |  |  |  |
| `trigger` | Selection |  | yes | yes | `create` At Creation, `points_reach` When Reaching | When |  |
| `points` | Float |  |  | yes |  |  |  |
| `mail_template_id` | Many2one | `mail.template` | yes | yes |  | Email Template |  |

## `loyalty.program`

Table `loyalty_program`.
Description: Loyalty Program.
Order: `sequence`.
Display name field: `name`.
Source: `loyalty_program.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Program Name |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `sequence` | Integer |  |  | yes |  |  |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `currency_id` | Many2one | `res.currency` | yes | yes |  | Currency | compute `_compute_currency_id` |
| `currency_symbol` | Char |  |  | no |  |  | related `currency_id.symbol` |
| `pricelist_ids` | Many2many | `product.pricelist` |  | yes |  | Pricelist |  |
| `total_order_count` | Integer |  |  | no |  | Total Order Count | compute `_compute_total_order_count` |
| `rule_ids` | One2many | `loyalty.rule` (inverse `program_id`) |  | yes |  | Conditional rules | compute `_compute_from_program_type` |
| `reward_ids` | One2many | `loyalty.reward` (inverse `program_id`) |  | yes |  | Rewards | compute `_compute_from_program_type` |
| `communication_plan_ids` | One2many | `loyalty.mail` (inverse `program_id`) |  | yes |  |  | compute `_compute_from_program_type` |
| `mail_template_id` | Many2one | `mail.template` |  | no |  | Email template | compute `_compute_mail_template_id` |
| `trigger_product_ids` | Many2many | (from related) |  | no |  |  | related `rule_ids.product_ids` |
| `coupon_ids` | One2many | `loyalty.card` (inverse `program_id`) |  | no (inverse) |  |  |  |
| `coupon_count` | Integer |  |  | no |  |  | compute `_compute_coupon_count` |
| `coupon_count_display` | Char |  |  | no |  | Items | compute `_compute_coupon_count_display` |
| `program_type` | Selection |  | yes | yes | `coupons` Coupons, `gift_card` Gift Card, `loyalty` Loyalty Cards, `promotion` Promotions, `ewallet` eWallet, `promo_code` Discount Code, `buy_x_get_y` Buy X Get Y, `next_order_coupons` Next Order Coupons; default: `'promotion'` |  |  |
| `date_from` | Date |  |  | yes |  | Start Date |  |
| `date_to` | Date |  |  | yes |  | End date |  |
| `limit_usage` | Boolean |  |  | yes |  | Limit Usage |  |
| `max_usage` | Integer |  |  | yes |  |  |  |
| `applies_on` | Selection |  | yes | yes | `current` Current order, `future` Future orders, `both` Current & Future orders; default: `'current'` |  | compute `_compute_from_program_type` |
| `trigger` | Selection |  |  | yes | `auto` Automatic, `with_code` Use a code |  | compute `_compute_from_program_type` |
| `portal_visible` | Boolean |  |  | yes | default: `False` |  |  |
| `portal_point_name` | Char |  |  | yes | default: `'Points'` |  | compute `_compute_portal_point_name` |
| `is_nominative` | Boolean |  |  | no |  |  | compute `_compute_is_nominative` |
| `is_payment_program` | Boolean |  |  | no |  |  | compute `_compute_is_payment_program` |
| `payment_program_discount_product_id` | Many2one | `product.product` |  | no |  | Discount Product | compute `_compute_payment_program_discount_product_id` |
| `available_on` | Boolean |  |  | no |  | Available On |  |

SQL constraints:

- `check_max_usage`: `CHECK (limit_usage = False OR max_usage > 0)`

## `loyalty.reward`

Table `loyalty_reward`.
Description: Loyalty Reward.
Order: `required_points asc`.
Display name field: `description`.
Source: `loyalty_reward.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `program_id` | Many2one | `loyalty.program` | yes | yes |  |  |  |
| `program_type` | Selection |  |  | no |  |  | related `program_id.program_type` |
| `company_id` | Many2one | (from related) |  | yes |  |  | related `program_id.company_id` |
| `currency_id` | Many2one | (from related) |  | no |  |  | related `program_id.currency_id` |
| `description` | Char |  |  | yes |  |  | compute `_compute_description` |
| `reward_type` | Selection |  | yes | yes | `product` Free Product, `discount` Discount; default: `'discount'` |  |  |
| `user_has_debug` | Boolean |  |  | no |  |  | compute `_compute_user_has_debug` |
| `discount` | Float |  |  | yes | default: `10` | Discount |  |
| `discount_mode` | Selection |  | yes | yes | (dynamic: _get_discount_mode_select); default: `'percent'` |  |  |
| `discount_applicability` | Selection |  |  | yes | `order` Order, `cheapest` Cheapest Product, `specific` Specific Products; default: `'order'` |  |  |
| `discount_product_domain` | Char |  |  | yes | default: `'[]'` |  |  |
| `discount_product_ids` | Many2many | `product.product` |  | yes |  | Discounted Products |  |
| `discount_product_category_id` | Many2one | `product.category` |  | yes |  | Discounted Prod. Categories |  |
| `discount_product_tag_id` | Many2one | `product.tag` |  | yes |  | Discounted Prod. Tag |  |
| `all_discount_product_ids` | Many2many | `product.product` |  | no |  |  | compute `_compute_all_discount_product_ids` |
| `reward_product_domain` | Char |  |  | no |  |  | compute `_compute_reward_product_domain` |
| `discount_max_amount` | Monetary |  |  | yes |  | Max Discount |  |
| `discount_line_product_id` | Many2one | `product.product` |  | yes |  |  |  |
| `is_global_discount` | Boolean |  |  | no |  |  | compute `_compute_is_global_discount` |
| `reward_product_id` | Many2one | `product.product` |  | yes |  | Product |  |
| `reward_product_tag_id` | Many2one | `product.tag` |  | yes |  | Product Tag |  |
| `multi_product` | Boolean |  |  | no |  |  | compute `_compute_multi_product` |
| `reward_product_ids` | Many2many | `product.product` |  | no |  | Reward Products | compute `_compute_multi_product` |
| `reward_product_qty` | Integer |  |  | yes | default: `1` |  |  |
| `reward_product_uom_id` | Many2one | `uom.uom` |  | no |  |  | compute `_compute_reward_product_uom_id` |
| `required_points` | Float |  |  | yes | default: `1` | Points needed |  |
| `point_name` | Char |  |  | no |  |  | related `program_id.portal_point_name` |
| `clear_wallet` | Boolean |  |  | yes | default: `False` |  |  |

SQL constraints:

- `required_points_positive`: `CHECK (required_points > 0)`
- `product_qty_positive`: `CHECK (reward_type != 'product' OR reward_product_qty > 0)`
- `discount_positive`: `CHECK (reward_type != 'discount' OR discount > 0)`

## `loyalty.rule`

Table `loyalty_rule`.
Description: Loyalty Rule.
Source: `loyalty_rule.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `program_id` | Many2one | `loyalty.program` | yes | yes |  |  |  |
| `program_type` | Selection |  |  | no |  |  | related `program_id.program_type` |
| `company_id` | Many2one | (from related) |  | yes |  |  | related `program_id.company_id` |
| `currency_id` | Many2one | (from related) |  | no |  |  | related `program_id.currency_id` |
| `user_has_debug` | Boolean |  |  | no |  |  | compute `_compute_user_has_debug` |
| `product_domain` | Char |  |  | yes | default: `'[]'` |  |  |
| `product_ids` | Many2many | `product.product` |  | yes |  | Products |  |
| `product_category_id` | Many2one | `product.category` |  | yes |  | Categories |  |
| `product_tag_id` | Many2one | `product.tag` |  | yes |  | Product Tag |  |
| `reward_point_amount` | Float |  |  | yes | default: `1` | Reward |  |
| `reward_point_split` | Boolean |  |  | yes | default: `False` | Split per unit |  |
| `reward_point_name` | Char |  |  | no |  |  | related `program_id.portal_point_name` |
| `reward_point_mode` | Selection |  | yes | yes | (dynamic: _get_reward_point_mode_selection); default: `'order'` |  |  |
| `minimum_qty` | Integer |  |  | yes | default: `1` | Minimum Quantity |  |
| `minimum_amount` | Monetary |  |  | yes |  | Minimum Purchase |  |
| `minimum_amount_tax_mode` | Selection |  | yes | yes | `incl` Included, `excl` Excluded; default: `'incl'` |  |  |
| `mode` | Selection |  |  | yes | `auto` Automatic, `with_code` With a promotion code | Application | compute `_compute_mode` |
| `code` | Char |  |  | yes |  | Discount code | compute `_compute_code` |

SQL constraints:

- `reward_point_amount_positive`: `CHECK (reward_point_amount > 0)`

## `product.pricelist` (extension)

Adds fields to `product.pricelist`, defined in another module. Every field below is added by this module.
Source: `product_pricelist.py`.

## `product.product` (extension)

Adds fields to `product.product`, defined in another module. Every field below is added by this module.
Source: `product_product.py`.

## `product.template` (extension)

Adds fields to `product.template`, defined in another module. Every field below is added by this module.
Source: `product_template.py`.

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `loyalty_card_count` | Integer |  |  | no |  | Active loyalty cards | compute `_compute_count_active_cards` |
