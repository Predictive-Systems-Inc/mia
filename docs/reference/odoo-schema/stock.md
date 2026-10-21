# Odoo 17.0 module `stock`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 20. Models extended here: 11.

## `barcode.rule` (extension)

Adds fields to `barcode.rule`, defined in another module. Every field below is added by this module.
Source: `barcode.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `type` | Selection |  |  | yes | added: `weight` Weighted Product, `location` Location, `lot` Lot, `package` Package |  |  |

## `ir.actions.report` (extension)

Adds fields to `ir.actions.report`, defined in another module. Every field below is added by this module.
Source: `ir_actions_report.py`.

## `procurement.group`

Table `procurement_group`.
Description: Procurement Group.
Order: `id desc`.
Source: `stock_rule.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `partner_id` | Many2one | `res.partner` |  | yes |  | Partner |  |
| `name` | Char |  | yes | yes | default: (computed) | Reference |  |
| `move_type` | Selection |  | yes | yes | `direct` Partial, `one` All at once; default: `'direct'` | Delivery Type |  |
| `stock_move_ids` | One2many | `stock.move` (inverse `group_id`) |  | no (inverse) |  | Related Stock Moves |  |

## `product.category` (extension)

Adds fields to `product.category`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `route_ids` | Many2many | `stock.route` (table `stock_route_categ`) |  | yes |  | Routes |  |
| `removal_strategy_id` | Many2one | `product.removal` |  | yes |  | Force Removal Strategy |  |
| `total_route_ids` | Many2many | `stock.route` |  | no |  | Total routes | compute `_compute_total_route_ids` |
| `putaway_rule_ids` | One2many | `stock.putaway.rule` (inverse `category_id`) |  | no (inverse) |  | Putaway Rules |  |
| `packaging_reserve_method` | Selection |  |  | yes | `full` Reserve Only Full Packagings, `partial` Reserve Partial Packagings; default: `'partial'` | Reserve Packagings |  |
| `filter_for_stock_putaway_rule` | Boolean |  |  | no |  | stock.putaway.rule |  |

## `product.packaging` (extension)

Adds fields to `product.packaging`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `package_type_id` | Many2one | `stock.package.type` |  | yes |  | Package Type |  |
| `route_ids` | Many2many | `stock.route` (table `stock_route_packaging`) |  | yes |  | Routes |  |

## `product.product` (extension)

Adds fields to `product.product`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `stock_quant_ids` | One2many | `stock.quant` (inverse `product_id`) |  | no (inverse) |  |  |  |
| `stock_move_ids` | One2many | `stock.move` (inverse `product_id`) |  | no (inverse) |  |  |  |
| `qty_available` | Float |  |  | no |  | Quantity On Hand | compute `_compute_quantities` |
| `virtual_available` | Float |  |  | no |  | Forecasted Quantity | compute `_compute_quantities` |
| `free_qty` | Float |  |  | no |  | Free To Use Quantity  | compute `_compute_quantities` |
| `incoming_qty` | Float |  |  | no |  | Incoming | compute `_compute_quantities` |
| `outgoing_qty` | Float |  |  | no |  | Outgoing | compute `_compute_quantities` |
| `orderpoint_ids` | One2many | `stock.warehouse.orderpoint` (inverse `product_id`) |  | no (inverse) |  | Minimum Stock Rules |  |
| `nbr_moves_in` | Integer |  |  | no |  |  | compute `_compute_nbr_moves` |
| `nbr_moves_out` | Integer |  |  | no |  |  | compute `_compute_nbr_moves` |
| `nbr_reordering_rules` | Integer |  |  | no |  | Reordering Rules | compute `_compute_nbr_reordering_rules` |
| `reordering_min_qty` | Float |  |  | no |  |  | compute `_compute_nbr_reordering_rules` |
| `reordering_max_qty` | Float |  |  | no |  |  | compute `_compute_nbr_reordering_rules` |
| `putaway_rule_ids` | One2many | `stock.putaway.rule` (inverse `product_id`) |  | no (inverse) |  | Putaway Rules |  |
| `storage_category_capacity_ids` | One2many | `stock.storage.category.capacity` (inverse `product_id`) |  | no (inverse) |  | Storage Category Capacity |  |
| `show_on_hand_qty_status_button` | Boolean |  |  | no |  |  | compute `_compute_show_qty_status_button` |
| `show_forecasted_qty_status_button` | Boolean |  |  | no |  |  | compute `_compute_show_qty_status_button` |
| `valid_ean` | Boolean |  |  | no |  | Barcode is valid EAN | compute `_compute_valid_ean` |
| `lot_properties_definition` | PropertiesDefinition |  |  | yes |  | Lot Properties |  |

## `product.removal`

