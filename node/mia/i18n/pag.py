"""Pangasinan strings. Machine drafts until a native speaker reviews them (docs/questions.md)."""

STRINGS: dict[str, str | list[str]] = {
    "agent.shift_supervisor.label": "Shift Supervisor",
    "agent.sales_supervisor.label": "Sales Supervisor",
    "agent.inventory_manager.label": "Inventory Manager",
    "agent.bookkeeper.label": "Bookkeeper",
    "agent.hr_officer.label": "HR Officer",
    "agent.branch_manager.label": "Branch Manager",
    "chat.switched": "({agent})",
    "route.question": "Nipaakar ya kasi ya:",
    "reply.busy": [
        "Busy si Mia natan tan sasagutan daka na bayad.",
        "Medyo busy si Mia natan. Sasagutan daka na ed saya.",
    ],
    "reply.no_agent": (
        "Anggapoy nitulong ko ed sika dia. Ibagam ed supervisor mo ya i-set up si Mia parad sika."
    ),
    "reply.unavailable": [
        "Pasensya, say anggapo ko makasagot natan. Pakiulit lamet bayad.",
        "Pasensya, wala so napaay ed sakey. Pakiulit lamet ed saya.",
    ],
    "reply.not_built": "Ag ni natulongan nen Mia iya.",
    "language.set": "Sige, {language} so usaren ko.",
}
