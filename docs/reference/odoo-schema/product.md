# Odoo 17.0 module `product`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 16. Models extended here: 8.

## `decimal.precision` (extension)

Adds fields to `decimal.precision`, defined in another module. Every field below is added by this module.
Source: `decimal_precision.py`.

## `ir.attachment` (extension)

Adds fields to `ir.attachment`, defined in another module. Every field below is added by this module.
Source: `ir_attachment.py`.

## `product.attribute`

Table `product_attribute`.
Description: Product Attribute.
Order: `sequence, id`.
Source: `product_attribute.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Attribute |  |
| `create_variant` | Selection |  | yes | yes | `always` Instantly, `dynamic` Dynamically, `no_variant` Never (option); default: `'always'` | Variants Creation Mode |  |
| `display_type` | Selection |  | yes | yes | `radio` Radio, `pills` Pills, `select` Select, `color` Color, `multi` Multi-checkbox (option); default: `'radio'` |  |  |
| `sequence` | Integer |  |  | yes | default: `20` | Sequence |  |
| `value_ids` | One2many | `product.attribute.value` (inverse `attribute_id`) |  | no (inverse) |  | Values |  |
| `attribute_line_ids` | One2many | `product.template.attribute.line` (inverse `attribute_id`) |  | no (inverse) |  | Lines |  |
| `product_tmpl_ids` | Many2many | `product.template` |  | yes |  | Related Products | compute `_compute_products` |
| `number_related_products` | Integer |  |  | no |  |  | compute `_compute_number_related_products` |

SQL constraints:

- `check_multi_checkbox_no_variant`: `CHECK(display_type != 'multi' OR create_variant = 'no_variant')`

## `product.attribute.custom.value`

Table `product_attribute_custom_value`.
Description: Product Attribute Custom Value.
Order: `custom_product_template_attribute_value_id, id`.
Source: `product_attribute_custom_value.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | no |  | Name | compute `_compute_name` |
| `custom_product_template_attribute_value_id` | Many2one | `product.template.attribute.value` | yes | yes |  | Attribute Value |  |
| `custom_value` | Char |  |  | yes |  | Custom Value |  |

## `product.attribute.value`

Table `product_attribute_value`.
Description: Attribute Value.
Order: `attribute_id, sequence, id`.
Source: `product_attribute_value.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Value |  |
| `sequence` | Integer |  |  | yes |  | Sequence |  |
| `attribute_id` | Many2one | `product.attribute` | yes | yes |  | Attribute |  |
| `pav_attribute_line_ids` | Many2many | `product.template.attribute.line` (table `product_attribute_value_product_template_attribute_line_rel`) |  | yes |  | Lines |  |
| `is_used_on_products` | Boolean |  |  | no |  | Used on Products | compute `_compute_is_used_on_products` |
| `default_extra_price` | Float |  |  | yes |  |  |  |
| `is_custom` | Boolean |  |  | yes |  | Is custom value |  |
| `html_color` | Char |  |  | yes |  | Color |  |
| `display_type` | Selection |  |  | no |  |  | related `attribute_id.display_type` |
| `color` | Integer |  |  | yes | default: (computed) | Color Index |  |
| `image` | Image |  |  | yes |  | Image |  |

SQL constraints:

- `value_company_uniq`: `unique (name, attribute_id)`

## `product.catalog.mixin`

Abstract model (mixin), no table of its own.
Description: Product Catalog Mixin.
Source: `product_catalog_mixin.py`.

## `product.category`

Table `product_category`.
Description: Product Category.
Order: `complete_name`.
Display name field: `complete_name`.
Source: `product_category.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `complete_name` | Char |  |  | yes |  | Complete Name | compute `_compute_complete_name` |
| `parent_id` | Many2one | `product.category` |  | yes |  | Parent Category |  |
| `parent_path` | Char |  |  | yes |  |  |  |
| `child_id` | One2many | `product.category` (inverse `parent_id`) |  | no (inverse) |  | Child Categories |  |
| `product_count` | Integer |  |  | no |  | # Products | compute `_compute_product_count` |
| `product_properties_definition` | PropertiesDefinition |  |  | yes |  | Product Properties |  |

## `product.document`