Table `product_removal`.
Description: Removal Strategy.
Source: `product_strategy.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `method` | Char |  | yes | yes |  | Method |  |

## `product.template` (extension)

Adds fields to `product.template`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `responsible_id` | Many2one | `res.users` |  | no (per company, ir.property) | default: (computed) | Responsible |  |
| `detailed_type` | Selection |  |  | yes | added: `product` Storable Product |  |  |
| `type` | Selection |  |  | yes | added: `product` Storable Product |  |  |
| `property_stock_production` | Many2one | `stock.location` |  | no (per company, ir.property) |  | Production Location |  |
| `property_stock_inventory` | Many2one | `stock.location` |  | no (per company, ir.property) |  | Inventory Location |  |
| `sale_delay` | Integer |  |  | yes | default: `0` | Customer Lead Time |  |
| `tracking` | Selection |  | yes | yes | `serial` By Unique Serial Number, `lot` By Lots, `none` No Tracking; default: `'none'` | Tracking | compute `_compute_tracking` |
| `description_picking` | Text |  |  | yes |  | Description on Picking |  |
| `description_pickingout` | Text |  |  | yes |  | Description on Delivery Orders |  |
| `description_pickingin` | Text |  |  | yes |  | Description on Receptions |  |
| `qty_available` | Float |  |  | no |  | Quantity On Hand | compute `_compute_quantities` |
| `virtual_available` | Float |  |  | no |  | Forecasted Quantity | compute `_compute_quantities` |
| `incoming_qty` | Float |  |  | no |  | Incoming | compute `_compute_quantities` |
| `outgoing_qty` | Float |  |  | no |  | Outgoing | compute `_compute_quantities` |
| `location_id` | Many2one | `stock.location` |  | no |  | Location |  |
| `warehouse_id` | Many2one | `stock.warehouse` |  | no |  | Warehouse |  |
| `has_available_route_ids` | Boolean |  |  | no | default: (computed) | Routes can be selected on this product | compute `_compute_has_available_route_ids` |
| `route_ids` | Many2many | `stock.route` (table `stock_route_product`) |  | yes |  | Routes |  |
| `nbr_moves_in` | Integer |  |  | no |  |  | compute `_compute_nbr_moves` |
| `nbr_moves_out` | Integer |  |  | no |  |  | compute `_compute_nbr_moves` |
| `nbr_reordering_rules` | Integer |  |  | no |  | Reordering Rules | compute `_compute_nbr_reordering_rules` |
| `reordering_min_qty` | Float |  |  | no |  |  | compute `_compute_nbr_reordering_rules` |
| `reordering_max_qty` | Float |  |  | no |  |  | compute `_compute_nbr_reordering_rules` |
| `route_from_categ_ids` | Many2many | (from related) |  | no |  | Category Routes | related `categ_id.total_route_ids` |
| `show_on_hand_qty_status_button` | Boolean |  |  | no |  |  | compute `_compute_show_qty_status_button` |
| `show_forecasted_qty_status_button` | Boolean |  |  | no |  |  | compute `_compute_show_qty_status_button` |

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Source: `res_company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `internal_transit_location_id` | Many2one | `stock.location` |  | yes |  | Internal Transit Location |  |
| `stock_move_email_validation` | Boolean |  |  | yes | default: `False` | Email Confirmation picking |  |
| `stock_mail_confirmation_template_id` | Many2one | `mail.template` |  | yes | default: (computed) | Email Template confirmation picking |  |
| `annual_inventory_month` | Selection |  |  | yes | `1` January, `2` February, `3` March, `4` April, `5` May, `6` June, `7` July, `8` August, `9` September, `10` October, `11` November, `12` December; default: `'12'` | Annual Inventory Month |  |
| `annual_inventory_day` | Integer |  |  | yes | default: `31` | Day of the month |  |

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `module_product_expiry` | Boolean |  |  | yes |  | Expiration Dates |  |
| `group_stock_production_lot` | Boolean |  |  | yes |  | Lots & Serial Numbers |  |
| `group_stock_lot_print_gs1` | Boolean |  |  | yes |  | Print GS1 Barcodes for Lots & Serial Numbers |  |
| `group_lot_on_delivery_slip` | Boolean |  |  | yes |  | Display Lots & Serial Numbers on Delivery Slips |  |
| `group_stock_tracking_lot` | Boolean |  |  | yes |  | Packages |  |
| `group_stock_tracking_owner` | Boolean |  |  | yes |  | Consignment |  |
| `group_stock_adv_location` | Boolean |  |  | yes |  | Multi-Step Routes |  |
| `group_warning_stock` | Boolean |  |  | yes |  | Warnings for Stock |  |
| `group_stock_sign_delivery` | Boolean |  |  | yes |  | Signature |  |
| `module_stock_picking_batch` | Boolean |  |  | yes |  | Batch Transfers |  |
| `group_stock_picking_wave` | Boolean |  |  | yes |  | Wave Transfers |  |
| `module_stock_barcode` | Boolean |  |  | yes |  | Barcode Scanner |  |
| `stock_move_email_validation` | Boolean |  |  | no |  |  | related `company_id.stock_move_email_validation` |
| `module_stock_sms` | Boolean |  |  | yes |  | SMS Confirmation |  |
| `module_delivery` | Boolean |  |  | yes |  | Delivery Methods |  |
| `module_delivery_dhl` | Boolean |  |  | yes |  | DHL Express Connector |  |
| `module_delivery_fedex` | Boolean |  |  | yes |  | FedEx Connector |  |
| `module_delivery_ups` | Boolean |  |  | yes |  | UPS Connector |  |
| `module_delivery_usps` | Boolean |  |  | yes |  | USPS Connector |  |
| `module_delivery_bpost` | Boolean |  |  | yes |  | bpost Connector |  |
| `module_delivery_easypost` | Boolean |  |  | yes |  | Easypost Connector |  |
| `module_delivery_sendcloud` | Boolean |  |  | yes |  | Sendcloud Connector |  |
| `module_delivery_shiprocket` | Boolean |  |  | yes |  | Shiprocket Connector |  |
| `module_quality_control` | Boolean |  |  | yes |  | Quality |  |
| `module_quality_control_worksheet` | Boolean |  |  | yes |  | Quality Worksheet |  |
| `group_stock_multi_locations` | Boolean |  |  | yes |  | Storage Locations |  |
| `group_stock_storage_categories` | Boolean |  |  | yes |  | Storage Categories |  |
| `annual_inventory_month` | Selection |  |  | no |  |  | related `company_id.annual_inventory_month` |
| `annual_inventory_day` | Integer |  |  | no |  |  | related `company_id.annual_inventory_day` |
| `group_stock_reception_report` | Boolean |  |  | yes |  | Reception Report |  |
| `module_stock_dropshipping` | Boolean |  |  | yes |  | Dropshipping |  |

## `res.partner` (extension)

Adds fields to `res.partner`, defined in another module. Every field below is added by this module.
Source: `res_partner.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `property_stock_customer` | Many2one | `stock.location` |  | no (per company, ir.property) |  | Customer Location |  |
| `property_stock_supplier` | Many2one | `stock.location` |  | no (per company, ir.property) |  | Vendor Location |  |
| `picking_warn` | Selection |  |  | yes | `no-message` No Message, `warning` Warning, `block` Blocking Message; default: `'no-message'` | Stock Picking |  |
| `picking_warn_msg` | Text |  |  | yes |  | Message for Stock Picking |  |

## `res.users` (extension)

Adds fields to `res.users`, defined in another module. Every field below is added by this module.
Source: `res_users.py`.

## `stock.location`

Table `stock_location`.
Description: Inventory Locations.
Order: `complete_name, id`.
Display name field: `complete_name`.
Source: `stock_location.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Location Name |  |
| `complete_name` | Char |  |  | yes |  | Full Location Name | compute `_compute_complete_name` |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `usage` | Selection |  | yes | yes | `supplier` Vendor Location, `view` View, `internal` Internal Location, `customer` Customer Location, `inventory` Inventory Loss, `production` Production, `transit` Transit Location; default: `'internal'` | Location Type |  |
| `location_id` | Many2one | `stock.location` |  | yes |  | Parent Location |  |
| `child_ids` | One2many | `stock.location` (inverse `location_id`) |  | no (inverse) |  | Contains |  |
| `child_internal_location_ids` | Many2many | `stock.location` |  | no |  | Internal locations among descendants | compute `_compute_child_internal_location_ids` |
| `comment` | Html |  |  | yes |  | Additional Information |  |
| `posx` | Integer |  |  | yes | default: `0` | Corridor (X) |  |
| `posy` | Integer |  |  | yes | default: `0` | Shelves (Y) |  |
| `posz` | Integer |  |  | yes | default: `0` | Height (Z) |  |
| `parent_path` | Char |  |  | yes |  |  |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `scrap_location` | Boolean |  |  | yes | default: `False` | Is a Scrap Location? |  |
| `return_location` | Boolean |  |  | yes |  | Is a Return Location? |  |
| `replenish_location` | Boolean |  |  | yes |  | Replenish Location | compute `_compute_replenish_location` |
| `removal_strategy_id` | Many2one | `product.removal` |  | yes |  | Removal Strategy |  |
| `putaway_rule_ids` | One2many | `stock.putaway.rule` (inverse `location_in_id`) |  | no (inverse) |  | Putaway Rules |  |
| `barcode` | Char |  |  | yes |  | Barcode |  |
| `quant_ids` | One2many | `stock.quant` (inverse `location_id`) |  | no (inverse) |  |  |  |
| `cyclic_inventory_frequency` | Integer |  |  | yes | default: `0` | Inventory Frequency (Days) |  |
| `last_inventory_date` | Date |  |  | yes |  | Last Effective Inventory |  |
| `next_inventory_date` | Date |  |  | yes |  | Next Expected Inventory | compute `_compute_next_inventory_date` |
| `warehouse_view_ids` | One2many | `stock.warehouse` (inverse `view_location_id`) |  | no (inverse) |  |  |  |
| `warehouse_id` | Many2one | `stock.warehouse` |  | yes |  |  | compute `_compute_warehouse_id` |
| `storage_category_id` | Many2one | `stock.storage.category` |  | yes |  | Storage Category |  |
| `outgoing_move_line_ids` | One2many | `stock.move.line` (inverse `location_id`) |  | no (inverse) |  |  |  |
| `incoming_move_line_ids` | One2many | `stock.move.line` (inverse `location_dest_id`) |  | no (inverse) |  |  |  |
| `net_weight` | Float |  |  | no |  | Net Weight | compute `_compute_weight` |
| `forecast_weight` | Float |  |  | no |  | Forecasted Weight | compute `_compute_weight` |

SQL constraints:

- `barcode_company_uniq`: `unique (barcode,company_id)`
- `inventory_freq_nonneg`: `check(cyclic_inventory_frequency >= 0)`

