"""Waray strings. Machine drafts until a native speaker reviews them (docs/questions.md)."""

STRINGS: dict[str, str | list[str]] = {
    "agent.shift_supervisor.label": "Shift Supervisor",
    "agent.sales_supervisor.label": "Sales Supervisor",
    "agent.inventory_manager.label": "Inventory Manager",
    "agent.bookkeeper.label": "Bookkeeper",
    "agent.hr_officer.label": "HR Officer",
    "agent.branch_manager.label": "Branch Manager",
    "chat.switched": "({agent})",
    "route.question": "Mahitungod ba iniha:",
    "reply.busy": [
        "Busy hi Mia yana ngan sasabton ka niya ha diri pa madugay.",
        "Medyo busy hi Mia yana. Makakarawat ka hin sabat ha diri pa madugay.",
    ],
    "reply.no_agent": (
        "Waray pa ak mabubulig ha im dinhi. Pakisabi ha im supervisor nga i-set up hi Mia para ha im."
    ),
    "reply.unavailable": [
        "Pasensya, diri ak makasabat yana. Pakisulay liwat ha makadiyot.",
        "Pasensya, may nagkaproblema ha akon. Pakisulay liwat ha diri pa madugay.",
    ],
    "reply.not_built": "Diri pa ini mabubuligan ni Mia.",
    "cli.learned.none": "Waray pa natun-an nga ruta hi Mia dinhi.",
    "cli.learned.row": "{agent}\t{route}\t{count}",
    "cli.forgotten": "Nalimtan na: {route}",
    "language.set": "Sige, an {language} an gagamiton ko.",
}
