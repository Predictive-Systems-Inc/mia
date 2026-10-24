# Odoo 17.0 module `mrp`

Extracted from the model source with Python `ast`; see README.md for conventions.

Models defined here: 14. Models extended here: 16.

## `mrp.bom`

Table `mrp_bom`.
Description: Bill of Material.
Inherits: `mail.thread`.
Order: `sequence, id`.
Display name field: `product_tmpl_id`.
Source: `mrp_bom.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `code` | Char |  |  | yes |  | Reference |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `type` | Selection |  | yes | yes | `normal` Manufacture this product, `phantom` Kit; default: `'normal'` | BoM Type |  |
| `product_tmpl_id` | Many2one | `product.template` | yes | yes |  | Product |  |
| `product_id` | Many2one | `product.product` |  | yes |  | Product Variant |  |
| `bom_line_ids` | One2many | `mrp.bom.line` (inverse `bom_id`) |  | no (inverse) |  | BoM Lines |  |
| `byproduct_ids` | One2many | `mrp.bom.byproduct` (inverse `bom_id`) |  | no (inverse) |  | By-products |  |
| `product_qty` | Float |  | yes | yes | default: `1.0` | Quantity |  |
| `product_uom_id` | Many2one | `uom.uom` | yes | yes | default: (computed) | Unit of Measure |  |
| `product_uom_category_id` | Many2one | (from related) |  | no |  |  | related `product_tmpl_id.uom_id.category_id` |
| `sequence` | Integer |  |  | yes |  | Sequence |  |
| `operation_ids` | One2many | `mrp.routing.workcenter` (inverse `bom_id`) |  | no (inverse) |  | Operations |  |
| `ready_to_produce` | Selection |  | yes | yes | `all_available`  When all components are available, `asap` When components for 1st operation are available; default: `'all_available'` | Manufacturing Readiness |  |
| `picking_type_id` | Many2one | `stock.picking.type` |  | yes |  | Operation Type |  |
| `company_id` | Many2one | `res.company` |  | yes | default: (computed) | Company |  |
| `consumption` | Selection |  | yes | yes | `flexible` Allowed, `warning` Allowed with warning, `strict` Blocked; default: `'warning'` | Flexible Consumption |  |
| `possible_product_template_attribute_value_ids` | Many2many | `product.template.attribute.value` |  | no |  |  | compute `_compute_possible_product_template_attribute_value_ids` |
| `allow_operation_dependencies` | Boolean |  |  | yes |  | Operation Dependencies |  |
| `produce_delay` | Integer |  |  | yes | default: `0` | Manufacturing Lead Time |  |
| `days_to_prepare_mo` | Integer |  |  | yes | default: `0` | Days to prepare Manufacturing Order |  |

SQL constraints:

- `qty_positive`: `check (product_qty > 0)`

## `mrp.bom.byproduct`

Table `mrp_bom_byproduct`.
Description: Byproduct.
Order: `sequence, id`.
Display name field: `product_id`.
Source: `mrp_bom.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `product_id` | Many2one | `product.product` | yes | yes |  | By-product |  |
| `company_id` | Many2one | (from related) |  | yes |  |  | related `bom_id.company_id` |
| `product_qty` | Float |  | yes | yes | default: `1.0` | Quantity |  |
| `product_uom_category_id` | Many2one | (from related) |  | no |  |  | related `product_id.uom_id.category_id` |
| `product_uom_id` | Many2one | `uom.uom` | yes | yes |  | Unit of Measure | compute `_compute_product_uom_id` |
| `bom_id` | Many2one | `mrp.bom` |  | yes |  | BoM |  |
| `allowed_operation_ids` | One2many | `mrp.routing.workcenter` |  | no (inverse) |  |  | related `bom_id.operation_ids` |
| `operation_id` | Many2one | `mrp.routing.workcenter` |  | yes |  | Produced in Operation |  |
| `possible_bom_product_template_attribute_value_ids` | Many2many | (from related) |  | no |  |  | related `bom_id.possible_product_template_attribute_value_ids` |
| `bom_product_template_attribute_value_ids` | Many2many | `product.template.attribute.value` |  | yes |  | Apply on Variants |  |
| `sequence` | Integer |  |  | yes |  | Sequence |  |
| `cost_share` | Float |  |  | yes |  | Cost Share (%) |  |

## `mrp.bom.line`

