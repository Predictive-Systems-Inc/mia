# bookkeeper v1: design

Date: 20 October 2026. Catalogue row: docs/agents-catalogue.md (bookkeeper). Shapes followed:
docs/superpowers/specs/2026-10-19-hr-officer-design.md and 2026-10-19-branch-manager-design.md.
Filipino first, never "Tagalog". The owner answered Q84 to Q87 on 20 October (D38): tender on counts and
supplier orders to core (data standard 1.6), the HR tables to core so payroll enters profit, no
utang in v1, VAT at 12 percent.

## 1. Goal

The bookkeeper keeps Ferino's money straight without a spreadsheet: the closing cash count
against the day's sales with a threshold for short or over; GCash and Maya settlements matched
to the day's sales by tender; Grab and Foodpanda payouts with their commissions; expenses and
petty cash by category; bank deposits; the BIR sales journal and the quarterly VAT figures as code
(output VAT on sales less input VAT from receipts); monthly profit per branch including
payroll cost from the shared payslips. Proof shop: Ferino's Bibingka (two kiosks).

Out of scope for v1: receipt photo reading, bank and e-wallet connectors (amounts are typed by
head staff), e-filing, the annual packet (a follow-up once a year of data exists), utang of any kind
(staff advances and suki credit, Q86: not in v1; Q57 stays answered no for now), percentage tax
(the dated table carries both regimes, the owner's setting picks VAT).

## 2. Data standard check (gate 1, the owner)

Data standard 1.6 (D38, answered yes): `sales_counts.tender` (cash, gcash, maya, grab,
foodpanda; default cash; the sales supervisor's count parser reads a tender word, the clerk
says it when it is not cash); `inventory_manager_orders` promoted to core `supplier_orders`;
`hr_officer_contracts`, `hr_officer_payslips`, `hr_officer_leave` promoted to core `contracts`,
`payslips`, `leave` with their `__redact__` and the HR officer's own-row rules kept (Q59 closed;
the bookkeeper reads payslip totals per branch and month, never lines by person, through a
read_all grant on payslips for owner and admin only). One migration edit, one ADR (018).
Reads: core `sales_counts`, `stock_events` (waste at cost), `retail_items` (cost),
`supplier_orders`, `payslips` (totals), `person`. Writes: agent-owned `bookkeeper_cash_counts`,
`bookkeeper_settlements`, `bookkeeper_payouts`, `bookkeeper_expenses` (petty cash is an expense
with source petty), `bookkeeper_deposits`, `bookkeeper_tax` (the dated rates and the quarterly
figures). No utang table in v1.

## 3. Who talks to it

Head staff (supervisor): the closing count, settlements, expenses with a receipt amount, petty
cash, deposits made, utang entries and repayments, their branch only. Owner and admin: all
branches, thresholds, categories, the tax figures, monthly profit, utang approval above a limit.
Clerk: not offered (cashiering is head staff's). Languages: ten, Filipino first.

## 4. Scenarios (the acceptance list)

1. Closing count: "cash count 12,450" after close: against the day's cash sales (counts by
   tender, or total sales less typed non-cash tenders); short or over beyond the threshold
   (settings, default 100 pesos) tells the owner with the amount; within it, a plain
   confirmation. `test_a_closing_count_compares_with_cash_sales`,
   `test_a_short_beyond_the_threshold_tells_the_owner`.
2. Settlement: "GCash settlement 3,210 for yesterday": matched to yesterday's GCash sales less
   the fee rate (settings); a gap beyond the threshold is flagged. `test_a_gcash_settlement_is_matched`.
3. Payout: "Grab payout 8,900 for the week": matched to Grab sales less commission (settings),
   the commission shown. `test_a_grab_payout_shows_the_commission`.
4. Expense: "nagbayad ng 2,000 sa kuryente, resibo 1234": category from a fixed list (utilities,
   rent, supplies, transport, repairs, other), the receipt number kept, a monthly total by
   category. `test_an_expense_is_recorded_by_category`.
5. Petty cash: "petty cash 500 para sa yelo": an expense from the petty fund; the fund's balance
   and a refill reminder under the floor. `test_petty_cash_keeps_its_balance`.
6. Deposit: "deposited 20,000 BDO today": the undeposited cash balance falls; a reminder when
   undeposited cash exceeds the limit for two days. `test_a_deposit_lowers_undeposited_cash`.
7. Utang: out of v1 (Q86); a message about an advance or suki credit gets the capabilities
   reply naming it as not built. `test_utang_is_not_built`.
