"""Hiligaynon strings. Machine drafts until a native speaker reviews them (docs/questions.md)."""

STRINGS: dict[str, str | list[str]] = {
    "agent.shift_supervisor.label": "Shift Supervisor",
    "agent.sales_supervisor.label": "Sales Supervisor",
    "agent.inventory_manager.label": "Inventory Manager",
    "agent.bookkeeper.label": "Bookkeeper",
    "agent.hr_officer.label": "HR Officer",
    "agent.branch_manager.label": "Branch Manager",
    "chat.switched": "({agent})",
    "route.question": "Parte bala ini sa:",
    "reply.busy": [
        "Busy si Mia subong kag sabton ka niya sa indi madugay.",
        "Medyo busy si Mia subong. Makabaton ka sang sabat sa indi madugay.",
    ],
    "reply.no_agent": (
        "Wala pa ako sing mahibulong sa imo diri. Pangayuha ang imo supervisor nga i-set up si Mia para sa imo."
    ),
    "reply.unavailable": [
        "Pasensya, indi ako makasabat subong. Palihog sulay liwat sa makadali.",
        "Pasensya, may nagkaproblema sa akon. Palihog sulay liwat sa indi madugay.",
    ],
    "reply.not_built": "Indi pa ini mabuligan ni Mia.",
    "language.set": "Sige, {language} ang gamiton ko.",
}