Table `mrp_bom_line`.
Description: Bill of Material Line.
Order: `sequence, id`.
Display name field: `product_id`.
Source: `mrp_bom.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `product_id` | Many2one | `product.product` | yes | yes |  | Component |  |
| `product_tmpl_id` | Many2one | `product.template` |  | yes |  | Product Template | related `product_id.product_tmpl_id` |
| `company_id` | Many2one | (from related) |  | yes |  |  | related `bom_id.company_id` |
| `product_qty` | Float |  | yes | yes | default: `1.0` | Quantity |  |
| `product_uom_id` | Many2one | `uom.uom` | yes | yes | default: (computed) | Product Unit of Measure |  |
| `product_uom_category_id` | Many2one | (from related) |  | no |  |  | related `product_id.uom_id.category_id` |
| `sequence` | Integer |  |  | yes | default: `1` | Sequence |  |
| `bom_id` | Many2one | `mrp.bom` | yes | yes |  | Parent BoM |  |
| `parent_product_tmpl_id` | Many2one | `product.template` |  | no |  | Parent Product Template | related `bom_id.product_tmpl_id` |
| `possible_bom_product_template_attribute_value_ids` | Many2many | (from related) |  | no |  |  | related `bom_id.possible_product_template_attribute_value_ids` |
| `bom_product_template_attribute_value_ids` | Many2many | `product.template.attribute.value` |  | yes |  | Apply on Variants |  |
| `allowed_operation_ids` | One2many | `mrp.routing.workcenter` |  | no (inverse) |  |  | related `bom_id.operation_ids` |
| `operation_id` | Many2one | `mrp.routing.workcenter` |  | yes |  | Consumed in Operation |  |
| `child_bom_id` | Many2one | `mrp.bom` |  | no |  | Sub BoM | compute `_compute_child_bom_id` |
| `child_line_ids` | One2many | `mrp.bom.line` |  | no (inverse) |  | BOM lines of the referred bom | compute `_compute_child_line_ids` |
| `attachments_count` | Integer |  |  | no |  | Attachments Count | compute `_compute_attachments_count` |
| `tracking` | Selection |  |  | no |  |  | related `product_id.tracking` |
| `manual_consumption` | Boolean |  |  | yes | default: `False` | Manual Consumption | compute `_compute_manual_consumption` |
| `manual_consumption_readonly` | Boolean |  |  | no |  | Manual Consumption Readonly | compute `_compute_manual_consumption_readonly` |

SQL constraints:

- `bom_qty_zero`: `CHECK (product_qty>=0)`

## `mrp.document`

Table `mrp_document`.
Description: Production Document.
Delegates (`_inherits`): `{'ir.attachment': 'ir_attachment_id'}`.
Order: `priority desc, id desc`.
Source: `mrp_document.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `ir_attachment_id` | Many2one | `ir.attachment` | yes | yes |  | Related attachment |  |
| `active` | Boolean |  |  | yes | default: `True` | Active |  |
| `priority` | Selection |  |  | yes | `0` Normal, `1` Low, `2` High, `3` Very High | Priority |  |

## `mrp.production`

