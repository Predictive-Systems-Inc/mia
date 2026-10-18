"""Bikol strings. Machine drafts until a native speaker reviews them (docs/questions.md)."""

STRINGS: dict[str, str | list[str]] = {
    "agent.shift_supervisor.label": "Shift Supervisor",
    "agent.sales_supervisor.label": "Sales Supervisor",
    "agent.inventory_manager.label": "Inventory Manager",
    "agent.bookkeeper.label": "Bookkeeper",
    "agent.hr_officer.label": "HR Officer",
    "agent.branch_manager.label": "Branch Manager",
    "chat.switched": "({agent})",
    "route.question": "Manonongod daw ini sa:",
    "reply.busy": [
        "Okupado si Mia ngunyan asin sasagutan ka niya sa dai pa magluwat.",
        "Medyo okupado si Mia ngunyan. Sasimbagan ka niya sa dai pa magluwat.",
    ],
    "reply.no_agent": (
        "Mayo pa akong maitatabang saimo digde. Sabihon sa saimong supervisor na i-set up si Mia para saimo."
    ),
    "reply.unavailable": [
        "Pasensya, dai ako makasimbag ngunyan. Pakisuway giraray sa mahapot.",
        "Pasensya, may nagkaproblema saakin. Pakisuway giraray sa dai pa magluwat.",
    ],
    "reply.not_built": "Dai pa ini matabangan ni Mia.",
    "language.set": "Sige, {language} an gagamiton ko.",
}
