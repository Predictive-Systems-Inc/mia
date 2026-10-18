"""Ilocano strings. Machine drafts until a native speaker reviews them (docs/questions.md)."""

STRINGS: dict[str, str | list[str]] = {
    "agent.shift_supervisor.label": "Shift Supervisor",
    "agent.sales_supervisor.label": "Sales Supervisor",
    "agent.inventory_manager.label": "Inventory Manager",
    "agent.bookkeeper.label": "Bookkeeper",
    "agent.hr_officer.label": "HR Officer",
    "agent.branch_manager.label": "Branch Manager",
    "chat.switched": "({agent})",
    "route.question": "Maipapan kadi daytoy iti:",
    "reply.busy": [
        "Busy ni Mia ita ket sungbatannaka iti dandani.",
        "Medyo busy ni Mia ita. Masungbatanka iti sungbat iti dandani.",
    ],
    "reply.no_agent": (
        "Awan pay ti maitulongko kenka ditoy. Kiddawem iti supervisormo nga i-set up ni Mia para kenka."
    ),
    "reply.unavailable": [
        "Pasensia, saanak a makasungbat ita. Pakiulit manen iti madamdama.",
        "Pasensia, adda napaay iti bangirak. Pakiulit manen iti dandani.",
    ],
    "language.set": "Wen, {language} ti usarek.",
}