Table `mrp_production`.
Description: Production Order.
Inherits: `mail.thread`, `mail.activity.mixin`.
Order: `priority desc, date_start asc,id`.
Source: `mrp_production.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes | default: (computed) | Reference |  |
| `priority` | Selection |  |  | yes | `0` Normal, `1` Urgent; default: `'0'` | Priority |  |
| `backorder_sequence` | Integer |  |  | yes | default: `0` | Backorder Sequence |  |
| `origin` | Char |  |  | yes |  | Source |  |
| `product_id` | Many2one | `product.product` | yes | yes |  | Product | compute `_compute_product_id` |
| `product_variant_attributes` | Many2many | `product.template.attribute.value` |  | no |  |  | related `product_id.product_template_attribute_value_ids` |
| `workcenter_id` | Many2one | `mrp.workcenter` |  | no |  |  |  |
| `product_tracking` | Selection |  |  | no |  |  | related `product_id.tracking` |
| `product_tmpl_id` | Many2one | `product.template` |  | no |  | Product Template | related `product_id.product_tmpl_id` |
| `product_qty` | Float |  | yes | yes |  | Quantity To Produce | compute `_compute_product_qty` |
| `product_uom_id` | Many2one | `uom.uom` | yes | yes |  | Product Unit of Measure | compute `_compute_uom_id` |
| `lot_producing_id` | Many2one | `stock.lot` |  | yes |  | Lot/Serial Number |  |
| `qty_producing` | Float |  |  | yes |  | Quantity Producing |  |
| `product_uom_category_id` | Many2one | (from related) |  | no |  |  | related `product_id.uom_id.category_id` |
| `product_uom_qty` | Float |  |  | yes |  | Total Quantity | compute `_compute_product_uom_qty` |
| `picking_type_id` | Many2one | `stock.picking.type` | yes | yes |  | Operation Type | compute `_compute_picking_type_id` |
| `use_create_components_lots` | Boolean |  |  | no |  |  | related `picking_type_id.use_create_components_lots` |
| `use_auto_consume_components_lots` | Boolean |  |  | no |  |  | related `picking_type_id.use_auto_consume_components_lots` |
| `location_src_id` | Many2one | `stock.location` | yes | yes |  | Components Location | compute `_compute_locations` |
| `warehouse_id` | Many2one | (from related) |  | no |  |  | related `location_src_id.warehouse_id` |
| `location_dest_id` | Many2one | `stock.location` | yes | yes |  | Finished Products Location | compute `_compute_locations` |
| `date_deadline` | Datetime |  |  | yes |  | Deadline | compute `_compute_date_deadline` |
| `date_start` | Datetime |  | yes | yes | default: (computed) | Start |  |
| `date_finished` | Datetime |  |  | yes | default: (computed) | End | compute `_compute_date_finished` |
| `duration_expected` | Float |  |  | no |  | Expected Duration | compute `_compute_duration_expected` |
| `duration` | Float |  |  | no |  | Real Duration | compute `_compute_duration` |
| `bom_id` | Many2one | `mrp.bom` |  | yes |  | Bill of Material | compute `_compute_bom_id` |
| `state` | Selection |  |  | yes | `draft` Draft, `confirmed` Confirmed, `progress` In Progress, `to_close` To Close, `done` Done, `cancel` Cancelled | State | compute `_compute_state` |
| `reservation_state` | Selection |  |  | yes | `confirmed` Waiting, `assigned` Ready, `waiting` Waiting Another Operation | MO Readiness | compute `_compute_reservation_state` |
| `move_raw_ids` | One2many | `stock.move` (inverse `raw_material_production_id`) |  | yes |  | Components | compute `_compute_move_raw_ids` |
| `move_finished_ids` | One2many | `stock.move` (inverse `production_id`) |  | yes |  | Finished Products | compute `_compute_move_finished_ids` |
| `all_move_raw_ids` | One2many | `stock.move` (inverse `raw_material_production_id`) |  | no (inverse) |  |  |  |
| `all_move_ids` | One2many | `stock.move` (inverse `production_id`) |  | no (inverse) |  |  |  |
| `move_byproduct_ids` | One2many | `stock.move` |  | no (inverse) |  |  | compute `_compute_move_byproduct_ids` |
| `finished_move_line_ids` | One2many | `stock.move.line` |  | no (inverse) |  | Finished Product | compute `_compute_lines` |
| `workorder_ids` | One2many | `mrp.workorder` (inverse `production_id`) |  | yes |  | Work Orders | compute `_compute_workorder_ids` |
| `move_dest_ids` | One2many | `stock.move` (inverse `created_production_id`) |  | no (inverse) |  | Stock Movements of Produced Goods |  |
| `unreserve_visible` | Boolean |  |  | no |  | Allowed to Unreserve Production | compute `_compute_unreserve_visible` |
| `reserve_visible` | Boolean |  |  | no |  | Allowed to Reserve Production | compute `_compute_unreserve_visible` |
| `user_id` | Many2one | `res.users` |  | yes | default: (computed) | Responsible |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `qty_produced` | Float |  |  | no |  | Quantity Produced | compute `_get_produced_qty` |
| `procurement_group_id` | Many2one | `procurement.group` |  | yes |  | Procurement Group |  |
| `product_description_variants` | Char |  |  | yes |  | Custom Description |  |
| `orderpoint_id` | Many2one | `stock.warehouse.orderpoint` |  | yes |  | Orderpoint |  |
| `propagate_cancel` | Boolean |  |  | yes |  | Propagate cancel and split |  |
| `delay_alert_date` | Datetime |  |  | no |  | Delay Alert Date | compute `_compute_delay_alert_date` |
| `json_popover` | Char |  |  | no |  | JSON data for the popover widget | compute `_compute_json_popover` |
| `scrap_ids` | One2many | `stock.scrap` (inverse `production_id`) |  | no (inverse) |  | Scraps |  |
| `scrap_count` | Integer |  |  | no |  | Scrap Move | compute `_compute_scrap_move_count` |
| `unbuild_ids` | One2many | `mrp.unbuild` (inverse `mo_id`) |  | no (inverse) |  | Unbuilds |  |
| `unbuild_count` | Integer |  |  | no |  | Number of Unbuilds | compute `_compute_unbuild_count` |
| `is_locked` | Boolean |  |  | yes | default: (computed) | Is Locked |  |
| `is_planned` | Boolean |  |  | yes |  | Its Operations are Planned | compute `_compute_is_planned` |
| `show_final_lots` | Boolean |  |  | no |  | Show Final Lots | compute `_compute_show_lots` |
| `production_location_id` | Many2one | `stock.location` |  | yes |  | Production Location | compute `_compute_production_location` |
| `picking_ids` | Many2many | `stock.picking` |  | no |  | Picking associated to this manufacturing order | compute `_compute_picking_ids` |
| `delivery_count` | Integer |  |  | no |  | Delivery Orders | compute `_compute_picking_ids` |
| `confirm_cancel` | Boolean |  |  | no |  |  | compute `_compute_confirm_cancel` |
| `consumption` | Selection |  | yes | yes | `flexible` Allowed, `warning` Allowed with warning, `strict` Blocked; default: `'flexible'` |  |  |
| `mrp_production_child_count` | Integer |  |  | no |  | Number of generated MO | compute `_compute_mrp_production_child_count` |
| `mrp_production_source_count` | Integer |  |  | no |  | Number of source MO | compute `_compute_mrp_production_source_count` |
| `mrp_production_backorder_count` | Integer |  |  | no |  | Count of linked backorder | compute `_compute_mrp_production_backorder` |
| `show_lock` | Boolean |  |  | no |  | Show Lock/unlock buttons | compute `_compute_show_lock` |
| `components_availability` | Char |  |  | no |  | Component Status | compute `_compute_components_availability` |
| `components_availability_state` | Selection |  |  | no | `available` Available, `expected` Expected, `late` Late, `unavailable` Not Available |  | compute `_compute_components_availability` |
| `production_capacity` | Float |  |  | no |  |  | compute `_compute_production_capacity` |
| `show_lot_ids` | Boolean |  |  | no |  | Display the serial number shortcut on the moves | compute `_compute_show_lot_ids` |
| `forecasted_issue` | Boolean |  |  | no |  |  | compute `_compute_forecasted_issue` |
| `show_serial_mass_produce` | Boolean |  |  | no |  | Display the serial mass produce wizard action | compute `_compute_show_serial_mass_produce` |
| `show_allocation` | Boolean |  |  | no |  |  | compute `_compute_show_allocation` |
| `allow_workorder_dependencies` | Boolean |  |  | yes |  | Allow Work Order Dependencies |  |
| `show_produce` | Boolean |  |  | no |  |  | compute `_compute_show_produce` |
| `show_produce_all` | Boolean |  |  | no |  |  | compute `_compute_show_produce` |
| `is_outdated_bom` | Boolean |  |  | yes |  | Outdated BoM |  |

SQL constraints:

- `name_uniq`: `unique(name, company_id)`
- `qty_positive`: `check (product_qty > 0)`

## `mrp.routing.workcenter`

Table `mrp_routing_workcenter`.
Description: Work Center Usage.
Order: `bom_id, sequence, id`.
Source: `mrp_routing.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Operation |  |
| `active` | Boolean |  |  | yes | default: `True` |  |  |
| `workcenter_id` | Many2one | `mrp.workcenter` | yes | yes |  | Work Center |  |
| `sequence` | Integer |  |  | yes | default: `100` | Sequence |  |
| `bom_id` | Many2one | `mrp.bom` | yes | yes |  | Bill of Material |  |
| `company_id` | Many2one | `res.company` |  | no |  | Company | related `bom_id.company_id` |
| `worksheet_type` | Selection |  |  | yes | `pdf` PDF, `google_slide` Google Slide, `text` Text; default: `'text'` | Worksheet |  |
| `note` | Html |  |  | yes |  | Description |  |
| `worksheet` | Binary |  |  | yes |  | PDF |  |
| `worksheet_google_slide` | Char |  |  | yes |  | Google Slide |  |
| `time_mode` | Selection |  |  | yes | `auto` Compute based on tracked time, `manual` Set duration manually; default: `'manual'` | Duration Computation |  |
| `time_mode_batch` | Integer |  |  | yes | default: `10` | Based on |  |
| `time_computed_on` | Char |  |  | no |  | Computed on last | compute `_compute_time_computed_on` |
| `time_cycle_manual` | Float |  |  | yes | default: `60` | Manual Duration |  |
| `time_cycle` | Float |  |  | no |  | Duration | compute `_compute_time_cycle` |
| `workorder_count` | Integer |  |  | no |  | # Work Orders | compute `_compute_workorder_count` |
| `workorder_ids` | One2many | `mrp.workorder` (inverse `operation_id`) |  | no (inverse) |  | Work Orders |  |
| `possible_bom_product_template_attribute_value_ids` | Many2many | (from related) |  | no |  |  | related `bom_id.possible_product_template_attribute_value_ids` |
| `bom_product_template_attribute_value_ids` | Many2many | `product.template.attribute.value` |  | yes |  | Apply on Variants |  |
| `allow_operation_dependencies` | Boolean |  |  | no |  |  | related `bom_id.allow_operation_dependencies` |
| `blocked_by_operation_ids` | Many2many | `mrp.routing.workcenter` (table `mrp_routing_workcenter_dependencies_rel`) |  | yes |  | Blocked By |  |
| `needed_by_operation_ids` | Many2many | `mrp.routing.workcenter` (table `mrp_routing_workcenter_dependencies_rel`) |  | yes |  | Blocks |  |

