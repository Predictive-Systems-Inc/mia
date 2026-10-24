# Eval test messages

One CSV per agent (`<agent_id>.csv`, `router.csv` for the router), UTF-8, read by `__init__.py` for each `<id>_cases.py`; a run also writes `docs/research/<agent>-<minute>.results.csv`.
Columns: `intent` (the expected action, `ask` for a short row that should ask, or the expected agent in router.csv), `message` (the text as staff type it), `lang` (en, fil, or fi in the router), `half` (tune, gate, short or spent; spent rows never run), `role` (the sender) and `previous` (Mia's last message, when there is one).
Argument columns, blank when unused: `item` (a seeded name or a typed code), `amount` (integer minor units), `number`, `date` (ISO, or `+Nd`: N days after the set's TODAY), `provider`, `category`, `kiosk`, `direction`, `unit`.
`extra` is a JSON object for the rest: the scenario, the remainder of an expected dict (including null values), several items, the router's active agent and group.
Edit a row in a spreadsheet or by hand, keep the header exactly, and run the set's shape test (`uv run pytest node/tests/evals/test_<agent>_cases.py --no-cov`).

The short rows are not all blind. The sales supervisor's option cues (52c164a) were written with its current short rows in view, so its short half no longer measures it blind: a blind measurement of that agent needs a fresh short block written without reading the action descriptions. The other agents' short rows predate their descriptions, so their short halves still read blind. The router's short rows (23 Oct 2026) are not blind for the shift supervisor: its option names the check-in and check-out texts in them ("here na", "going home").