## `stock.lot`

Table `stock_lot`.
Description: Lot/Serial.
Inherits: `mail.thread`, `mail.activity.mixin`.
Order: `name, id`.
Source: `stock_lot.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: (computed) | Lot/Serial Number |  |
| `ref` | Char |  |  | yes |  | Internal Reference |  |
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `product_uom_id` | Many2one | `uom.uom` |  | yes |  | Unit of Measure | related `product_id.uom_id` |
| `quant_ids` | One2many | `stock.quant` (inverse `lot_id`) |  | no (inverse) |  | Quants |  |
| `product_qty` | Float |  |  | no |  | On Hand Quantity | compute `_product_qty` |
| `note` | Html |  |  | yes |  | Description |  |
| `display_complete` | Boolean |  |  | no |  |  | compute `_compute_display_complete` |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `delivery_ids` | Many2many | `stock.picking` |  | no |  | Transfers | compute `_compute_delivery_ids` |
| `delivery_count` | Integer |  |  | no |  | Delivery order count | compute `_compute_delivery_ids` |
| `last_delivery_partner_id` | Many2one | `res.partner` |  | no |  |  | compute `_compute_last_delivery_partner_id` |
| `lot_properties` | Properties |  |  | yes |  | Properties |  |
| `location_id` | Many2one | `stock.location` |  | yes |  | Location | compute `_compute_single_location` |

## `stock.move`

Table `stock_move`.
Description: Stock Move.
Order: `sequence, id`.
Source: `stock_move.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Description |  |
| `sequence` | Integer |  |  | yes | default: `10` | Sequence |  |
| `priority` | Selection |  |  | yes | `0` Normal, `1` Urgent; default: `'0'` | Priority | compute `_compute_priority` |
| `date` | Datetime |  | yes | yes | default: (computed) | Date Scheduled |  |
| `date_deadline` | Datetime |  |  | yes |  | Deadline |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `description_picking` | Text |  |  | yes |  | Description of Picking |  |
| `product_qty` | Float |  |  | yes |  | Real Quantity | compute `_compute_product_qty` |
| `product_uom_qty` | Float |  | yes | yes | default: `0` | Demand |  |
| `product_uom` | Many2one | `uom.uom` | yes | yes |  | UoM | compute `_compute_product_uom` |
| `product_uom_category_id` | Many2one | (from related) |  | no |  |  | related `product_id.uom_id.category_id` |
| `product_tmpl_id` | Many2one | `product.template` |  | no |  | Product Template | related `product_id.product_tmpl_id` |
| `location_id` | Many2one | `stock.location` | yes | yes |  | Source Location |  |
| `location_dest_id` | Many2one | `stock.location` | yes | yes |  | Destination Location |  |
| `location_usage` | Selection |  |  | no |  | Source Location Type | related `location_id.usage` |
| `location_dest_usage` | Selection |  |  | no |  | Destination Location Type | related `location_dest_id.usage` |
| `partner_id` | Many2one | `res.partner` |  | yes |  | Destination Address  | compute `_compute_partner_id` |
| `move_dest_ids` | Many2many | `stock.move` (table `stock_move_move_rel`) |  | yes |  | Destination Moves |  |
| `move_orig_ids` | Many2many | `stock.move` (table `stock_move_move_rel`) |  | yes |  | Original Move |  |
| `picking_id` | Many2one | `stock.picking` |  | yes |  | Transfer |  |
| `state` | Selection |  |  | yes | `draft` New, `waiting` Waiting Another Move, `confirmed` Waiting Availability, `partially_available` Partially Available, `assigned` Available, `done` Done, `cancel` Cancelled; default: `'draft'` | Status |  |
| `picked` | Boolean |  |  | yes | default: `False` | Picked | compute `_compute_picked` |
| `price_unit` | Float |  |  | yes |  | Unit Price |  |
| `origin` | Char |  |  | yes |  | Source Document |  |
| `procure_method` | Selection |  | yes | yes | `make_to_stock` Default: Take From Stock, `make_to_order` Advanced: Apply Procurement Rules; default: `'make_to_stock'` | Supply Method |  |
| `scrapped` | Boolean |  |  | yes |  | Scrapped | related `location_dest_id.scrap_location` |
| `scrap_id` | Many2one | `stock.scrap` |  | yes |  | Scrap operation |  |
| `group_id` | Many2one | `procurement.group` |  | yes | default: (computed) | Procurement Group |  |
| `rule_id` | Many2one | `stock.rule` |  | yes |  | Stock Rule |  |
| `propagate_cancel` | Boolean |  |  | yes | default: `True` | Propagate cancel and split |  |
| `delay_alert_date` | Datetime |  |  | yes |  | Delay Alert Date | compute `_compute_delay_alert_date` |
| `picking_type_id` | Many2one | `stock.picking.type` |  | yes |  | Operation Type | compute `_compute_picking_type_id` |
| `is_inventory` | Boolean |  |  | yes |  | Inventory |  |
| `move_line_ids` | One2many | `stock.move.line` (inverse `move_id`) |  | no (inverse) |  |  |  |
| `origin_returned_move_id` | Many2one | `stock.move` |  | yes |  | Origin return move |  |
| `returned_move_ids` | One2many | `stock.move` (inverse `origin_returned_move_id`) |  | no (inverse) |  | All returned moves |  |
| `availability` | Float |  |  | no |  | Forecasted Quantity | compute `_compute_product_availability` |
| `restrict_partner_id` | Many2one | `res.partner` |  | yes |  | Owner  |  |
| `route_ids` | Many2many | `stock.route` (table `stock_route_move`) |  | yes |  | Destination route |  |
| `warehouse_id` | Many2one | `stock.warehouse` |  | yes |  | Warehouse |  |
| `has_tracking` | Selection |  |  | no |  | Product with Tracking | related `product_id.tracking` |
| `quantity` | Float |  |  | yes |  | Quantity | compute `_compute_quantity` |
| `show_operations` | Boolean |  |  | no |  |  | related `picking_id.picking_type_id.show_operations` |
| `picking_code` | Selection |  |  | no |  |  | related `picking_id.picking_type_id.code` |
| `show_details_visible` | Boolean |  |  | no |  | Details Visible | compute `_compute_show_details_visible` |
| `product_type` | Selection |  |  | no |  |  | related `product_id.detailed_type` |
| `additional` | Boolean |  |  | yes | default: `False` | Whether the move was added after the picking's confirmation |  |
| `is_locked` | Boolean |  |  | no |  |  | compute `_compute_is_locked` |
| `is_initial_demand_editable` | Boolean |  |  | no |  | Is initial demand editable | compute `_compute_is_initial_demand_editable` |
| `is_quantity_done_editable` | Boolean |  |  | no |  | Is quantity done editable | compute `_compute_is_quantity_done_editable` |
| `reference` | Char |  |  | yes |  | Reference | compute `_compute_reference` |
| `move_lines_count` | Integer |  |  | no |  |  | compute `_compute_move_lines_count` |
| `package_level_id` | Many2one | `stock.package_level` |  | yes |  | Package Level |  |
| `picking_type_entire_packs` | Boolean |  |  | no |  |  | related `picking_type_id.show_entire_packs` |
| `display_assign_serial` | Boolean |  |  | no |  |  | compute `_compute_display_assign_serial` |
| `display_import_lot` | Boolean |  |  | no |  |  | compute `_compute_display_assign_serial` |
| `next_serial` | Char |  |  | yes |  | First SN |  |
| `next_serial_count` | Integer |  |  | yes |  | Number of SN |  |
| `orderpoint_id` | Many2one | `stock.warehouse.orderpoint` |  | yes |  | Original Reordering Rule |  |
| `forecast_availability` | Float |  |  | no |  | Forecast Availability | compute `_compute_forecast_information` |
| `forecast_expected_date` | Datetime |  |  | no |  | Forecasted Expected date | compute `_compute_forecast_information` |
| `lot_ids` | Many2many | `stock.lot` |  | no |  | Serial Numbers | compute `_compute_lot_ids` |
| `reservation_date` | Date |  |  | yes |  | Date to Reserve | compute `_compute_reservation_date` |
| `product_packaging_id` | Many2one | `product.packaging` |  | yes |  | Packaging |  |
| `product_packaging_qty` | Float |  |  | no |  | Reserved Packaging Quantity | compute `_compute_product_packaging_qty` |
| `product_packaging_quantity` | Float |  |  | no |  | Done Packaging Quantity | compute `_compute_product_packaging_quantity` |
| `show_reserved` | Boolean |  |  | no |  |  | compute `_compute_show_reserved` |
| `show_quant` | Boolean |  |  | no |  | Show Quant | compute `_compute_show_info` |
| `show_lots_m2o` | Boolean |  |  | no |  | Show lot_id | compute `_compute_show_info` |
| `show_lots_text` | Boolean |  |  | no |  | Show lot_name | compute `_compute_show_info` |