## `mrp.unbuild`

Table `mrp_unbuild`.
Description: Unbuild Order.
Inherits: `mail.thread`, `mail.activity.mixin`.
Order: `id desc`.
Source: `mrp_unbuild.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes | default: (computed) | Reference |  |
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) | Company |  |
| `product_qty` | Float |  | yes | yes | default: `1.0` | Quantity |  |
| `product_uom_id` | Many2one | `uom.uom` | yes | yes |  | Unit of Measure | compute `_compute_product_uom_id` |
| `bom_id` | Many2one | `mrp.bom` |  | yes |  | Bill of Material |  |
| `mo_id` | Many2one | `mrp.production` |  | yes |  | Manufacturing Order |  |
| `mo_bom_id` | Many2one | `mrp.bom` |  | no |  | Bill of Material used on the Production Order | related `mo_id.bom_id` |
| `lot_id` | Many2one | `stock.lot` |  | yes |  | Lot/Serial Number |  |
| `has_tracking` | Selection |  |  | no |  |  | related `product_id.tracking` |
| `location_id` | Many2one | `stock.location` | yes | yes |  | Source Location | compute `_compute_location_id` |
| `location_dest_id` | Many2one | `stock.location` | yes | yes |  | Destination Location | compute `_compute_location_id` |
| `consume_line_ids` | One2many | `stock.move` (inverse `consume_unbuild_id`) |  | no (inverse) |  | Consumed Disassembly Lines |  |
| `produce_line_ids` | One2many | `stock.move` (inverse `unbuild_id`) |  | no (inverse) |  | Processed Disassembly Lines |  |
| `state` | Selection |  |  | yes | `draft` Draft, `done` Done; default: `'draft'` | Status |  |

SQL constraints:

- `qty_positive`: `check (product_qty > 0)`

## `mrp.workcenter`

Table `mrp_workcenter`.
Description: Work Center.
Inherits: `resource.mixin`.
Order: `sequence, id`.
Source: `mrp_workcenter.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  |  | yes |  | Work Center | related `resource_id.name` |
| `time_efficiency` | Float |  |  | yes | default: `100` | Time Efficiency | related `resource_id.time_efficiency` |
| `active` | Boolean |  |  | yes | default: `True` | Active | related `resource_id.active` |
| `code` | Char |  |  | yes |  | Code |  |
| `note` | Html |  |  | yes |  | Description |  |
| `default_capacity` | Float |  |  | yes | default: `1.0` | Capacity |  |
| `sequence` | Integer |  | yes | yes | default: `1` | Sequence |  |
| `color` | Integer |  |  | yes |  | Color |  |
| `currency_id` | Many2one | `res.currency` | yes | no |  | Currency | related `company_id.currency_id` |
| `costs_hour` | Float |  |  | yes | default: `0.0` | Cost per hour |  |
| `time_start` | Float |  |  | yes |  | Setup Time |  |
| `time_stop` | Float |  |  | yes |  | Cleanup Time |  |
| `routing_line_ids` | One2many | `mrp.routing.workcenter` (inverse `workcenter_id`) |  | no (inverse) |  | Routing Lines |  |
| `has_routing_lines` | Boolean |  |  | no |  |  | compute `_compute_has_routing_lines` |
| `order_ids` | One2many | `mrp.workorder` (inverse `workcenter_id`) |  | no (inverse) |  | Orders |  |
| `workorder_count` | Integer |  |  | no |  | # Work Orders | compute `_compute_workorder_count` |
| `workorder_ready_count` | Integer |  |  | no |  | # Read Work Orders | compute `_compute_workorder_count` |
| `workorder_progress_count` | Integer |  |  | no |  | Total Running Orders | compute `_compute_workorder_count` |
| `workorder_pending_count` | Integer |  |  | no |  | Total Pending Orders | compute `_compute_workorder_count` |
| `workorder_late_count` | Integer |  |  | no |  | Total Late Orders | compute `_compute_workorder_count` |
| `time_ids` | One2many | `mrp.workcenter.productivity` (inverse `workcenter_id`) |  | no (inverse) |  | Time Logs |  |
| `working_state` | Selection |  |  | yes | `normal` Normal, `blocked` Blocked, `done` In Progress | Workcenter Status | compute `_compute_working_state` |
| `blocked_time` | Float |  |  | no |  | Blocked Time | compute `_compute_blocked_time` |
| `productive_time` | Float |  |  | no |  | Productive Time | compute `_compute_productive_time` |
| `oee` | Float |  |  | no |  |  | compute `_compute_oee` |
| `oee_target` | Float |  |  | yes | default: `90` | OEE Target |  |
| `performance` | Integer |  |  | no |  | Performance | compute `_compute_performance` |
| `workcenter_load` | Float |  |  | no |  | Work Center Load | compute `_compute_workorder_count` |
| `alternative_workcenter_ids` | Many2many | `mrp.workcenter` (table `mrp_workcenter_alternative_rel`) |  | yes |  | Alternative Workcenters |  |
| `tag_ids` | Many2many | `mrp.workcenter.tag` |  | yes |  |  |  |
| `capacity_ids` | One2many | `mrp.workcenter.capacity` (inverse `workcenter_id`) |  | no (inverse) |  | Product Capacities |  |