Table `product_document`.
Description: Product Document.
Delegates (`_inherits`): `{'ir.attachment': 'ir_attachment_id'}`.
Order: `name`.
Source: `product_document.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `ir_attachment_id` | Many2one | `ir.attachment` | yes | yes |  | Related attachment |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |

## `product.packaging`

Table `product_packaging`.
Description: Product Packaging.
Order: `product_id, sequence, id`.
Source: `product_packaging.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Product Packaging |  |
| `sequence` | Integer |  |  | yes | default: `1` | Sequence |  |
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `qty` | Float |  |  | yes | default: `1` | Contained Quantity |  |
| `barcode` | Char |  |  | yes |  | Barcode |  |
| `product_uom_id` | Many2one | `uom.uom` |  | no |  |  | related `product_id.uom_id` |
| `company_id` | Many2one | `res.company` |  | yes |  | Company |  |

SQL constraints:

- `positive_qty`: `CHECK(qty > 0)`
- `barcode_uniq`: `unique(barcode)`

## `product.pricelist`

Table `product_pricelist`.
Description: Pricelist.
Inherits: `mail.thread`, `mail.activity.mixin`.
Order: `sequence asc, id asc`.
Source: `product_pricelist.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Pricelist Name |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `sequence` | Integer |  |  | yes | default: `16` |  |  |
| `currency_id` | Many2one | `res.currency` | yes | yes | default: (computed) |  |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) |  |  |
| `country_group_ids` | Many2many | `res.country.group` (table `res_country_group_pricelist_rel`) |  | yes |  | Country Groups |  |
| `discount_policy` | Selection |  | yes | yes | `with_discount` Discount included in the price, `without_discount` Show public price & discount to the customer; default: `'with_discount'` |  |  |
| `item_ids` | One2many | `product.pricelist.item` (inverse `pricelist_id`) |  | no (inverse) |  | Pricelist Rules |  |

## `product.pricelist.item`

Table `product_pricelist_item`.
Description: Pricelist Rule.
Order: `applied_on, min_quantity desc, categ_id desc, id desc`.
Source: `product_pricelist_item.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pricelist_id` | Many2one | `product.pricelist` | yes | yes | default: (computed) | Pricelist |  |
| `company_id` | Many2one | (from related) |  | yes |  |  | related `pricelist_id.company_id` |
| `currency_id` | Many2one | (from related) |  | yes |  |  | related `pricelist_id.currency_id` |
| `date_start` | Datetime |  |  | yes |  | Start Date |  |
| `date_end` | Datetime |  |  | yes |  | End Date |  |
| `min_quantity` | Float |  |  | yes | default: `0` | Min. Quantity |  |
| `applied_on` | Selection |  | yes | yes | `3_global` All Products, `2_product_category` Product Category, `1_product` Product, `0_product_variant` Product Variant; default: `'3_global'` | Apply On |  |
| `categ_id` | Many2one | `product.category` |  | yes |  | Product Category |  |
| `product_tmpl_id` | Many2one | `product.template` |  | yes |  | Product |  |
| `product_id` | Many2one | `product.product` |  | yes |  | Product Variant |  |
| `base` | Selection |  | yes | yes | `list_price` Sales Price, `standard_price` Cost, `pricelist` Other Pricelist; default: `'list_price'` | Based on |  |
| `base_pricelist_id` | Many2one | `product.pricelist` |  | yes |  | Other Pricelist |  |
| `compute_price` | Selection |  | yes | yes | `fixed` Fixed Price, `percentage` Discount, `formula` Formula; default: `'fixed'` |  |  |
| `fixed_price` | Float |  |  | yes |  | Fixed Price |  |
| `percent_price` | Float |  |  | yes |  | Percentage Price |  |
| `price_discount` | Float |  |  | yes | default: `0` | Price Discount |  |
| `price_round` | Float |  |  | yes |  | Price Rounding |  |
| `price_surcharge` | Float |  |  | yes |  | Price Surcharge |  |
| `price_min_margin` | Float |  |  | yes |  | Min. Price Margin |  |
| `price_max_margin` | Float |  |  | yes |  | Max. Price Margin |  |
| `name` | Char |  |  | no |  | Name | compute `_compute_name_and_price` |
| `price` | Char |  |  | no |  | Price | compute `_compute_name_and_price` |
| `rule_tip` | Char |  |  | no |  |  | compute `_compute_rule_tip` |

## `product.product`

Table `product_product`.
Description: Product Variant.
Inherits: `mail.thread`, `mail.activity.mixin`.
Delegates (`_inherits`): `{'product.template': 'product_tmpl_id'}`.
Order: `priority desc, default_code, name, id`.
Source: `product_product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `price_extra` | Float |  |  | no |  | Variant Price Extra | compute `_compute_product_price_extra` |
| `lst_price` | Float |  |  | no |  | Sales Price | compute `_compute_product_lst_price` |
| `default_code` | Char |  |  | yes |  | Internal Reference |  |
| `code` | Char |  |  | no |  | Reference | compute `_compute_product_code` |
| `partner_ref` | Char |  |  | no |  | Customer Ref | compute `_compute_partner_ref` |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `product_tmpl_id` | Many2one | `product.template` | yes | yes |  | Product Template |  |
| `barcode` | Char |  |  | yes |  | Barcode |  |
| `product_template_attribute_value_ids` | Many2many | `product.template.attribute.value` (table `product_variant_combination`) |  | yes |  | Attribute Values |  |
| `product_template_variant_value_ids` | Many2many | `product.template.attribute.value` (table `product_variant_combination`) |  | yes |  | Variant Values |  |
| `combination_indices` | Char |  |  | yes |  |  | compute `_compute_combination_indices` |
| `is_product_variant` | Boolean |  |  | no |  |  | compute `_compute_is_product_variant` |
| `standard_price` | Float |  |  | no (per company, ir.property) |  | Cost |  |
| `volume` | Float |  |  | yes |  | Volume |  |
| `weight` | Float |  |  | yes |  | Weight |  |
| `pricelist_item_count` | Integer |  |  | no |  | Number of price rules | compute `_compute_variant_item_count` |
| `product_document_ids` | One2many | `product.document` (inverse `res_id`) |  | no (inverse) |  | Documents |  |
| `product_document_count` | Integer |  |  | no |  | Documents Count | compute `_compute_product_document_count` |
| `packaging_ids` | One2many | `product.packaging` (inverse `product_id`) |  | no (inverse) |  | Product Packages |  |
| `additional_product_tag_ids` | Many2many | `product.tag` (table `product_tag_product_product_rel`) |  | yes |  | Additional Product Tags |  |
| `all_product_tag_ids` | Many2many | `product.tag` |  | no |  |  | compute `_compute_all_product_tag_ids` |
| `image_variant_1920` | Image |  |  | yes |  | Variant Image |  |
| `image_variant_1024` | Image |  |  | yes |  | Variant Image 1024 | related `image_variant_1920` |
| `image_variant_512` | Image |  |  | yes |  | Variant Image 512 | related `image_variant_1920` |
| `image_variant_256` | Image |  |  | yes |  | Variant Image 256 | related `image_variant_1920` |
| `image_variant_128` | Image |  |  | yes |  | Variant Image 128 | related `image_variant_1920` |
| `can_image_variant_1024_be_zoomed` | Boolean |  |  | yes |  | Can Variant Image 1024 be zoomed | compute `_compute_can_image_variant_1024_be_zoomed` |
| `image_1920` | Image |  |  | no |  | Image | compute `_compute_image_1920` |
| `image_1024` | Image |  |  | no |  | Image 1024 | compute `_compute_image_1024` |
| `image_512` | Image |  |  | no |  | Image 512 | compute `_compute_image_512` |
| `image_256` | Image |  |  | no |  | Image 256 | compute `_compute_image_256` |
| `image_128` | Image |  |  | no |  | Image 128 | compute `_compute_image_128` |
| `can_image_1024_be_zoomed` | Boolean |  |  | no |  | Can Image 1024 be zoomed | compute `_compute_can_image_1024_be_zoomed` |
| `write_date` | Datetime |  |  | yes |  |  | compute `_compute_write_date` |