## `stock.move.line`

Table `stock_move_line`.
Description: Product Moves (Stock Move Line).
Order: `result_package_id desc, id`.
Display name field: `product_id`.
Source: `stock_move_line.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `picking_id` | Many2one | `stock.picking` |  | yes |  | Transfer |  |
| `move_id` | Many2one | `stock.move` |  | yes |  | Stock Operation |  |
| `company_id` | Many2one | `res.company` | yes | yes |  | Company |  |
| `product_id` | Many2one | `product.product` |  | yes |  | Product |  |
| `product_uom_id` | Many2one | `uom.uom` | yes | yes |  | Unit of Measure | compute `_compute_product_uom_id` |
| `product_uom_category_id` | Many2one | (from related) |  | no |  |  | related `product_id.uom_id.category_id` |
| `product_category_name` | Char |  |  | yes |  | Product Category | related `product_id.categ_id.complete_name` |
| `quantity` | Float |  |  | yes |  | Quantity | compute `_compute_quantity` |
| `quantity_product_uom` | Float |  |  | yes |  | Quantity in Product UoM | compute `_compute_quantity_product_uom` |
| `picked` | Boolean |  |  | yes |  | Picked | compute `_compute_picked` |
| `package_id` | Many2one | `stock.quant.package` |  | yes |  | Source Package |  |
| `package_level_id` | Many2one | `stock.package_level` |  | yes |  | Package Level |  |
| `lot_id` | Many2one | `stock.lot` |  | yes |  | Lot/Serial Number |  |
| `lot_name` | Char |  |  | yes |  | Lot/Serial Number Name |  |
| `result_package_id` | Many2one | `stock.quant.package` |  | yes |  | Destination Package |  |
| `date` | Datetime |  | yes | yes | default: (computed) | Date |  |
| `owner_id` | Many2one | `res.partner` |  | yes |  | From Owner |  |
| `location_id` | Many2one | `stock.location` | yes | yes |  | From | compute `_compute_location_id` |
| `location_dest_id` | Many2one | `stock.location` | yes | yes |  | To | compute `_compute_location_id` |
| `location_usage` | Selection |  |  | no |  | Source Location Type | related `location_id.usage` |
| `location_dest_usage` | Selection |  |  | no |  | Destination Location Type | related `location_dest_id.usage` |
| `lots_visible` | Boolean |  |  | no |  |  | compute `_compute_lots_visible` |
| `picking_partner_id` | Many2one | (from related) |  | no |  |  | related `picking_id.partner_id` |
| `picking_code` | Selection |  |  | no |  |  | related `picking_type_id.code` |
| `picking_type_id` | Many2one | `stock.picking.type` |  | no |  | Operation type | compute `_compute_picking_type_id` |
| `picking_type_use_create_lots` | Boolean |  |  | no |  |  | related `picking_type_id.use_create_lots` |
| `picking_type_use_existing_lots` | Boolean |  |  | no |  |  | related `picking_type_id.use_existing_lots` |
| `picking_type_entire_packs` | Boolean |  |  | no |  |  | related `picking_id.picking_type_id.show_entire_packs` |
| `state` | Selection |  |  | yes |  |  | related `move_id.state` |
| `is_inventory` | Boolean |  |  | no |  |  | related `move_id.is_inventory` |
| `is_locked` | Boolean |  |  | no |  |  | related `move_id.is_locked` |
| `consume_line_ids` | Many2many | `stock.move.line` (table `stock_move_line_consume_rel`) |  | yes |  |  |  |
| `produce_line_ids` | Many2many | `stock.move.line` (table `stock_move_line_consume_rel`) |  | yes |  |  |  |
| `reference` | Char |  |  | yes |  |  | related `move_id.reference` |
| `tracking` | Selection |  |  | no |  |  | related `product_id.tracking` |
| `origin` | Char |  |  | no |  | Source | related `move_id.origin` |
| `description_picking` | Text |  |  | yes |  | Description picking |  |
| `quant_id` | Many2one | `stock.quant` |  | no |  | Pick From |  |
| `product_packaging_qty` | Float |  |  | no |  | Reserved Packaging Quantity | compute `_compute_product_packaging_qty` |
| `picking_location_id` | Many2one | (from related) |  | no |  |  | related `picking_id.location_id` |
| `picking_location_dest_id` | Many2one | (from related) |  | no |  |  | related `picking_id.location_dest_id` |

## `stock.package.type`

Table `stock_package_type`.
Description: Stock package type.
Order: `sequence, id`.
Source: `stock_package_type.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Package Type |  |
| `sequence` | Integer |  |  | yes | default: `1` | Sequence |  |
| `height` | Float |  |  | yes |  | Height |  |
| `width` | Float |  |  | yes |  | Width |  |
| `packaging_length` | Float |  |  | yes |  | Length |  |
| `base_weight` | Float |  |  | yes |  | Weight |  |
| `max_weight` | Float |  |  | yes |  | Max Weight |  |
| `barcode` | Char |  |  | yes |  | Barcode |  |
| `weight_uom_name` | Char |  |  | no | default: (computed) | Weight unit of measure label | compute `_compute_weight_uom_name` |
| `length_uom_name` | Char |  |  | no | default: (computed) | Length unit of measure label | compute `_compute_length_uom_name` |
| `company_id` | Many2one | `res.company` |  | yes |  | Company |  |
| `storage_category_capacity_ids` | One2many | `stock.storage.category.capacity` (inverse `package_type_id`) |  | no (inverse) |  | Storage Category Capacity |  |

SQL constraints:

- `barcode_uniq`: `unique(barcode)`
- `positive_height`: `CHECK(height>=0.0)`
- `positive_width`: `CHECK(width>=0.0)`
- `positive_length`: `CHECK(packaging_length>=0.0)`
- `positive_max_weight`: `CHECK(max_weight>=0.0)`

## `stock.package_level`

