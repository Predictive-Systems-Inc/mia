"""Filipino strings. Machine drafts until a native speaker reviews them (docs/questions.md)."""

STRINGS: dict[str, str | list[str]] = {
    "agent.shift_supervisor.label": "Shift Supervisor",
    "agent.sales_supervisor.label": "Sales Supervisor",
    "agent.inventory_manager.label": "Inventory Manager",
    "agent.bookkeeper.label": "Bookkeeper",
    "agent.hr_officer.label": "HR Officer",
    "agent.branch_manager.label": "Branch Manager",
    "chat.switched": "({agent})",
    "route.question": "Tungkol ba ito sa:",
    "reply.busy": [
        "Abala si Mia ngayon at sasagutin ka niya mamaya.",
        "Medyo abala si Mia ngayon. Sasagutin ka niya sa lalong madaling panahon.",
    ],
    "reply.no_agent": (
        "Wala pa akong maitutulong sa iyo dito. Pakisabi sa iyong supervisor na i-set up si Mia para sa iyo."
    ),
    "reply.unavailable": [
        "Pasensya, hindi ako makasagot ngayon. Pakisubukan ulit mamaya.",
        "Pasensya, may nagkaproblema sa akin. Pakisubukan ulit maya-maya.",
    ],
    "language.set": "Sige, {language} na ang gagamitin ko.",
}