## `mrp.workcenter.capacity`

Table `mrp_workcenter_capacity`.
Description: Work Center Capacity.
Source: `mrp_workcenter.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `workcenter_id` | Many2one | `mrp.workcenter` | yes | yes |  | Work Center |  |
| `product_id` | Many2one | `product.product` | yes | yes |  | Product |  |
| `product_uom_id` | Many2one | `uom.uom` |  | no |  | Product UoM | related `product_id.uom_id` |
| `capacity` | Float |  |  | yes | default: `1.0` | Capacity |  |
| `time_start` | Float |  |  | yes | default: (computed) | Setup Time (minutes) |  |
| `time_stop` | Float |  |  | yes | default: (computed) | Cleanup Time (minutes) |  |

SQL constraints:

- `positive_capacity`: `CHECK(capacity > 0)`
- `unique_product`: `UNIQUE(workcenter_id, product_id)`

## `mrp.workcenter.productivity`

Table `mrp_workcenter_productivity`.
Description: Workcenter Productivity Log.
Order: `id desc`.
Display name field: `loss_id`.
Source: `mrp_workcenter.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `production_id` | Many2one | `mrp.production` |  | no |  | Manufacturing Order | related `workorder_id.production_id` |
| `workcenter_id` | Many2one | `mrp.workcenter` | yes | yes |  | Work Center |  |
| `company_id` | Many2one | `res.company` | yes | yes | default: (computed) |  |  |
| `workorder_id` | Many2one | `mrp.workorder` |  | yes |  | Work Order |  |
| `user_id` | Many2one | `res.users` |  | yes | default: (computed) | User |  |
| `loss_id` | Many2one | `mrp.workcenter.productivity.loss` | yes | yes |  | Loss Reason |  |
| `loss_type` | Selection |  |  | yes |  | Effectiveness | related `loss_id.loss_type` |
| `description` | Text |  |  | yes |  | Description |  |
| `date_start` | Datetime |  | yes | yes | default: (computed) | Start Date |  |
| `date_end` | Datetime |  |  | yes |  | End Date |  |
| `duration` | Float |  |  | yes |  | Duration | compute `_compute_duration` |

## `mrp.workcenter.productivity.loss`

Table `mrp_workcenter_productivity_loss`.
Description: Workcenter Productivity Losses.
Order: `sequence, id`.
Source: `mrp_workcenter.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Blocking Reason |  |
| `sequence` | Integer |  |  | yes | default: `1` | Sequence |  |
| `manual` | Boolean |  |  | yes | default: `True` | Is a Blocking Reason |  |
| `loss_id` | Many2one | `mrp.workcenter.productivity.loss.type` |  | yes |  | Category |  |
| `loss_type` | Selection |  |  | yes |  | Effectiveness Category | related `loss_id.loss_type` |

## `mrp.workcenter.productivity.loss.type`

Table `mrp_workcenter_productivity_loss_type`.
Description: MRP Workorder productivity losses.
Display name field: `loss_type`.
Source: `mrp_workcenter.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `loss_type` | Selection |  | yes | yes | `availability` Availability, `performance` Performance, `quality` Quality, `productive` Productive; default: `'availability'` | Category |  |

## `mrp.workcenter.tag`