Table `stock_package_level`.
Description: Stock Package Level.
Source: `stock_package_level.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `package_id` | Many2one | `stock.quant.package` | yes | yes |  | Package |  |
| `picking_id` | Many2one | `stock.picking` |  | yes |  | Picking |  |
| `move_ids` | One2many | `stock.move` (inverse `package_level_id`) |  | no (inverse) |  |  |  |
| `move_line_ids` | One2many | `stock.move.line` (inverse `package_level_id`) |  | no (inverse) |  |  |  |
| `location_id` | Many2one | `stock.location` |  | no |  | From | compute `_compute_location_id` |
| `location_dest_id` | Many2one | `stock.location` |  | yes |  | To | compute `_compute_location_dest_id` |
| `is_done` | Boolean |  |  | no |  | Done | compute `_compute_is_done` |
| `state` | Selection |  |  | no | `draft` Draft, `confirmed` Confirmed, `assigned` Reserved, `new` New, `done` Done, `cancel` Cancelled | State | compute `_compute_state` |
| `is_fresh_package` | Boolean |  |  | no |  |  | compute `_compute_fresh_pack` |
| `picking_type_code` | Selection |  |  | no |  |  | related `picking_id.picking_type_code` |
| `show_lots_m2o` | Boolean |  |  | no |  |  | compute `_compute_show_lot` |
| `show_lots_text` | Boolean |  |  | no |  |  | compute `_compute_show_lot` |
| `company_id` | Many2one | `res.company` | yes | yes |  | Company |  |

## `stock.picking`

Table `stock_picking`.
Description: Transfer.
Inherits: `mail.thread`, `mail.activity.mixin`.
Order: `priority desc, scheduled_date asc, id desc`.
Source: `stock_picking.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes | default: `'/'` | Reference |  |
| `origin` | Char |  |  | yes |  | Source Document |  |
| `note` | Html |  |  | yes |  | Notes |  |
| `backorder_id` | Many2one | `stock.picking` |  | yes |  | Back Order of |  |
| `backorder_ids` | One2many | `stock.picking` (inverse `backorder_id`) |  | no (inverse) |  | Back Orders |  |
| `return_id` | Many2one | `stock.picking` |  | yes |  | Return of |  |
| `return_ids` | One2many | `stock.picking` (inverse `return_id`) |  | no (inverse) |  | Returns |  |
| `return_count` | Integer |  |  | no |  | # Returns | compute `_compute_return_count` |
| `move_type` | Selection |  | yes | yes | `direct` As soon as possible, `one` When all products are ready; default: `'direct'` | Shipping Policy |  |
| `state` | Selection |  |  | yes | `draft` Draft, `waiting` Waiting Another Operation, `confirmed` Waiting, `assigned` Ready, `done` Done, `cancel` Cancelled | Status | compute `_compute_state` |
| `group_id` | Many2one | `procurement.group` |  | yes |  | Procurement Group | related `move_ids.group_id` |
| `priority` | Selection |  |  | yes | `0` Normal, `1` Urgent; default: `'0'` | Priority |  |
| `scheduled_date` | Datetime |  |  | yes | default: (computed) | Scheduled Date | compute `_compute_scheduled_date` |
| `date_deadline` | Datetime |  |  | yes |  | Deadline | compute `_compute_date_deadline` |
| `has_deadline_issue` | Boolean |  |  | yes | default: `False` | Is late | compute `_compute_has_deadline_issue` |
| `date` | Datetime |  |  | yes | default: (computed) | Creation Date |  |
| `date_done` | Datetime |  |  | yes |  | Date of Transfer |  |
| `delay_alert_date` | Datetime |  |  | no |  | Delay Alert Date | compute `_compute_delay_alert_date` |
| `json_popover` | Char |  |  | no |  | JSON data for the popover widget | compute `_compute_json_popover` |
| `location_id` | Many2one | `stock.location` | yes | yes |  | Source Location | compute `_compute_location_id` |
| `location_dest_id` | Many2one | `stock.location` | yes | yes |  | Destination Location | compute `_compute_location_id` |
| `move_ids` | One2many | `stock.move` (inverse `picking_id`) |  | no (inverse) |  | Stock Moves |  |
| `move_ids_without_package` | One2many | `stock.move` (inverse `picking_id`) |  | no (inverse) |  | Stock move |  |
| `has_scrap_move` | Boolean |  |  | no |  | Has Scrap Moves | compute `_has_scrap_move` |
| `picking_type_id` | Many2one | `stock.picking.type` | yes | yes | default: (computed) | Operation Type |  |
| `picking_type_code` | Selection |  |  | no |  |  | related `picking_type_id.code` |
| `picking_type_entire_packs` | Boolean |  |  | no |  |  | related `picking_type_id.show_entire_packs` |
| `use_create_lots` | Boolean |  |  | no |  |  | related `picking_type_id.use_create_lots` |
| `use_existing_lots` | Boolean |  |  | no |  |  | related `picking_type_id.use_existing_lots` |
| `hide_picking_type` | Boolean |  |  | no |  |  | compute `_compute_hide_picking_type` |
| `partner_id` | Many2one | `res.partner` |  | yes |  | Contact |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | related `picking_type_id.company_id` |
| `user_id` | Many2one | `res.users` |  | yes | default: (computed) | Responsible |  |
| `move_line_ids` | One2many | `stock.move.line` (inverse `picking_id`) |  | no (inverse) |  | Operations |  |
| `move_line_ids_without_package` | One2many | `stock.move.line` (inverse `picking_id`) |  | no (inverse) |  | Operations without package |  |
| `move_line_exist` | Boolean |  |  | no |  | Has Pack Operations | compute `_compute_move_line_exist` |
| `has_packages` | Boolean |  |  | no |  | Has Packages | compute `_compute_has_packages` |
| `show_check_availability` | Boolean |  |  | no |  |  | compute `_compute_show_check_availability` |
| `show_allocation` | Boolean |  |  | no |  |  | compute `_compute_show_allocation` |
| `owner_id` | Many2one | `res.partner` |  | yes |  | Assign Owner |  |
| `printed` | Boolean |  |  | yes |  | Printed |  |
| `signature` | Image |  |  | yes |  | Signature |  |
| `is_signed` | Boolean |  |  | no |  | Is Signed | compute `_compute_is_signed` |
| `is_locked` | Boolean |  |  | yes | default: `True` |  |  |
| `product_id` | Many2one | `product.product` |  | no |  | Product | related `move_ids.product_id` |
| `lot_id` | Many2one | `stock.lot` |  | no |  | Lot/Serial Number | related `move_line_ids.lot_id` |
| `show_operations` | Boolean |  |  | no |  |  | related `picking_type_id.show_operations` |
| `show_reserved` | Boolean |  |  | no |  |  | related `picking_type_id.show_reserved` |
| `show_lots_text` | Boolean |  |  | no |  |  | compute `_compute_show_lots_text` |
| `has_tracking` | Boolean |  |  | no |  |  | compute `_compute_has_tracking` |
| `package_level_ids` | One2many | `stock.package_level` (inverse `picking_id`) |  | no (inverse) |  |  |  |
| `package_level_ids_details` | One2many | `stock.package_level` (inverse `picking_id`) |  | no (inverse) |  |  |  |
| `products_availability` | Char |  |  | no |  | Product Availability | compute `_compute_products_availability` |
| `products_availability_state` | Selection |  |  | no | `available` Available, `expected` Expected, `late` Late |  | compute `_compute_products_availability` |
| `show_set_qty_button` | Boolean |  |  | no |  |  | compute `_compute_show_qty_button` |
| `show_clear_qty_button` | Boolean |  |  | no |  |  | compute `_compute_show_qty_button` |
| `picking_properties` | Properties |  |  | yes |  | Properties |  |

SQL constraints:

- `name_uniq`: `unique(name, company_id)`

## `stock.picking.type`