## `product.supplierinfo`

Table `product_supplierinfo`.
Description: Supplier Pricelist.
Order: `sequence, min_qty DESC, price, id`.
Display name field: `partner_id`.
Source: `product_supplierinfo.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `partner_id` | Many2one | `res.partner` | yes | yes |  | Vendor |  |
| `product_name` | Char |  |  | yes |  | Vendor Product Name |  |
| `product_code` | Char |  |  | yes |  | Vendor Product Code |  |
| `sequence` | Integer |  |  | yes | default: `1` | Sequence |  |
| `product_uom` | Many2one | `uom.uom` |  | no |  | Unit of Measure | related `product_tmpl_id.uom_po_id` |
| `min_qty` | Float |  | yes | yes | default: `0.0` | Quantity |  |
| `price` | Float |  | yes | yes | default: `0.0` | Price |  |
| `price_discounted` | Float |  |  | no |  | Discounted Price | compute `_compute_price_discounted` |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `currency_id` | Many2one | `res.currency` | yes | yes | default: (computed) | Currency |  |
| `date_start` | Date |  |  | yes |  | Start Date |  |
| `date_end` | Date |  |  | yes |  | End Date |  |
| `product_id` | Many2one | `product.product` |  | yes | default: (computed) | Product Variant |  |
| `product_tmpl_id` | Many2one | `product.template` |  | yes |  | Product Template |  |
| `product_variant_count` | Integer |  |  | no |  | Variant Count | related `product_tmpl_id.product_variant_count` |
| `delay` | Integer |  | yes | yes | default: `1` | Delivery Lead Time |  |
| `discount` | Float |  |  | yes |  | Discount (%) |  |

## `product.tag`

Table `product_tag`.
Description: Product Tag.
Source: `product_tag.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `color` | Char |  |  | yes | default: `'#3C3C3C'` | Color |  |
| `product_template_ids` | Many2many | `product.template` (table `product_tag_product_template_rel`) |  | yes | default: (computed) | Product Templates |  |
| `product_product_ids` | Many2many | `product.product` (table `product_tag_product_product_rel`) |  | yes | default: (computed) | Product Variants |  |
| `product_ids` | Many2many | `product.product` |  | no |  | All Product Variants using this Tag | compute `_compute_product_ids` |