Table `mrp_workcenter_tag`.
Description: Add tag for the workcenter.
Order: `name`.
Source: `mrp_workcenter.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Tag Name |  |
| `color` | Integer |  |  | yes | default: (computed) | Color Index |  |

SQL constraints:

- `tag_name_unique`: `unique(name)`

## `mrp.workorder`

Table `mrp_workorder`.
Description: Work Order.
Order: `leave_id, date_start, id`.
Source: `mrp_workorder.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `name` | Char |  | yes | yes |  | Work Order |  |
| `barcode` | Char |  |  | yes |  |  | compute `_compute_barcode` |
| `workcenter_id` | Many2one | `mrp.workcenter` | yes | yes |  | Work Center |  |
| `working_state` | Selection |  |  | no |  | Workcenter Status | related `workcenter_id.working_state` |
| `product_id` | Many2one | (from related) |  | yes |  |  | related `production_id.product_id` |
| `product_tracking` | Selection |  |  | no |  |  | related `product_id.tracking` |
| `product_uom_id` | Many2one | `uom.uom` | yes | yes |  | Unit of Measure |  |
| `production_id` | Many2one | `mrp.production` | yes | yes |  | Manufacturing Order |  |
| `production_availability` | Selection |  |  | yes |  | Stock Availability | related `production_id.reservation_state` |
| `production_state` | Selection |  |  | no |  | Production State | related `production_id.state` |
| `production_bom_id` | Many2one | `mrp.bom` |  | no |  |  | related `production_id.bom_id` |
| `qty_production` | Float |  |  | no |  | Original Production Quantity | related `production_id.product_qty` |
| `company_id` | Many2one | (from related) |  | no |  |  | related `production_id.company_id` |
| `qty_producing` | Float |  |  | no |  | Currently Produced Quantity | compute `_compute_qty_producing` |
| `qty_remaining` | Float |  |  | no |  | Quantity To Be Produced | compute `_compute_qty_remaining` |
| `qty_produced` | Float |  |  | yes | default: `0.0` | Quantity |  |
| `is_produced` | Boolean |  |  | no |  | Has Been Produced | compute `_compute_is_produced` |
| `state` | Selection |  |  | yes | `pending` Waiting for another WO, `waiting` Waiting for components, `ready` Ready, `progress` In Progress, `done` Finished, `cancel` Cancelled; default: `'pending'` | Status | compute `_compute_state` |
| `leave_id` | Many2one | `resource.calendar.leaves` |  | yes |  |  |  |
| `date_start` | Datetime |  |  | yes |  | Start | compute `_compute_dates` |
| `date_finished` | Datetime |  |  | yes |  | End | compute `_compute_dates` |
| `duration_expected` | Float |  |  | yes |  | Expected Duration | compute `_compute_duration_expected` |
| `duration` | Float |  |  | yes |  | Real Duration | compute `_compute_duration` |
| `duration_unit` | Float |  |  | yes |  | Duration Per Unit | compute `_compute_duration` |
| `duration_percent` | Integer |  |  | yes |  | Duration Deviation (%) | compute `_compute_duration` |
| `progress` | Float |  |  | no |  | Progress Done (%) | compute `_compute_progress` |
| `operation_id` | Many2one | `mrp.routing.workcenter` |  | yes |  | Operation |  |
| `has_worksheet` | Boolean |  |  | no |  |  | compute `_compute_has_worksheet` |
| `worksheet` | Binary |  |  | no |  | Worksheet | related `operation_id.worksheet` |
| `worksheet_type` | Selection |  |  | no |  | Worksheet Type | related `operation_id.worksheet_type` |
| `worksheet_google_slide` | Char |  |  | no |  | Worksheet URL | related `operation_id.worksheet_google_slide` |
| `operation_note` | Html |  |  | no |  | Description | related `operation_id.note` |
| `move_raw_ids` | One2many | `stock.move` (inverse `workorder_id`) |  | no (inverse) |  | Raw Moves |  |
| `move_finished_ids` | One2many | `stock.move` (inverse `workorder_id`) |  | no (inverse) |  | Finished Moves |  |
| `move_line_ids` | One2many | `stock.move.line` (inverse `workorder_id`) |  | no (inverse) |  | Moves to Track |  |
| `finished_lot_id` | Many2one | `stock.lot` |  | no |  | Lot/Serial Number | related `production_id.lot_producing_id` |
| `time_ids` | One2many | `mrp.workcenter.productivity` (inverse `workorder_id`) |  | no (inverse) |  |  |  |
| `is_user_working` | Boolean |  |  | no |  | Is the Current User Working | compute `_compute_working_users` |
| `working_user_ids` | One2many | `res.users` |  | no (inverse) |  | Working user on this work order. | compute `_compute_working_users` |
| `last_working_user_id` | One2many | `res.users` |  | no (inverse) |  | Last user that worked on this work order. | compute `_compute_working_users` |
| `costs_hour` | Float |  |  | yes | default: `0.0` | Cost per hour |  |
| `scrap_ids` | One2many | `stock.scrap` (inverse `workorder_id`) |  | no (inverse) |  |  |  |
| `scrap_count` | Integer |  |  | no |  | Scrap Move | compute `_compute_scrap_move_count` |
| `production_date` | Datetime |  |  | yes |  | Production Date | related `production_id.date_start` |
| `json_popover` | Char |  |  | no |  | Popover Data JSON | compute `_compute_json_popover` |
| `show_json_popover` | Boolean |  |  | no |  | Show Popover? | compute `_compute_json_popover` |
| `consumption` | Selection |  |  | no |  |  | related `production_id.consumption` |
| `qty_reported_from_previous_wo` | Float |  |  | yes |  | Carried Quantity |  |
| `is_planned` | Boolean |  |  | no |  |  | related `production_id.is_planned` |
| `allow_workorder_dependencies` | Boolean |  |  | no |  |  | related `production_id.allow_workorder_dependencies` |
| `blocked_by_workorder_ids` | Many2many | `mrp.workorder` (table `mrp_workorder_dependencies_rel`) |  | yes |  | Blocked By |  |
| `needed_by_workorder_ids` | Many2many | `mrp.workorder` (table `mrp_workorder_dependencies_rel`) |  | yes |  | Blocks |  |

## `procurement.group` (extension)