Table `stock_picking_type`.
Description: Picking Type.
Order: `sequence, id`.
Source: `stock_picking.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Operation Type |  |
| `color` | Integer |  |  | yes |  | Color |  |
| `sequence` | Integer |  |  | yes |  | Sequence |  |
| `sequence_id` | Many2one | `ir.sequence` |  | yes |  | Reference Sequence |  |
| `sequence_code` | Char |  | yes | yes |  | Sequence Prefix |  |
| `default_location_src_id` | Many2one | `stock.location` |  | yes |  | Default Source Location | compute `_compute_default_location_src_id` |
| `default_location_dest_id` | Many2one | `stock.location` |  | yes |  | Default Destination Location | compute `_compute_default_location_dest_id` |
| `default_location_return_id` | Many2one | `stock.location` |  | yes |  | Default returns location |  |
| `code` | Selection |  | yes | yes | `incoming` Receipt, `outgoing` Delivery, `internal` Internal Transfer; default: `'incoming'` | Type of Operation |  |
| `return_picking_type_id` | Many2one | `stock.picking.type` |  | yes |  | Operation Type for Returns |  |
| `show_entire_packs` | Boolean |  |  | yes |  | Move Entire Packages |  |
| `warehouse_id` | Many2one | `stock.warehouse` |  | yes |  | Warehouse | compute `_compute_warehouse_id` |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `use_create_lots` | Boolean |  |  | yes | default: `True` | Create New Lots/Serial Numbers | compute `_compute_use_create_lots` |
| `use_existing_lots` | Boolean |  |  | yes | default: `True` | Use Existing Lots/Serial Numbers | compute `_compute_use_existing_lots` |
| `print_label` | Boolean |  |  | yes |  | Print Label | compute `_compute_print_label` |
| `show_operations` | Boolean |  |  | yes | default: `False` | Show Detailed Operations |  |
| `show_reserved` | Boolean |  |  | yes | default: `True` | Pre-fill Detailed Operations | compute `_compute_show_reserved` |
| `reservation_method` | Selection |  | yes | yes | `at_confirm` At Confirmation, `manual` Manually, `by_date` Before scheduled date; default: `'at_confirm'` | Reservation Method |  |
| `reservation_days_before` | Integer |  |  | yes |  | Days |  |
| `reservation_days_before_priority` | Integer |  |  | yes |  | Days when starred |  |
| `auto_show_reception_report` | Boolean |  |  | yes |  | Show Reception Report at Validation |  |
| `auto_print_delivery_slip` | Boolean |  |  | yes |  | Auto Print Delivery Slip |  |
| `auto_print_return_slip` | Boolean |  |  | yes |  | Auto Print Return Slip |  |
| `auto_print_product_labels` | Boolean |  |  | yes |  | Auto Print Product Labels |  |
| `product_label_format` | Selection |  |  | yes | `dymo` Dymo, `2x7xprice` 2 x 7 with price, `4x7xprice` 4 x 7 with price, `4x12` 4 x 12, `4x12xprice` 4 x 12 with price, `zpl` ZPL Labels, `zplxprice` ZPL Labels with price; default: `'2x7xprice'` | Product Label Format to auto-print |  |
| `auto_print_lot_labels` | Boolean |  |  | yes |  | Auto Print Lot/SN Labels |  |
| `lot_label_format` | Selection |  |  | yes | `4x12_lots` 4 x 12 - One per lot/SN, `4x12_units` 4 x 12 - One per unit, `zpl_lots` ZPL Labels - One per lot/SN, `zpl_units` ZPL Labels - One per unit; default: `'4x12_lots'` | Lot Label Format to auto-print |  |
| `auto_print_reception_report` | Boolean |  |  | yes |  | Auto Print Reception Report |  |
| `auto_print_reception_report_labels` | Boolean |  |  | yes |  | Auto Print Reception Report Labels |  |
| `auto_print_packages` | Boolean |  |  | yes |  | Auto Print Packages |  |
| `auto_print_package_label` | Boolean |  |  | yes |  | Auto Print Package Label |  |
| `package_label_to_print` | Selection |  |  | yes | `pdf` PDF, `zpl` ZPL; default: `'pdf'` | Package Label to Print |  |
| `count_picking_draft` | Integer |  |  | no |  |  | compute `_compute_picking_count` |
| `count_picking_ready` | Integer |  |  | no |  |  | compute `_compute_picking_count` |
| `count_picking` | Integer |  |  | no |  |  | compute `_compute_picking_count` |
| `count_picking_waiting` | Integer |  |  | no |  |  | compute `_compute_picking_count` |
| `count_picking_late` | Integer |  |  | no |  |  | compute `_compute_picking_count` |
| `count_picking_backorders` | Integer |  |  | no |  |  | compute `_compute_picking_count` |
| `hide_reservation_method` | Boolean |  |  | no |  |  | compute `_compute_hide_reservation_method` |
| `barcode` | Char |  |  | yes |  | Barcode |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `create_backorder` | Selection |  | yes | yes | `ask` Ask, `always` Always, `never` Never; default: `'ask'` | Create Backorder |  |
| `show_picking_type` | Boolean |  |  | no |  |  | compute `_compute_show_picking_type` |
| `picking_properties_definition` | PropertiesDefinition |  |  | yes |  | Picking Properties |  |

## `stock.putaway.rule`

Table `stock_putaway_rule`.
Description: Putaway Rule.
Order: `sequence,product_id`.
Source: `product_strategy.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `product_id` | Many2one | `product.product` |  | yes | default: (computed) | Product |  |
| `category_id` | Many2one | `product.category` |  | yes | default: (computed) | Product Category |  |
| `location_in_id` | Many2one | `stock.location` | yes | yes | default: (computed) | When product arrives in |  |
| `location_out_id` | Many2one | `stock.location` | yes | yes |  | Store to sublocation |  |
| `sequence` | Integer |  |  | yes |  | Priority |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `package_type_ids` | Many2many | `stock.package.type` |  | yes |  | Package Type |  |
| `storage_category_id` | Many2one | `stock.storage.category` |  | yes |  | Storage Category |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |

## `stock.quant`

Table `stock_quant`.
Description: Quants.
Display name field: `product_id`.
Source: `stock_quant.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `product_tmpl_id` | Many2one | `product.template` |  | no |  | Product Template | related `product_id.product_tmpl_id` |
| `product_uom_id` | Many2one | `uom.uom` |  | no |  | Unit of Measure | related `product_id.uom_id` |
| `priority` | Selection |  |  | no |  |  | related `product_tmpl_id.priority` |
| `company_id` | Many2one | (from related) |  | yes |  | Company | related `location_id.company_id` |
| `location_id` | Many2one | `stock.location` | yes | yes |  | Location |  |
| `warehouse_id` | Many2one | `stock.warehouse` |  | no |  |  | related `location_id.warehouse_id` |
| `storage_category_id` | Many2one | (from related) |  | yes |  |  | related `location_id.storage_category_id` |
| `cyclic_inventory_frequency` | Integer |  |  | no |  |  | related `location_id.cyclic_inventory_frequency` |
| `lot_id` | Many2one | `stock.lot` |  | yes |  | Lot/Serial Number |  |
| `lot_properties` | Properties |  |  | no |  |  | related `lot_id.lot_properties` |
| `sn_duplicated` | Boolean |  |  | no |  | Duplicated Serial Number | compute `_compute_sn_duplicated` |
| `package_id` | Many2one | `stock.quant.package` |  | yes |  | Package |  |
| `owner_id` | Many2one | `res.partner` |  | yes |  | Owner |  |
| `quantity` | Float |  |  | yes |  | Quantity |  |
| `reserved_quantity` | Float |  | yes | yes | default: `0.0` | Reserved Quantity |  |
| `available_quantity` | Float |  |  | no |  | Available Quantity | compute `_compute_available_quantity` |
| `in_date` | Datetime |  | yes | yes | default: (computed) | Incoming Date |  |
| `tracking` | Selection |  |  | no |  |  | related `product_id.tracking` |
| `on_hand` | Boolean |  |  | no |  | On Hand |  |
| `product_categ_id` | Many2one | (from related) |  | no |  |  | related `product_tmpl_id.categ_id` |
| `inventory_quantity` | Float |  |  | yes |  | Counted Quantity |  |
| `inventory_quantity_auto_apply` | Float |  |  | no |  | Inventoried Quantity | compute `_compute_inventory_quantity_auto_apply` |
| `inventory_diff_quantity` | Float |  |  | yes |  | Difference | compute `_compute_inventory_diff_quantity` |
| `inventory_date` | Date |  |  | yes |  | Scheduled Date | compute `_compute_inventory_date` |
| `last_count_date` | Date |  |  | no |  |  | compute `_compute_last_count_date` |
| `inventory_quantity_set` | Boolean |  |  | yes | default: `False` |  | compute `_compute_inventory_quantity_set` |
| `is_outdated` | Boolean |  |  | no |  | Quantity has been moved since last count | compute `_compute_is_outdated` |
| `user_id` | Many2one | `res.users` |  | yes |  | Assigned To |  |

## `stock.quant.package`

Table `stock_quant_package`.
Description: Packages.
Order: `name`.
Source: `stock_quant.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: (computed) | Package Reference |  |
| `quant_ids` | One2many | `stock.quant` (inverse `package_id`) |  | no (inverse) |  | Bulk Content |  |
| `package_type_id` | Many2one | `stock.package.type` |  | yes |  | Package Type |  |
| `location_id` | Many2one | `stock.location` |  | yes |  | Location | compute `_compute_package_info` |
| `company_id` | Many2one | `res.company` |  | yes |  | Company | compute `_compute_package_info` |
| `owner_id` | Many2one | `res.partner` |  | no |  | Owner | compute `_compute_owner_id` |
| `package_use` | Selection |  | yes | yes | `disposable` Disposable Box, `reusable` Reusable Box; default: `'disposable'` | Package Use |  |
| `valid_sscc` | Boolean |  |  | no |  | Package name is valid SSCC | compute `_compute_valid_sscc` |
| `pack_date` | Date |  |  | yes | default: (computed) | Pack Date |  |