SQL constraints:

- `name_uniq`: `unique (name)`

## `product.template`

Table `product_template`.
Description: Product.
Inherits: `mail.thread`, `mail.activity.mixin`, `image.mixin`.
Order: `priority desc, name`.
Source: `product_template.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `sequence` | Integer |  |  | yes | default: `1` | Sequence |  |
| `description` | Html |  |  | yes |  | Description |  |
| `description_purchase` | Text |  |  | yes |  | Purchase Description |  |
| `description_sale` | Text |  |  | yes |  | Sales Description |  |
| `detailed_type` | Selection |  | yes | yes | `consu` Consumable, `service` Service; default: `'consu'` | Product Type |  |
| `type` | Selection |  |  | yes | `consu` Consumable, `service` Service |  | compute `_compute_type` |
| `categ_id` | Many2one | `product.category` | yes | yes | default: (computed) | Product Category |  |
| `currency_id` | Many2one | `res.currency` |  | no |  | Currency | compute `_compute_currency_id` |
| `cost_currency_id` | Many2one | `res.currency` |  | no |  | Cost Currency | compute `_compute_cost_currency_id` |
| `list_price` | Float |  |  | yes | default: `1.0` | Sales Price |  |
| `standard_price` | Float |  |  | no |  | Cost | compute `_compute_standard_price` |
| `volume` | Float |  |  | yes |  | Volume | compute `_compute_volume` |
| `volume_uom_name` | Char |  |  | no |  | Volume unit of measure label | compute `_compute_volume_uom_name` |
| `weight` | Float |  |  | yes |  | Weight | compute `_compute_weight` |
| `weight_uom_name` | Char |  |  | no |  | Weight unit of measure label | compute `_compute_weight_uom_name` |
| `sale_ok` | Boolean |  |  | yes | default: `True` | Can be Sold |  |
| `purchase_ok` | Boolean |  |  | yes | default: `True` | Can be Purchased |  |
| `uom_id` | Many2one | `uom.uom` | yes | yes | default: (computed) | Unit of Measure |  |
| `uom_name` | Char |  |  | no |  | Unit of Measure Name | related `uom_id.name` |
| `uom_po_id` | Many2one | `uom.uom` | yes | yes |  | Purchase UoM | compute `_compute_uom_po_id` |
| `company_id` | Many2one | `res.company` |  | yes |  | Company |  |
| `packaging_ids` | One2many | `product.packaging` |  | no (inverse) |  | Product Packages | compute `_compute_packaging_ids` |
| `seller_ids` | One2many | `product.supplierinfo` (inverse `product_tmpl_id`) |  | no (inverse) |  | Vendors |  |
| `variant_seller_ids` | One2many | `product.supplierinfo` (inverse `product_tmpl_id`) |  | no (inverse) |  |  |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `color` | Integer |  |  | yes |  | Color Index |  |
| `is_product_variant` | Boolean |  |  | no |  | Is a product variant | compute `_compute_is_product_variant` |
| `attribute_line_ids` | One2many | `product.template.attribute.line` (inverse `product_tmpl_id`) |  | no (inverse) |  | Product Attributes |  |
| `valid_product_template_attribute_line_ids` | Many2many | `product.template.attribute.line` |  | no |  | Valid Product Attribute Lines | compute `_compute_valid_product_template_attribute_line_ids` |
| `product_variant_ids` | One2many | `product.product` (inverse `product_tmpl_id`) | yes | no (inverse) |  | Products |  |
| `product_variant_id` | Many2one | `product.product` |  | no |  | Product | compute `_compute_product_variant_id` |
| `product_variant_count` | Integer |  |  | no |  | # Product Variants | compute `_compute_product_variant_count` |
| `barcode` | Char |  |  | no |  | Barcode | compute `_compute_barcode` |
| `default_code` | Char |  |  | yes |  | Internal Reference | compute `_compute_default_code` |
| `pricelist_item_count` | Integer |  |  | no |  | Number of price rules | compute `_compute_item_count` |
| `product_document_ids` | One2many | `product.document` (inverse `res_id`) |  | no (inverse) |  | Documents |  |
| `product_document_count` | Integer |  |  | no |  | Documents Count | compute `_compute_product_document_count` |
| `can_image_1024_be_zoomed` | Boolean |  |  | yes |  | Can Image 1024 be zoomed | compute `_compute_can_image_1024_be_zoomed` |
| `has_configurable_attributes` | Boolean |  |  | yes |  | Is a configurable product | compute `_compute_has_configurable_attributes` |
| `product_tooltip` | Char |  |  | no |  |  | compute `_compute_product_tooltip` |
| `priority` | Selection |  |  | yes | `0` Normal, `1` Favorite; default: `'0'` | Favorite |  |
| `product_tag_ids` | Many2many | `product.tag` (table `product_tag_product_template_rel`) |  | yes |  | Product Template Tags |  |
| `product_properties` | Properties |  |  | yes |  | Properties |  |

## `product.template.attribute.exclusion`

Table `product_template_attribute_exclusion`.
Description: Product Template Attribute Exclusion.
Order: `product_tmpl_id, id`.
Source: `product_template_attribute_exclusion.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `product_template_attribute_value_id` | Many2one | `product.template.attribute.value` |  | yes |  | Attribute Value |  |
| `product_tmpl_id` | Many2one | `product.template` | yes | yes |  | Product Template |  |
| `value_ids` | Many2many | `product.template.attribute.value` (table `product_attr_exclusion_value_ids_rel`) |  | yes |  | Attribute Values |  |