Adds fields to `procurement.group`, defined in another module. Every field below is added by this module.
Source: `stock_rule.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `mrp_production_ids` | One2many | `mrp.production` (inverse `procurement_group_id`) |  | no (inverse) |  |  |  |

## `product.product` (extension)

Adds fields to `product.product`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `variant_bom_ids` | One2many | `mrp.bom` (inverse `product_id`) |  | no (inverse) |  | BOM Product Variants |  |
| `bom_line_ids` | One2many | `mrp.bom.line` (inverse `product_id`) |  | no (inverse) |  | BoM Components |  |
| `bom_count` | Integer |  |  | no |  | # Bill of Material | compute `_compute_bom_count` |
| `used_in_bom_count` | Integer |  |  | no |  | # BoM Where Used | compute `_compute_used_in_bom_count` |
| `mrp_product_qty` | Float |  |  | no |  | Manufactured | compute `_compute_mrp_product_qty` |
| `is_kits` | Boolean |  |  | no |  |  | compute `_compute_is_kits` |

## `product.template` (extension)

Adds fields to `product.template`, defined in another module. Every field below is added by this module.
Source: `product.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `bom_line_ids` | One2many | `mrp.bom.line` (inverse `product_tmpl_id`) |  | no (inverse) |  | BoM Components |  |
| `bom_ids` | One2many | `mrp.bom` (inverse `product_tmpl_id`) |  | no (inverse) |  | Bill of Materials |  |
| `bom_count` | Integer |  |  | no |  | # Bill of Material | compute `_compute_bom_count` |
| `used_in_bom_count` | Integer |  |  | no |  | # of BoM Where is Used | compute `_compute_used_in_bom_count` |
| `mrp_product_qty` | Float |  |  | no |  | Manufactured | compute `_compute_mrp_product_qty` |
| `is_kits` | Boolean |  |  | no |  |  | compute `_compute_is_kits` |

## `res.company` (extension)

Adds fields to `res.company`, defined in another module. Every field below is added by this module.
Source: `res_company.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `manufacturing_lead` | Float |  | yes | yes | default: `0.0` | Manufacturing Lead Time |  |

## `res.config.settings` (extension)

Adds fields to `res.config.settings`, defined in another module. Every field below is added by this module.
Source: `res_config_settings.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `manufacturing_lead` | Float |  |  | no |  | Manufacturing Lead Time | related `company_id.manufacturing_lead` |
| `use_manufacturing_lead` | Boolean |  |  | yes |  | Default Manufacturing Lead Time |  |
| `group_mrp_byproducts` | Boolean |  |  | yes |  | By-Products |  |
| `module_mrp_mps` | Boolean |  |  | yes |  | Master Production Schedule |  |
| `module_mrp_plm` | Boolean |  |  | yes |  | Product Lifecycle Management (PLM) |  |
| `module_quality_control` | Boolean |  |  | yes |  | Quality |  |
| `module_quality_control_worksheet` | Boolean |  |  | yes |  | Quality Worksheet |  |
| `module_mrp_subcontracting` | Boolean |  |  | yes |  | Subcontracting |  |
| `group_mrp_routings` | Boolean |  |  | yes |  | MRP Work Orders |  |
| `group_unlocked_by_default` | Boolean |  |  | yes |  | Unlock Manufacturing Orders |  |
| `group_mrp_reception_report` | Boolean |  |  | yes |  | Allocation Report for Manufacturing Orders |  |
| `group_mrp_workorder_dependencies` | Boolean |  |  | yes |  | Work Order Dependencies |  |

## `stock.lot` (extension)

Adds fields to `stock.lot`, defined in another module. Every field below is added by this module.
Source: `stock_lot.py`.

## `stock.move` (extension)

Adds fields to `stock.move`, defined in another module. Every field below is added by this module.
Source: `stock_move.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `created_production_id` | Many2one | `mrp.production` |  | yes |  | Created Production Order |  |
| `production_id` | Many2one | `mrp.production` |  | yes |  | Production Order for finished products |  |
| `raw_material_production_id` | Many2one | `mrp.production` |  | yes |  | Production Order for components |  |
| `unbuild_id` | Many2one | `mrp.unbuild` |  | yes |  | Disassembly Order |  |
| `consume_unbuild_id` | Many2one | `mrp.unbuild` |  | yes |  | Consumed Disassembly Order |  |
| `allowed_operation_ids` | One2many | `mrp.routing.workcenter` |  | no (inverse) |  |  | related `raw_material_production_id.bom_id.operation_ids` |
| `operation_id` | Many2one | `mrp.routing.workcenter` |  | yes |  | Operation To Consume |  |
| `workorder_id` | Many2one | `mrp.workorder` |  | yes |  | Work Order To Consume |  |
| `bom_line_id` | Many2one | `mrp.bom.line` |  | yes |  | BoM Line |  |
| `byproduct_id` | Many2one | `mrp.bom.byproduct` |  | yes |  | By-products |  |
| `unit_factor` | Float |  |  | yes |  | Unit Factor | compute `_compute_unit_factor` |
| `is_done` | Boolean |  |  | yes |  | Done | compute `_compute_is_done` |
| `order_finished_lot_id` | Many2one | `stock.lot` |  | yes |  | Finished Lot/Serial Number | related `raw_material_production_id.lot_producing_id` |
| `should_consume_qty` | Float |  |  | no |  | Quantity To Consume | compute `_compute_should_consume_qty` |
| `cost_share` | Float |  |  | yes |  | Cost Share (%) |  |
| `product_qty_available` | Float |  |  | no |  | Product On Hand Quantity | related `product_id.qty_available` |
| `product_virtual_available` | Float |  |  | no |  | Product Forecasted Quantity | related `product_id.virtual_available` |
| `description_bom_line` | Char |  |  | no |  | Kit | compute `_compute_description_bom_line` |
| `manual_consumption` | Boolean |  |  | yes |  | Manual Consumption | compute `_compute_manual_consumption` |

## `stock.move.line` (extension)

Adds fields to `stock.move.line`, defined in another module. Every field below is added by this module.
Source: `stock_move.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `workorder_id` | Many2one | `mrp.workorder` |  | yes |  | Work Order |  |
| `production_id` | Many2one | `mrp.production` |  | yes |  | Production Order |  |
| `description_bom_line` | Char |  |  | no |  |  | related `move_id.description_bom_line` |

## `stock.picking` (extension)