## `stock.route`

Table `stock_route`.
Description: Inventory Routes.
Order: `sequence`.
Source: `stock_location.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Route |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `sequence` | Integer |  |  | yes | default: `0` | Sequence |  |
| `rule_ids` | One2many | `stock.rule` (inverse `route_id`) |  | no (inverse) |  | Rules |  |
| `product_selectable` | Boolean |  |  | yes | default: `True` | Applicable on Product |  |
| `product_categ_selectable` | Boolean |  |  | yes |  | Applicable on Product Category |  |
| `warehouse_selectable` | Boolean |  |  | yes |  | Applicable on Warehouse |  |
| `packaging_selectable` | Boolean |  |  | yes |  | Applicable on Packaging |  |
| `supplied_wh_id` | Many2one | `stock.warehouse` |  | yes |  | Supplied Warehouse |  |
| `supplier_wh_id` | Many2one | `stock.warehouse` |  | yes |  | Supplying Warehouse |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `product_ids` | Many2many | `product.template` (table `stock_route_product`) |  | yes |  | Products |  |
| `categ_ids` | Many2many | `product.category` (table `stock_route_categ`) |  | yes |  | Product Categories |  |
| `packaging_ids` | Many2many | `product.packaging` (table `stock_route_packaging`) |  | yes |  | Packagings |  |
| `warehouse_domain_ids` | One2many | `stock.warehouse` |  | no (inverse) |  |  | compute `_compute_warehouses` |
| `warehouse_ids` | Many2many | `stock.warehouse` (table `stock_route_warehouse`) |  | yes |  | Warehouses |  |

## `stock.rule`

Table `stock_rule`.
Description: Stock Rule.
Order: `sequence, id`.
Source: `stock_rule.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Name |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `group_propagation_option` | Selection |  |  | yes | `none` Leave Empty, `propagate` Propagate, `fixed` Fixed; default: `'propagate'` | Propagation of Procurement Group |  |
| `group_id` | Many2one | `procurement.group` |  | yes |  | Fixed Procurement Group |  |
| `action` | Selection |  | yes | yes | `pull` Pull From, `push` Push To, `pull_push` Pull & Push; default: `'pull'` | Action |  |
| `sequence` | Integer |  |  | yes | default: `20` | Sequence |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `location_dest_id` | Many2one | `stock.location` | yes | yes |  | Destination Location |  |
| `location_src_id` | Many2one | `stock.location` |  | yes |  | Source Location |  |
| `route_id` | Many2one | `stock.route` | yes | yes |  | Route |  |
| `route_company_id` | Many2one | (from related) |  | no |  | Route Company | related `route_id.company_id` |
| `procure_method` | Selection |  | yes | yes | `make_to_stock` Take From Stock, `make_to_order` Trigger Another Rule, `mts_else_mto` Take From Stock, if unavailable, Trigger Another Rule; default: `'make_to_stock'` | Supply Method |  |
| `route_sequence` | Integer |  |  | yes |  | Route Sequence | related `route_id.sequence` |
| `picking_type_id` | Many2one | `stock.picking.type` | yes | yes |  | Operation Type |  |
| `picking_type_code_domain` | Char |  |  | no |  |  | compute `_compute_picking_type_code_domain` |
| `delay` | Integer |  |  | yes | default: `0` | Lead Time |  |
| `partner_address_id` | Many2one | `res.partner` |  | yes |  | Partner Address |  |
| `propagate_cancel` | Boolean |  |  | yes | default: `False` | Cancel Next Move |  |
| `propagate_carrier` | Boolean |  |  | yes | default: `False` | Propagation of carrier |  |
| `warehouse_id` | Many2one | `stock.warehouse` |  | yes |  | Warehouse |  |
| `propagate_warehouse_id` | Many2one | `stock.warehouse` |  | yes |  | Warehouse to Propagate |  |
| `auto` | Selection |  | yes | yes | `manual` Manual Operation, `transparent` Automatic No Step Added; default: `'manual'` | Automatic Move |  |
| `rule_message` | Html |  |  | no |  |  | compute `_compute_action_message` |

## `stock.scrap`

Table `stock_scrap`.
Description: Scrap.
Inherits: `mail.thread`.
Order: `id desc`.
Source: `stock_scrap.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: (computed) | Reference |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `origin` | Char |  |  | yes |  | Source Document |  |
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `product_uom_id` | Many2one | `uom.uom` | yes | yes |  | Unit of Measure | compute `_compute_product_uom_id` |
| `product_uom_category_id` | Many2one | (from related) |  | no |  |  | related `product_id.uom_id.category_id` |
| `tracking` | Selection |  |  | no |  | Product Tracking | related `product_id.tracking` |
| `lot_id` | Many2one | `stock.lot` |  | yes |  | Lot/Serial |  |
| `package_id` | Many2one | `stock.quant.package` |  | yes |  | Package |  |
| `owner_id` | Many2one | `res.partner` |  | yes |  | Owner |  |
| `move_ids` | One2many | `stock.move` (inverse `scrap_id`) |  | no (inverse) |  |  |  |
| `picking_id` | Many2one | `stock.picking` |  | yes |  | Picking |  |
| `location_id` | Many2one | `stock.location` | yes | yes |  | Source Location | compute `_compute_location_id` |
| `scrap_location_id` | Many2one | `stock.location` | yes | yes |  | Scrap Location | compute `_compute_scrap_location_id` |
| `scrap_qty` | Float |  | yes | yes | default: `1.0` | Quantity | compute `_compute_scrap_qty` |
| `state` | Selection |  |  | yes | `draft` Draft, `done` Done; default: `'draft'` | Status |  |
| `date_done` | Datetime |  |  | yes |  | Date |  |
| `should_replenish` | Boolean |  |  | yes |  | Replenish Quantities |  |

## `stock.storage.category`

Table `stock_storage_category`.
Description: Storage Category.
Order: `name`.
Source: `stock_storage_category.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Storage Category |  |
| `max_weight` | Float |  |  | yes |  | Max Weight |  |
| `capacity_ids` | One2many | `stock.storage.category.capacity` (inverse `storage_category_id`) |  | no (inverse) |  |  |  |
| `product_capacity_ids` | One2many | `stock.storage.category.capacity` |  | no (inverse) |  |  | compute `_compute_storage_capacity_ids` |
| `package_capacity_ids` | One2many | `stock.storage.category.capacity` |  | no (inverse) |  |  | compute `_compute_storage_capacity_ids` |
| `allow_new_product` | Selection |  | yes | yes | `empty` If the location is empty, `same` If all products are same, `mixed` Allow mixed products; default: `'mixed'` |  |  |
| `location_ids` | One2many | `stock.location` (inverse `storage_category_id`) |  | no (inverse) |  |  |  |
| `company_id` | Many2one | `res.company` |  | yes |  | Company |  |
| `weight_uom_name` | Char |  |  | no |  | Weight unit | compute `_compute_weight_uom_name` |