## `product.template.attribute.line`

Table `product_template_attribute_line`.
Description: Product Template Attribute Line.
Order: `sequence, attribute_id, id`.
Display name field: `attribute_id`.
Source: `product_template_attribute_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `product_tmpl_id` | Many2one | `product.template` | yes | yes |  | Product Template |  |
| `sequence` | Integer |  |  | yes | default: `10` | Sequence |  |
| `attribute_id` | Many2one | `product.attribute` | yes | yes |  | Attribute |  |
| `value_ids` | Many2many | `product.attribute.value` (table `product_attribute_value_product_template_attribute_line_rel`) |  | yes |  | Values |  |
| `value_count` | Integer |  |  | yes |  |  | compute `_compute_value_count` |
| `product_template_value_ids` | One2many | `product.template.attribute.value` (inverse `attribute_line_id`) |  | no (inverse) |  | Product Attribute Values |  |

## `product.template.attribute.value`

Table `product_template_attribute_value`.
Description: Product Template Attribute Value.
Order: `attribute_line_id, product_attribute_value_id, id`.
Source: `product_template_attribute_value.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `ptav_active` | Boolean |  |  | yes | default: `True` | Active |  |
| `name` | Char |  |  | no |  | Value | related `product_attribute_value_id.name` |
| `product_attribute_value_id` | Many2one | `product.attribute.value` | yes | yes |  | Attribute Value |  |
| `attribute_line_id` | Many2one | `product.template.attribute.line` | yes | yes |  |  |  |
| `price_extra` | Float |  |  | yes | default: `0.0` | Value Price Extra |  |
| `currency_id` | Many2one | (from related) |  | no |  |  | related `attribute_line_id.product_tmpl_id.currency_id` |
| `exclude_for` | One2many | `product.template.attribute.exclusion` (inverse `product_template_attribute_value_id`) |  | no (inverse) |  | Exclude for |  |
| `product_tmpl_id` | Many2one | (from related) |  | yes |  |  | related `attribute_line_id.product_tmpl_id` |
| `attribute_id` | Many2one | (from related) |  | yes |  |  | related `attribute_line_id.attribute_id` |
| `ptav_product_variant_ids` | Many2many | `product.product` (table `product_variant_combination`) |  | yes |  | Related Variants |  |
| `html_color` | Char |  |  | no |  | HTML Color Index | related `product_attribute_value_id.html_color` |
| `is_custom` | Boolean |  |  | no |  |  | related `product_attribute_value_id.is_custom` |
| `display_type` | Selection |  |  | no |  |  | related `product_attribute_value_id.display_type` |
| `color` | Integer |  |  | yes | default: (computed) | Color |  |
| `image` | Image |  |  | no |  |  | related `product_attribute_value_id.image` |

