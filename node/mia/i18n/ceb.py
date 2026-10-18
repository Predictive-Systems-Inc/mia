"""Cebuano strings. Machine drafts until a native speaker reviews them (docs/questions.md)."""

STRINGS: dict[str, str | list[str]] = {
    "agent.shift_supervisor.label": "Shift Supervisor",
    "agent.sales_supervisor.label": "Sales Supervisor",
    "agent.inventory_manager.label": "Inventory Manager",
    "agent.bookkeeper.label": "Bookkeeper",
    "agent.hr_officer.label": "HR Officer",
    "agent.branch_manager.label": "Branch Manager",
    "chat.switched": "({agent})",
    "route.question": "Mahitungod ba ni sa:",
    "reply.busy": [
        "Busy si Mia karon ug motubag ka niya sa dili madugay.",
        "Medyo busy si Mia karon. Makadawat ka og tubag sa dili madugay.",
    ],
    "reply.no_agent": (
        "Wala pa koy mahimo nga makatabang nimo dinhi. Pangayoa ang imong supervisor nga i-set up si Mia para nimo."
    ),
    "reply.unavailable": [
        "Pasensya, dili ko makatubag karon. Sulayi usab pagkahuman sa usa ka minuto.",
        "Pasensya, adunay nagkaproblema sa akong kiliran. Sulayi usab dayon.",
    ],
    "reply.not_built": "Dili pa kini matabangan ni Mia.",
    "language.set": "Sige, gamiton nako ang {language}.",
}