Adds fields to `stock.picking`, defined in another module. Every field below is added by this module.
Source: `stock_picking.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `has_kits` | Boolean |  |  | no |  |  | compute `_compute_has_kits` |

## `stock.picking.type` (extension)

Adds fields to `stock.picking.type`, defined in another module. Every field below is added by this module.
Source: `stock_picking.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `code` | Selection |  |  | yes | added: `mrp_operation` Manufacturing |  |  |
| `count_mo_todo` | Integer |  |  | no |  | Number of Manufacturing Orders to Process | compute `_get_mo_count` |
| `count_mo_waiting` | Integer |  |  | no |  | Number of Manufacturing Orders Waiting | compute `_get_mo_count` |
| `count_mo_late` | Integer |  |  | no |  | Number of Manufacturing Orders Late | compute `_get_mo_count` |
| `use_create_components_lots` | Boolean |  |  | yes | default: `False` | Create New Lots/Serial Numbers for Components |  |
| `use_auto_consume_components_lots` | Boolean |  |  | yes |  | Consume Reserved Lots/Serial Numbers automatically |  |
| `auto_print_done_production_order` | Boolean |  |  | yes |  | Auto Print Done Production Order |  |
| `auto_print_done_mrp_product_labels` | Boolean |  |  | yes |  | Auto Print Produced Product Labels |  |
| `mrp_product_label_to_print` | Selection |  |  | yes | `pdf` PDF, `zpl` ZPL; default: `'pdf'` | Product Label to Print |  |
| `auto_print_done_mrp_lot` | Boolean |  |  | yes |  | Auto Print Produced Lot Label |  |
| `done_mrp_lot_label_to_print` | Selection |  |  | yes | `pdf` PDF, `zpl` ZPL; default: `'pdf'` | Lot/SN Label to Print |  |
| `auto_print_mrp_reception_report` | Boolean |  |  | yes |  | Auto Print Allocation Report |  |
| `auto_print_mrp_reception_report_labels` | Boolean |  |  | yes |  | Auto Print Allocation Report Labels |  |
| `auto_print_generated_mrp_lot` | Boolean |  |  | yes |  | Auto Print Generated Lot/SN Label |  |
| `generated_mrp_lot_label_to_print` | Selection |  |  | yes | `pdf` PDF, `zpl` ZPL; default: `'pdf'` | Generated Lot/SN Label to Print |  |

## `stock.quant` (extension)

Adds fields to `stock.quant`, defined in another module. Every field below is added by this module.
Source: `stock_quant.py`.

## `stock.rule` (extension)

Adds fields to `stock.rule`, defined in another module. Every field below is added by this module.
Source: `stock_rule.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `action` | Selection |  |  | yes | added: `manufacture` Manufacture |  |  |

## `stock.scrap` (extension)

Adds fields to `stock.scrap`, defined in another module. Every field below is added by this module.
Source: `stock_scrap.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `production_id` | Many2one | `mrp.production` |  | yes |  | Manufacturing Order |  |
| `workorder_id` | Many2one | `mrp.workorder` |  | yes |  | Work Order |  |
| `product_is_kit` | Boolean |  |  | no |  |  | related `product_id.is_kits` |
| `product_template` | Many2one | (from related) |  | no |  |  | related `product_id.product_tmpl_id` |
| `bom_id` | Many2one | `mrp.bom` |  | yes |  | Kit |  |

## `stock.traceability.report` (extension)

Adds fields to `stock.traceability.report`, defined in another module. Every field below is added by this module.
Source: `stock_traceability.py`.

## `stock.warehouse` (extension)

Adds fields to `stock.warehouse`, defined in another module. Every field below is added by this module.
Source: `stock_warehouse.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `manufacture_to_resupply` | Boolean |  |  | yes | default: `True` | Manufacture to Resupply |  |
| `manufacture_pull_id` | Many2one | `stock.rule` |  | yes |  | Manufacture Rule |  |
| `manufacture_mto_pull_id` | Many2one | `stock.rule` |  | yes |  | Manufacture MTO Rule |  |
| `pbm_mto_pull_id` | Many2one | `stock.rule` |  | yes |  | Picking Before Manufacturing MTO Rule |  |
| `sam_rule_id` | Many2one | `stock.rule` |  | yes |  | Stock After Manufacturing Rule |  |
| `manu_type_id` | Many2one | `stock.picking.type` |  | yes |  | Manufacturing Operation Type |  |
| `pbm_type_id` | Many2one | `stock.picking.type` |  | yes |  | Picking Before Manufacturing Operation Type |  |
| `sam_type_id` | Many2one | `stock.picking.type` |  | yes |  | Stock After Manufacturing Operation Type |  |
| `manufacture_steps` | Selection |  | yes | yes | `mrp_one_step` Manufacture (1 step), `pbm` Pick components and then manufacture (2 steps), `pbm_sam` Pick components, manufacture and then store products (3 steps); default: `'mrp_one_step'` | Manufacture |  |
| `pbm_route_id` | Many2one | `stock.route` |  | yes |  | Picking Before Manufacturing Route |  |
| `pbm_loc_id` | Many2one | `stock.location` |  | yes |  | Picking before Manufacturing Location |  |
| `sam_loc_id` | Many2one | `stock.location` |  | yes |  | Stock after Manufacturing Location |  |

## `stock.warehouse.orderpoint` (extension)

Adds fields to `stock.warehouse.orderpoint`, defined in another module. Every field below is added by this module.
Source: `stock_orderpoint.py`, `stock_warehouse.py`.

| field | type | relation | required | stored | values / default | label | notes |
|---|---|---|---|---|---|---|---|
| `show_bom` | Boolean |  |  | no |  | Show BoM column | compute `_compute_show_bom` |
| `bom_id` | Many2one | `mrp.bom` |  | yes |  | Bill of Materials |  |
| `manufacturing_visibility_days` | Float |  |  | yes | default: `0.0` |  |  |
