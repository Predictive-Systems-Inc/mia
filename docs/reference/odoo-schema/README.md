# Odoo 17.0 data schema (reference)

A reference for designing the Mia backend, starting with sales. This folder holds a schema
description only. No Odoo code is in this repository and none was run, imported or executed.

## Source

- Repository: odoo/odoo on GitHub, branch `17.0`, licence LGPL-3.
- Commit: `3682340c62f59b2a317601b2da849af12cb52b48` (committed 21 Oct 2026, read 22 Oct 2026).
- Fetched with a shallow, sparse clone of the `models/` folder of each module listed below.

## How it was extracted

A small script parsed each `models/*.py` file with the Python `ast` module (no imports, no
execution) and read, per class that derives from `models.Model`, `models.AbstractModel` or
`models.TransientModel`:

- `_name`, `_inherit`, `_inherits`, `_description`, `_order`, `_rec_name`, `_table`, `_auto`,
  `_sql_constraints`;
- every `name = fields.<Type>(...)` assignment in the class body: the type, `comodel_name` and
  `inverse_name` (positional or keyword), the Many2many relation table when named, `required`,
  `compute`, `related`, `store`, `company_dependent`, `string` (the label), `selection` or
  `selection_add` when literal (also when it names a module or class level list constant), and
  `default` when literal.

Values that are not literals are shown as `(dynamic: ...)` with the source expression, or as
`default: (computed)`. Expressions that call a method at runtime are not evaluated.

## Modules covered

| module | file | models defined | models extended | fields |
|---|---|---|---|---|
| base (`odoo/addons/base`) | base.md | 109 | 0 | 681 |
| product | product.md | 16 | 8 | 207 |
| sale | sale.md | 2 | 18 | 149 |
| sale_stock | sale_stock.md | 0 | 16 | 36 |
| account | account.md | 35 | 23 | 823 |
| point_of_sale | point_of_sale.md | 13 | 25 | 351 |
| stock | stock.md | 20 | 11 | 554 |
| purchase | purchase.md | 2 | 12 | 107 |
| mrp | mrp.md | 14 | 16 | 359 |
| hr | hr.md | 9 | 12 | 247 |
| hr_attendance | hr_attendance.md | 2 | 7 | 78 |
| hr_holidays | hr_holidays.md | 6 | 9 | 204 |
| crm | crm.md | 6 | 10 | 142 |
| loyalty | loyalty.md | 5 | 4 | 94 |
| sale_loyalty | sale_loyalty.md | 1 | 5 | 15 |
| pos_loyalty | pos_loyalty.md | 0 | 11 | 17 |

`sales-first.md` is the hand-picked subset for the sales flow, quotation to payment.

Not covered:

- `hr_payroll_account` (and payroll in general) is Odoo Enterprise, not in odoo/odoo.
- Modules these depend on but that were not fetched: `mail` (the `mail.thread` and
  `mail.activity.mixin` mixins add chatter fields such as `message_ids` and `activity_ids`),
  `uom`, `sales_team` (`crm.team`), `payment` (`payment.transaction`), `analytic`, `utm`,
  `portal`, `resource` (working calendars used by hr). Fields pointing at their models are listed,
  the models themselves are not.
- `wizard/` and `report/` folders (transient wizards and SQL report views).
- Fields the ORM creates at runtime (for example the parent fields read through `_inherits`).

## Conventions

- A model is a table named by replacing dots with underscores (`sale.order` is `sale_order`),
  unless `_table` says otherwise. Every table also has `id`, `create_uid`, `create_date`,
  `write_uid` and `write_date`, added by the ORM and not listed.
- Abstract models (mixins) have no table; their fields land in each model that inherits them.
- A file section marked "(extension)" is a model defined in another module; the fields listed
  there are the ones this module adds or redefines. "(redefines inherited field)" in the relation
  column means the module changes an existing field (for example its `ondelete` or label) without
  repeating the comodel.
- `_inherits` (delegation, for example `product.product` to `product.template` and
  `account.payment` to `account.move`) means the child row holds a required Many2one to the parent
  and reads the parent's fields as its own.
- Many2one is a foreign key column (`<field>` holds the comodel's `id`).
- One2many is the inverse side of a Many2one on the comodel (named in "inverse"), not a column.
- Many2many is a join table; its name is shown when the source names it, otherwise the ORM
  builds one from the two table names.
- A computed field without `store=True`, and a `related` field without `store=True`, is not a
  column ("stored: no"). `company_dependent` fields are stored per company in `ir_property`, not
  as a column.
- Money in Odoo is a float (`Float` or `Monetary` with a `currency_id`). Mia stores money as
  integer minor units plus currency (CLAUDE.md rule 10), so this is a shape reference, not a
  storage format to copy.