SQL constraints:

- `attribute_value_unique`: `unique(attribute_line_id, product_attribute_value_id)`

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Source: `res_company.py`.

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `group_discount_per_so_line` | Boolean |  |  | yes |  | Discounts |  |
| `group_uom` | Boolean |  |  | yes |  | Units of Measure |  |
| `group_product_variant` | Boolean |  |  | yes |  | Variants |  |
| `module_sale_product_matrix` | Boolean |  |  | yes |  | Sales Grid Entry |  |
| `module_loyalty` | Boolean |  |  | yes |  | Promotions, Coupons, Gift Card & Loyalty Program |  |
| `group_stock_packaging` | Boolean |  |  | yes |  | Product Packagings |  |
| `group_product_pricelist` | Boolean |  |  | yes |  | Pricelists |  |
| `group_sale_pricelist` | Boolean |  |  | yes |  | Advanced Pricelists |  |
| `product_pricelist_setting` | Selection |  |  | yes | `basic` Multiple prices per product, `advanced` Advanced price rules (discounts, formulas); default: `'basic'` | Pricelists Method |  |
| `product_weight_in_lbs` | Selection |  |  | yes | `0` Kilograms, `1` Pounds; default: `'0'` | Weight unit of measure |  |
| `product_volume_volume_in_cubic_feet` | Selection |  |  | yes | `0` Cubic Meters, `1` Cubic Feet; default: `'0'` | Volume unit of measure |  |

## `res.country.group` (extension)

Adds fields to `res.country.group`, defined in another module. Every field below is added by this module.
Source: `res_country_group.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `pricelist_ids` | Many2many | `product.pricelist` (table `res_country_group_pricelist_rel`) |  | yes |  | Pricelists |  |

## `res.currency` (extension)

Adds fields to `res.currency`, defined in another module. Every field below is added by this module.
Source: `res_currency.py`.

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `property_product_pricelist` | Many2one | `product.pricelist` |  | no |  | Pricelist | compute `_compute_product_pricelist` |

## `uom.uom` (extension)

Adds fields to `uom.uom`, defined in another module. Every field below is added by this module.
Source: `uom_uom.py`.