8. Tax: the BIR sales journal for a month (gross sales by day and tender) and the quarterly VAT
   figure (12 percent output VAT on VAT-able sales less input VAT from expenses recorded with a
   VAT amount; the dated table also carries the 3 percent percentage tax for other shops; the
   regime is a setting) as code with unit tests. `test_quarterly_vat_is_computed_from_the_journal_and_receipts`.
9. Monthly profit per branch: sales less cost of goods (stock issued at cost), waste at cost,
   expenses, commissions and fees, supplier spend, payroll (payslip totals of the month); a
   plain table to the owner on the second business day. `test_monthly_profit_per_branch_includes_payroll`.
10. Security: a supervisor sees their branch only and never a payslip total; a clerk is not
    offered the agent; an expense over the owner's limit (settings, default 5,000) needs the
    owner's approval card (money risk); amounts are never model-computed.
    `test_a_supervisor_reads_their_branch_only`, `test_a_large_expense_needs_the_owner`.

## 5. Data

Agent-owned (ULIDs, minor units plus currency, aware times, `0000_initial` edited in place):
`bookkeeper_cash_counts` (branch, business_date, counted, expected, difference, counted_by,
note), `bookkeeper_settlements` (branch, provider gcash or maya, period_start, period_end,
amount, expected, fee, matched_by), `bookkeeper_payouts` (provider grab or foodpanda, period,
amount, expected, commission), `bookkeeper_expenses` (branch, business_date, category, amount,
vat_amount nullable, receipt_no nullable, source cash or petty or bank, approval_id nullable,
recorded_by), `bookkeeper_deposits` (branch, business_date, bank, amount, reference),
`bookkeeper_tax`
(regime, period, gross, taxable, rate, due; rates as a dated table in code like the PH
contributions). Settings: thresholds, fee and commission rates per provider, the expense approval limit, the
tax regime (vat for Ferino's), the petty cash floor, the undeposited cash limit.

## 6. The agent

Actions: cash_count, settlement, payout, expense, petty_cash, deposit, balances, journal,
tax_quarter, profit, greeting, clarify. Tools: record_cash_count (write), record_settlement,
record_payout, record_expense (money risk above the limit: approval always when amount > limit,
approvers owner and admin; the owner's own entry decided by the owner, D37), record_petty,
record_deposit, balances (read), sales_journal (read), tax_quarter (read), monthly_profit
(read_all, owner and admin; reads payslip totals).
Due work: the closing-count reminder an hour after close when no count exists; the petty
floor and undeposited cash reminders; the monthly profit on the second business day; the
quarterly tax figure five days before the deadline (dated table). Events: `bookkeeper.*` per
write. Every amount is typed and parsed by code; the model picks the action and the provider.

## 7. Parsing

Code: amounts (the price parser's money reading), providers and banks from fixed lists, the
category list, dates from `parsing.find_dates`, person names from the branch's people (own
branch) with the pseudonymiser; Jev picks action, provider, category and person among
candidates. Negations as corrections.

## 8. i18n

Keys `bk.*`, `intent.bookkeeper.*`, the label; en and fi by the build, the eight modules as
drafts (Q28 to Q35).

## 9. Seed and configuration

Ferino's settings: thresholds, GCash and Maya fee 2 percent, Grab commission 25 percent,
Foodpanda 28 percent (placeholders the owner corrects), the VAT regime, limits. Seed: two
weeks of cash counts with tenders on the counts, settlements, a payout, expenses with VAT
amounts, a deposit.

## 10. Testing and gates

Pure-code tests for every computation (tax, matching, profit, balances); chat tests through
run_turn; approval tests (large expense, staff advance); due tests at fixed clocks; the decider
gate at the Q40 bar on fresh halves; router seeds with the contrast "cash, expenses, deposits,
settlements and tax; not sales counts and not pay".

## 11. Open questions (asked and answered 20 October, D38)

Q84 data standard 1.6 (yes): `sales_counts.tender` and `supplier_orders` in core. Q85 (yes):
the HR tables promoted; payroll enters profit as totals. Q86 (no): no utang in v1. Q87 (VAT):
12 percent, output less input, the dated table keeps both regimes. New: Q88 which sales are
VAT-exempt at Ferino's (assumed none; all sales VAT-able); Q89 the input VAT rule for receipts
without a VAT amount (assumed no input VAT).

## 12. Order of work

1. Data standard 1.6 (tender, supplier_orders, the HR tables), tables, settings, seed, policy. 2. Pure code: matching, tax
table, profit, balances. 3. Actions and decider. 4. Tools and the two approvals. 5. Chat turn,
scenarios 1 to 8 and 10. 6. Due work (reminders, monthly profit, quarterly figure). 7. Ten
languages. 8. Evals, gates, docs.

## Carried over

(filled by the reviews)