SQL constraints:

- `positive_max_weight`: `CHECK(max_weight >= 0)`

## `stock.storage.category.capacity`

Table `stock_storage_category_capacity`.
Description: Storage Category Capacity.
Order: `storage_category_id`.
Source: `stock_storage_category.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `storage_category_id` | Many2one | `stock.storage.category` | yes | yes |  |  |  |
| `product_id` | Many2one | `product.product` |  | yes |  | Product |  |
| `package_type_id` | Many2one | `stock.package.type` |  | yes |  | Package Type |  |
| `quantity` | Float |  | yes | yes |  | Quantity |  |
| `product_uom_id` | Many2one | (from related) |  | no |  |  | related `product_id.uom_id` |
| `company_id` | Many2one | `res.company` |  | no |  | Company | related `storage_category_id.company_id` |

SQL constraints:

- `positive_quantity`: `CHECK(quantity > 0)`
- `unique_product`: `UNIQUE(product_id, storage_category_id)`
- `unique_package_type`: `UNIQUE(package_type_id, storage_category_id)`

## `stock.warehouse`

Table `stock_warehouse`.
Description: Warehouse.
Order: `sequence,id`.
Source: `stock_warehouse.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: (computed) | Warehouse |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `partner_id` | Many2one | `res.partner` |  | yes | default: (computed) | Address |  |
| `view_location_id` | Many2one | `stock.location` | yes | yes |  | View Location |  |
| `lot_stock_id` | Many2one | `stock.location` | yes | yes |  | Location Stock |  |
| `code` | Char |  | yes | yes |  | Short Name |  |
| `route_ids` | Many2many | `stock.route` (table `stock_route_warehouse`) |  | yes |  | Routes |  |
| `reception_steps` | Selection |  | yes | yes | `one_step` Receive goods directly (1 step), `two_steps` Receive goods in input and then stock (2 steps), `three_steps` Receive goods in input, then quality and then stock (3 steps); default: `'one_step'` | Incoming Shipments |  |
| `delivery_steps` | Selection |  | yes | yes | `ship_only` Deliver goods directly (1 step), `pick_ship` Send goods in output and then deliver (2 steps), `pick_pack_ship` Pack goods, send goods in output and then deliver (3 steps); default: `'ship_only'` | Outgoing Shipments |  |
| `wh_input_stock_loc_id` | Many2one | `stock.location` |  | yes |  | Input Location |  |
| `wh_qc_stock_loc_id` | Many2one | `stock.location` |  | yes |  | Quality Control Location |  |
| `wh_output_stock_loc_id` | Many2one | `stock.location` |  | yes |  | Output Location |  |
| `wh_pack_stock_loc_id` | Many2one | `stock.location` |  | yes |  | Packing Location |  |
| `mto_pull_id` | Many2one | `stock.rule` |  | yes |  | MTO rule |  |
| `pick_type_id` | Many2one | `stock.picking.type` |  | yes |  | Pick Type |  |
| `pack_type_id` | Many2one | `stock.picking.type` |  | yes |  | Pack Type |  |
| `out_type_id` | Many2one | `stock.picking.type` |  | yes |  | Out Type |  |
| `in_type_id` | Many2one | `stock.picking.type` |  | yes |  | In Type |  |
| `int_type_id` | Many2one | `stock.picking.type` |  | yes |  | Internal Type |  |
| `crossdock_route_id` | Many2one | `stock.route` |  | yes |  | Crossdock Route |  |
| `reception_route_id` | Many2one | `stock.route` |  | yes |  | Receipt Route |  |
| `delivery_route_id` | Many2one | `stock.route` |  | yes |  | Delivery Route |  |
| `resupply_wh_ids` | Many2many | `stock.warehouse` (table `stock_wh_resupply_table`) |  | yes |  | Resupply From |  |
| `resupply_route_ids` | One2many | `stock.route` (inverse `supplied_wh_id`) |  | no (inverse) |  | Resupply Routes |  |
| `sequence` | Integer |  |  | yes | default: `10` |  |  |

SQL constraints:

- `warehouse_name_uniq`: `unique(name, company_id)`
- `warehouse_code_uniq`: `unique(code, company_id)`

## `stock.warehouse.orderpoint`

Table `stock_warehouse_orderpoint`.
Description: Minimum Inventory Rule.
Order: `location_id,company_id,id`.
Source: `stock_orderpoint.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes | default: (computed) | Name |  |
| `trigger` | Selection |  | yes | yes | `auto` Auto, `manual` Manual; default: `'auto'` | Trigger |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `snoozed_until` | Date |  |  | yes |  | Snoozed |  |
| `warehouse_id` | Many2one | `stock.warehouse` | yes | yes |  | Warehouse | compute `_compute_warehouse_id` |
| `location_id` | Many2one | `stock.location` | yes | yes |  | Location | compute `_compute_location_id` |
| `product_tmpl_id` | Many2one | `product.template` |  | no |  |  | related `product_id.product_tmpl_id` |
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `product_category_id` | Many2one | `product.category` |  | yes |  |  | related `product_id.categ_id` |
| `product_uom` | Many2one | `uom.uom` |  | no |  | Unit of Measure | related `product_id.uom_id` |
| `product_uom_name` | Char |  |  | no |  | Product unit of measure label | related `product_uom.display_name` |
| `product_min_qty` | Float |  | yes | yes | default: `0.0` | Min Quantity |  |
| `product_max_qty` | Float |  | yes | yes | default: `0.0` | Max Quantity |  |
| `qty_multiple` | Float |  | yes | yes | default: `1` | Multiple Quantity |  |
| `group_id` | Many2one | `procurement.group` |  | yes |  | Procurement Group |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `allowed_location_ids` | One2many | `stock.location` |  | no (inverse) |  |  | compute `_compute_allowed_location_ids` |
| `rule_ids` | Many2many | `stock.rule` |  | no |  | Rules used | compute `_compute_rules` |
| `lead_days_date` | Date |  |  | no |  |  | compute `_compute_lead_days` |
| `route_id` | Many2one | `stock.route` |  | yes |  | Route |  |
| `qty_on_hand` | Float |  |  | no |  | On Hand | compute `_compute_qty` |
| `qty_forecast` | Float |  |  | no |  | Forecast | compute `_compute_qty` |
| `qty_to_order` | Float |  |  | yes |  | To Order | compute `_compute_qty_to_order` |
| `days_to_order` | Float |  |  | no |  |  | compute `_compute_days_to_order` |
| `visibility_days` | Float |  |  | no |  |  | compute `_compute_visibility_days` |
| `unwanted_replenish` | Boolean |  |  | no |  | Unwanted Replenish | compute `_compute_unwanted_replenish` |

SQL constraints:

- `qty_multiple_check`: `CHECK( qty_multiple >= 0 )`
- `product_location_check`: `unique (product_id, location_id, company_id)`

## `uom.uom` (extension)

Adds fields to `uom.uom`, defined in another module. Every field below is added by this module.
Source: `product.py`.
